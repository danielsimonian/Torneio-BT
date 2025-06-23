import os
from flask import Flask, jsonify, request
from pymongo import MongoClient
from dotenv import load_dotenv
from datetime import datetime
from bson.objectid import ObjectId
from flask_cors import CORS

from PIL import Image, ImageDraw, ImageFont
import qrcode
import base64
import io

load_dotenv()

app = Flask(__name__)
CORS(app) 

mongo_uri = os.getenv("MONGO_URI")
if not mongo_uri:
    raise ValueError("MONGO_URI não encontrada nas variáveis de ambiente.")

client = MongoClient(mongo_uri)
db = client.torneiobt_db

players_collection = db.players
tournaments_collection = db.tournaments
registrations_collection = db.registrations
matches_collection = db.matches 

@app.route('/')
def hello_world():
    return jsonify(message="Olá do backend Python com MongoDB conectado!")

@app.route('/test_db')
def test_db_connection():
    try:
        db.test_collection.insert_one({"test": "conexao_ok", "timestamp": datetime.utcnow()})
        db.test_collection.find_one({"test": "conexao_ok"})
        return jsonify(message="Conexão com o MongoDB Atlas bem-sucedida!", status="success"), 200
    except Exception as e:
        return jsonify(message=f"Erro ao conectar ou testar o MongoDB: {e}", status="error"), 500

@app.route('/players', methods=['POST'])
def create_player():
    data = request.get_json()
    if not data:
        return jsonify(message="Dados inválidos ou ausentes"), 400

    required_fields = ["nomeCompleto", "email", "dataNascimento", "nivelHabilidade", "genero"]
    for field in required_fields:
        if field not in data:
            return jsonify(message=f"Campo '{field}' é obrigatório."), 400
    
    if players_collection.find_one({"email": data["email"]}):
        return jsonify(message="Um jogador com este email já existe."), 409

    data['dataCadastro'] = datetime.utcnow()

    try:
        result = players_collection.insert_one(data)
        return jsonify(message="Jogador criado com sucesso!", playerId=str(result.inserted_id)), 201
    except Exception as e:
        print(f"Erro ao criar jogador: {e}")
        return jsonify(message=f"Erro ao criar jogador: {e}", status="error"), 500

@app.route('/players', methods=['GET'])
def get_all_players():
    email = request.args.get('email')
    
    try:
        players_list = []
        query = {}
        if email:
            query["email"] = email
        
        for player in players_collection.find(query):
            player['_id'] = str(player['_id'])
            players_list.append(player)
        return jsonify(players_list), 200
    except Exception as e:
        print(f"Erro ao buscar jogadores: {e}")
        return jsonify(message=f"Erro ao buscar jogadores: {e}", status="error"), 500

@app.route('/players/<string:player_id>', methods=['GET'])
def get_player_by_id(player_id):
    try:
        player = players_collection.find_one({"_id": ObjectId(player_id)})
        if player:
            player['_id'] = str(player['_id'])
            return jsonify(player), 200
        else:
            return jsonify(message="Jogador não encontrado."), 404
    except Exception as e:
        print(f"Erro ao buscar jogador: {e}")
        return jsonify(message=f"Erro ao buscar jogador: {e}", status="error"), 500

@app.route('/players/<string:player_id>', methods=['PUT'])
def update_player(player_id):
    data = request.get_json()
    if not data:
        return jsonify(message="Dados inválidos ou ausentes para atualização"), 400

    try:
        obj_id = ObjectId(player_id)
    except Exception:
        return jsonify(message="ID de jogador inválido."), 400

    update_data = {k: v for k, v in data.items() if k not in ['_id', 'dataCadastro']}

    try:
        result = players_collection.update_one({"_id": obj_id}, {"$set": update_data})

        if result.matched_count == 0:
            return jsonify(message="Jogador não encontrado para atualização."), 404
        if result.modified_count == 0:
            return jsonify(message="Nenhuma alteração detectada ou jogador já atualizado."), 200
            
        updated_player = players_collection.find_one({"_id": obj_id})
        updated_player['_id'] = str(updated_player['_id'])
            
        return jsonify(message="Jogador atualizado com sucesso!", player=updated_player), 200
    except Exception as e:
        print(f"Erro ao atualizar jogador: {e}")
        return jsonify(message=f"Erro ao atualizar jogador: {e}", status="error"), 500

@app.route('/players/<string:player_id>', methods=['DELETE'])
def delete_player(player_id):
    try:
        obj_id = ObjectId(player_id)
    except Exception:
        return jsonify(message="ID de jogador inválido."), 400

    try:
        result = players_collection.delete_one({"_id": obj_id})

        if result.deleted_count == 0:
            return jsonify(message="Jogador não encontrado para exclusão."), 404
            
        registrations_collection.delete_many({"jogadorId": player_id})

        return jsonify(message="Jogador excluído com sucesso!"), 200
    except Exception as e:
        print(f"Erro ao excluir jogador: {e}")
        return jsonify(message=f"Erro ao excluir jogador: {e}", status="error"), 500

@app.route('/tournaments', methods=['POST'])
def create_tournament():
    data = request.get_json()
    if not data:
        return jsonify(message="Dados inválidos ou ausentes"), 400

    required_fields = ["nome", "local", "dataInicio", "dataFim", "dataLimiteInscricao", "categorias"]
    for field in required_fields:
        if field not in data:
            return jsonify(message=f"Campo '{field}' é obrigatório."), 400

    if not isinstance(data["categorias"], list) or not isinstance(data["categorias"], list):
        return jsonify(message="Categorias devem ser uma lista não vazia."), 400
    for cat in data["categorias"]:
        if not all(k in cat for k in ["nome", "valorInscricao", "vagas"]):
            return jsonify(message="Cada categoria deve ter nome, valorInscricao e vagas."), 400
        if not isinstance(cat["valorInscricao"], (int, float)) or not isinstance(cat["vagas"], int):
            return jsonify(message="valorInscricao deve ser um número e vagas deve ser um inteiro."), 400

    data['dataCriacao'] = datetime.utcnow() 
    data['status'] = data.get('status', 'Inscrições Abertas') 

    try:
        result = tournaments_collection.insert_one(data)
        return jsonify(message="Torneio criado com sucesso!", tournamentId=str(result.inserted_id)), 201
    except Exception as e:
        print(f"Erro ao criar torneio: {e}")
        return jsonify(message=f"Erro ao criar torneio: {e}", status="error"), 500

@app.route('/tournaments', methods=['GET'])
def get_all_tournaments():
    try:
        tournaments = []
        for tournament in tournaments_collection.find():
            tournament['_id'] = str(tournament['_id'])
            tournaments.append(tournament)
        return jsonify(tournaments), 200
    except Exception as e:
        print(f"Erro ao buscar torneios: {e}")
        return jsonify(message=f"Erro ao buscar torneios: {e}", status="error"), 500

@app.route('/tournaments/<string:tournament_id>', methods=['GET'])
def get_tournament_by_id(tournament_id):
    try:
        tournament = tournaments_collection.find_one({"_id": ObjectId(tournament_id)})
        if tournament:
            tournament['_id'] = str(tournament['_id'])
            return jsonify(tournament), 200
        else:
            return jsonify(message="Torneio não encontrado."), 404
    except Exception as e:
        print(f"Erro ao buscar torneio: {e}")
        return jsonify(message=f"Erro ao buscar torneio: {e}", status="error"), 500

@app.route('/tournaments/<string:tournament_id>', methods=['PUT'])
def update_tournament(tournament_id):
    data = request.get_json()
    if not data:
        return jsonify(message="Dados inválidos ou ausentes para atualização"), 400

    try:
        obj_id = ObjectId(tournament_id)
    except Exception:
        return jsonify(message="ID de torneio inválido."), 400

    update_data = {k: v for k, v in data.items() if k not in ['_id', 'dataCriacao']}
    
    if 'categorias' in update_data:
        if not isinstance(update_data["categorias"], list) or not isinstance(update_data["categorias"], list):
            return jsonify(message="Categorias devem ser uma lista não vazia para atualização."), 400
        for cat in update_data["categorias"]:
            if not all(k in cat for k in ["nome", "valorInscricao", "vagas"]):
                return jsonify(message="Cada categoria deve ter nome, valorInscricao e vagas."), 400
            if not isinstance(cat["valorInscricao"], (int, float)) or not isinstance(cat["vagas"], int):
                return jsonify(message="valorInscricao deve ser um número e vagas deve ser um inteiro."), 400

    try:
        result = tournaments_collection.update_one({"_id": obj_id}, {"$set": update_data})

        if result.matched_count == 0:
            return jsonify(message="Torneio não encontrado para atualização."), 404
        if result.modified_count == 0:
            return jsonify(message="Nenhuma alteração detectada ou torneio já atualizado."), 200

        updated_tournament = tournaments_collection.find_one({"_id": obj_id})
        updated_tournament['_id'] = str(updated_tournament['_id'])

        return jsonify(message="Torneio atualizado com sucesso!", tournament=updated_tournament), 200
    except Exception as e:
        print(f"Erro ao atualizar torneio: {e}")
        return jsonify(message=f"Erro ao atualizar torneio: {e}", status="error"), 500

@app.route('/tournaments/<string:tournament_id>', methods=['DELETE'])
def delete_tournament(tournament_id):
    try:
        obj_id = ObjectId(tournament_id)
    except Exception:
        return jsonify(message="ID de torneio inválido."), 400

    try:
        result = tournaments_collection.delete_one({"_id": obj_id})

        if result.deleted_count == 0:
            return jsonify(message="Torneio não encontrado para exclusão."), 404
        
        registrations_collection.delete_many({"torneioId": tournament_id})

        return jsonify(message="Torneio excluído com sucesso! Inscrições relacionadas também foram removidas."), 200
    except Exception as e:
        print(f"Erro ao excluir torneio: {e}")
        return jsonify(message=f"Erro ao excluir torneio: {e}", status="error"), 500

@app.route('/registrations', methods=['POST'])
def create_registration():
    data = request.get_json()
    if not data:
        return jsonify(message="Dados inválidos ou ausentes"), 400

    required_fields = ["torneioId", "jogadorId", "categoriaInscrita"]
    for field in required_fields:
        if field not in data:
            return jsonify(message=f"Campo '{field}' é obrigatório."), 400
            
    if not all(k in data["categoriaInscrita"] for k in ["nome", "valorInscricao"]):
        return jsonify(message="categoriaInscrita deve conter nome e valorInscricao."), 400
    
    try:
        if not tournaments_collection.find_one({"_id": ObjectId(data["torneioId"])}):
            return jsonify(message="Torneio não encontrado."), 404
        if not players_collection.find_one({"_id": ObjectId(data["jogadorId"])}):
            return jsonify(message="Jogador não encontrado."), 404
    except Exception:
        return jsonify(message="IDs de Torneio ou Jogador inválidos (formato)."), 400

    existing_registration = registrations_collection.find_one({
        "torneioId": data["torneioId"],
        "jogadorId": data["jogadorId"],
        "categoriaInscrita.nome": data["categoriaInscrita"]["nome"]
    })
    if existing_registration:
        return jsonify(message="Este atleta já está inscrito nesta categoria do torneio."), 409

    data['dataInscricao'] = datetime.utcnow()
    data['statusPagamento'] = data.get('statusPagamento', 'Pendente')
    data['pixDetails'] = {} 

    try:
        result = registrations_collection.insert_one(data)
        return jsonify(message="Inscrição criada com sucesso!", registrationId=str(result.inserted_id)), 201
    except Exception as e:
        print(f"Erro ao criar inscrição: {e}")
        return jsonify(message=f"Erro ao criar inscrição: {e}", status="error"), 500

@app.route('/registrations', methods=['GET'])
def get_all_registrations():
    try:
        registrations = []
        for reg in registrations_collection.find():
            reg['_id'] = str(reg['_id'])
            registrations.append(reg)
        return jsonify(registrations), 200
    except Exception as e:
        print(f"Erro ao buscar inscrições: {e}")
        return jsonify(message=f"Erro ao buscar inscrições: {e}", status="error"), 500

@app.route('/registrations/<string:registration_id>', methods=['GET'])
def get_registration_by_id(registration_id):
    try:
        reg = registrations_collection.find_one({"_id": ObjectId(registration_id)})
        if reg:
            reg['_id'] = str(reg['_id'])
            return jsonify(reg), 200
        else:
            return jsonify(message="Inscrição não encontrada."), 404
    except Exception as e:
        print(f"Erro ao buscar inscrição: {e}")
        return jsonify(message=f"Erro ao buscar inscrição: {e}", status="error"), 500

@app.route('/registrations/<string:registration_id>', methods=['PUT'])
def update_registration(registration_id):
    data = request.get_json()
    if not data:
        return jsonify(message="Dados inválidos ou ausentes para atualização"), 400

    try:
        obj_id = ObjectId(registration_id)
    except Exception:
        return jsonify(message="ID de inscrição inválido."), 400

    update_data = {k: v for k, v in data.items() if k not in ['_id', 'dataInscricao']}

    try:
        result = registrations_collection.update_one({"_id": obj_id}, {"$set": update_data})

        if result.matched_count == 0:
            return jsonify(message="Inscrição não encontrada para atualização."), 404
        if result.modified_count == 0:
            return jsonify(message="Nenhuma alteração detectada ou inscrição já atualizada."), 200

        updated_reg = registrations_collection.find_one({"_id": obj_id})
        updated_reg['_id'] = str(updated_reg['_id'])

        return jsonify(message="Inscrição atualizada com sucesso!", registration=updated_reg), 200
    except Exception as e:
        print(f"Erro ao atualizar inscrição: {e}")
        return jsonify(message=f"Erro ao atualizar inscrição: {e}", status="error"), 500

@app.route('/registrations/<string:registration_id>', methods=['DELETE'])
def delete_registration(registration_id):
    try:
        obj_id = ObjectId(registration_id)
    except Exception:
        return jsonify(message="ID de inscrição inválido."), 400

    try:
        result = registrations_collection.delete_one({"_id": obj_id})

        if result.deleted_count == 0:
            return jsonify(message="Inscrição não encontrada para exclusão."), 404

        return jsonify(message="Inscrição excluída com sucesso!"), 200
    except Exception as e:
        print(f"Erro ao excluir inscrição: {e}")
        return jsonify(message=f"Erro ao excluir inscrição: {e}", status="error"), 500

@app.route('/tournaments/<string:torneio_id>/registrations', methods=['GET'])
def get_registrations_by_tournament(torneio_id):
    try:
        registrations = []
        for reg in registrations_collection.find({"torneioId": torneio_id}):
            reg['_id'] = str(reg['_id'])
            registrations.append(reg)
        return jsonify(registrations), 200
    except Exception as e:
        print(f"Erro ao buscar inscrições por torneio: {e}")
        return jsonify(message=f"Erro ao buscar inscrições por torneio: {e}", status="error"), 500

@app.route('/players/<string:jogador_id>/registrations', methods=['GET'])
def get_registrations_by_player(jogador_id):
    try:
        registrations = []
        for reg in registrations_collection.find({"jogadorId": jogador_id}):
            reg['_id'] = str(reg['_id'])
            registrations.append(reg)
        return jsonify(registrations), 200
    except Exception as e:
        print(f"Erro ao buscar inscrições por jogador: {e}")
        return jsonify(message=f"Erro ao buscar inscrições por jogador: {e}", status="error"), 500

# --- Rota para Gerar PIX para uma Inscrição Específica (SIMULADO) ---
@app.route('/registrations/<string:registration_id>/generate_pix', methods=['POST'])
def generate_pix_for_registration(registration_id):
    try:
        obj_id = ObjectId(registration_id)
    except Exception:
        return jsonify(message="ID de inscrição inválido."), 400
    
    registration = registrations_collection.find_one({"_id": obj_id})
    if not registration:
        return jsonify(message="Inscrição não encontrada."), 404
    
    valor_inscricao = registration['categoriaInscrita']['valorInscricao']
    
    # === GERAÇÃO DO PIX COPIA E COLA (BR CODE) USANDO UM TEMPLATE VÁLIDO DE TESTE ===
    # Este é um PIX de teste que aponta para um recebedor genérico do Mercado Pago (OSASCO).
    # O valor é fixo em R$ 1.00 NESTA STRING DE TESTE.
    # O QR Code gerado a partir desta string será LIDO pelo aplicativo do banco.
    # A sua chave, nome e valor da inscrição serão exibidos TEXTUALMENTE abaixo do QR.
    
    # String PIX de teste (gerada de um ambiente real de simulação do Mercado Pago)
    pix_copia_e_cola_data = f"00020126580014BR.GOV.BCB.PIX0136d2466986-7a7d-417c-95ea-65f58535031b52040000530398654051.005802BR5913MERCADO PAGO6009OSASCO62070503***6304ED25"
    
    # Geração do QR Code como imagem
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(pix_copia_e_cola_data) # O QR Code é gerado a partir da string de teste acima
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    # Converte a imagem do QR Code para formato Base64
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    qr_code_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    
    # === DETALHES PIX PARA O FRONTEND (ESTES SÃO OS QUE APARECERÃO NO TEXTO DA PÁGINA) ===
    # Estes dados são os seus dados PIX REAIS que você me passou.
    # Eles são exibidos textualmente para o usuário, ao lado do QR Code de teste.
    pix_details = {
        "pixCopiaECola": pix_copia_e_cola_data, # A string completa do PIX de teste
        "qrCodeBase64": qr_code_base64,         # A imagem do QR Code em Base64
        "valor": valor_inscricao,               # <--- VALOR REAL DA INSCRIÇÃO
        "chaveRecebedor": "jlteambt@gmail.com", # <--- SUA CHAVE PIX REAL
        "nomeRecebedor": "ASSESP",              # <--- SEU NOME REAL
        "cidadeRecebedor": "Santos"             # <--- SUA CIDADE
    }
    
    result = registrations_collection.update_one(
        {"_id": obj_id},
        {"$set": {"pixDetails": pix_details}}
    )

    if result.matched_count == 0:
        return jsonify(message="Inscrição não encontrada para gerar PIX."), 404
    
    return jsonify(
        message="PIX gerado com sucesso!", 
        pixDetails=pix_details
    ), 200

# --- Rota para Atualizar Status de Pagamento Manualmente ---
@app.route('/registrations/<string:registration_id>/status', methods=['PUT'])
def update_registration_status(registration_id):
    data = request.get_json()
    new_status = data.get('statusPagamento')
    
    if not new_status or new_status not in ['Pendente', 'Confirmado', 'Cancelado']:
        return jsonify(message="Status de pagamento inválido."), 400
    
    try:
        obj_id = ObjectId(registration_id)
    except Exception:
        return jsonify(message="ID de inscrição inválido."), 400

    try:
        result = registrations_collection.update_one(
            {"_id": obj_id},
            {"$set": {"statusPagamento": new_status}}
        )

        if result.matched_count == 0:
            return jsonify(message="Inscrição não encontrada para atualizar status."), 404
        if result.modified_count == 0:
            return jsonify(message="Nenhuma alteração detectada ou status já atualizado."), 200

        updated_reg = registrations_collection.find_one({"_id": obj_id})
        updated_reg['_id'] = str(updated_reg['_id'])

        return jsonify(message="Status de pagamento atualizado com sucesso!", registration=updated_reg), 200
    except Exception as e:
        print(f"Erro ao atualizar status de pagamento: {e}")
        return jsonify(message=f"Erro ao atualizar status de pagamento: {e}", status="error"), 500


# --- Rotas para Geração e Visualização de Confrontos/Chaves ---
@app.route('/tournaments/<string:torneio_id>/<string:categoria_nome>/generate_draw', methods=['POST'])
def generate_draw(torneio_id, categoria_nome):
    try:
        tournament = tournaments_collection.find_one({"_id": ObjectId(torneio_id)})
        if not tournament:
            return jsonify(message="Torneio não encontrado."), 404

        category_details = None
        for cat in tournament.get('categorias', []):
            if cat['nome'] == categoria_nome:
                category_details = cat
                break
        if not category_details:
            return jsonify(message=f"Categoria '{categoria_nome}' não encontrada no torneio."), 404

        registered_players_ids = registrations_collection.find({
            "torneioId": torneio_id,
            "categoriaInscrita.nome": categoria_nome,
            "statusPagamento": "Confirmado" 
        }, {"jogadorId": 1, "_id": 0})

        players_for_draw_raw = [reg["jogadorId"] for reg in registered_players_ids]
        
        players_details = []
        for p_id in players_for_draw_raw:
            player_info = players_collection.find_one({"_id": ObjectId(p_id)})
            if player_info:
                players_details.append({"id": str(player_info["_id"]), "nome": player_info["nomeCompleto"]})
        
        import random
        random.shuffle(players_details)

        num_players = len(players_details)
        
        if num_players == 0:
            return jsonify(message="Não há jogadores inscritos e confirmados para gerar a chave para esta categoria."), 400
        
        import math
        next_power_of_2 = 2**math.ceil(math.log2(num_players))
        num_byes = next_power_of_2 - num_players

        draw_size = next_power_of_2
        
        players_in_draw = list(players_details)

        for _ in range(num_byes):
            players_in_draw.append({"id": "BYE", "nome": "BYE"})
        
        random.shuffle(players_in_draw)
        
        if len(players_in_draw) < 2 and num_byes == 0:
            return jsonify(message="Número insuficiente de jogadores para formar partidas (mínimo 2)."), 400
        
        matches_collection.delete_many({
            "torneioId": torneio_id,
            "categoriaNome": categoria_nome
        })

        match_counter = 0
        first_round_matches_ids = []

        for i in range(0, len(players_in_draw), 2):
            player1 = players_in_draw[i]
            player2 = players_in_draw[i+1]
            match_counter += 1

            if player1["id"] == "BYE" or player2["id"] == "BYE":
                vencedor_id = player1["id"] if player2["id"] == "BYE" else player2["id"]
                match_data = {
                    "torneioId": torneio_id,
                    "categoriaNome": categoria_nome,
                    "rodada": f"Primeira Rodada ({draw_size} Participantes)",
                    "partidaNumero": match_counter,
                    "jogador1": player1,
                    "jogador2": player2,
                    "vencedorId": vencedor_id,
                    "placar": "BYE",
                    "dataHora": None,
                    "quadra": None,
                    "status": "Finalizada"
                }
            else:
                match_data = {
                    "torneioId": torneio_id,
                    "categoriaNome": categoria_nome,
                    "rodada": f"Primeira Rodada ({draw_size} Participantes)",
                    "partidaNumero": match_counter,
                    "jogador1": player1,
                    "jogador2": player2,
                    "vencedorId": None,
                    "placar": None,
                    "dataHora": None,
                    "quadra": None,
                    "status": "Agendada"
                }
            
            result = matches_collection.insert_one(match_data)
            first_round_matches_ids.append(str(result.inserted_id))

        return jsonify(
            message=f"Chave de eliminação simples gerada com sucesso para a categoria '{categoria_nome}'.",
            totalPlayers=num_players,
            byesAssigned=num_byes,
            drawSize=draw_size,
            firstRoundMatchesCount=len(first_round_matches_ids),
            firstRoundMatchIds=first_round_matches_ids
        ), 201

    except Exception as e:
        print(f"Erro ao gerar chave: {e}")
        return jsonify(message=f"Erro ao gerar chave: {e}", status="error"), 500

@app.route('/tournaments/<string:torneio_id>/<string:categoria_nome>/matches', methods=['GET'])
def get_matches_for_category(torneio_id, categoria_nome):
    try:
        matches = []
        for match in matches_collection.find({
            "torneioId": torneio_id,
            "categoriaNome": categoria_nome
        }).sort([("rodada", 1), ("partidaNumero", 1)]):
            match['_id'] = str(match['_id'])
            matches.append(match)
        return jsonify(matches), 200
    except Exception as e:
        print(f"Erro ao buscar partidas: {e}")
        return jsonify(message=f"Erro ao buscar partidas: {e}", status="error"), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)