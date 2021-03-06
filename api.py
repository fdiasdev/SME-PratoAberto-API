# coding: utf-8
# -*- coding: utf-8 -*-
import json
import os

from flask import Flask, request, jsonify, make_response
from pymongo import MongoClient
from bson import json_util
from users import users_api


API_KEY = os.environ.get('API_KEY')
API_MONGO_URI = 'mongodb://{}'.format(os.environ.get('API_MONGO_URI'))

client = MongoClient(API_MONGO_URI)
db = client['pratoaberto']


def create_app():

    app = Flask(__name__)
    app.register_blueprint(users_api)

    with open('de_para.json', 'r') as f:
        conf = json.load(f)
        refeicoes = conf['refeicoes']
        idades = conf['idades']
        idades_reversed = {v: k for k, v in conf['idades'].items()}

    def copy_for(query, req, key):
        if req.args.get(key):
            query[key] = req.args[key]
        return query

    def dic_to_list(data, dic, key):
        if key in data:
            data[key] = [dic.get(x, x) for x in data[key]]

    def fill_data_query(query, data, request):
        if data:
            query['data'] = str(data)
        else:
            data = {}
            data = update_data(data, request)
            if data:
                query['data'] = data
        return query

    def choose_escola_atributos(escola):
            escola = dic_to_list(escola, idades, 'idades')
            escola = dic_to_list(escola, refeicoes, 'refeicoes')

            if escola:
                response = app.response_class(
                    response=json_util.dumps(escola),
                    status=200,
                    mimetype='application/json'
                )
            else:
                response = app.response_class(
                    response=json_util.dumps({'erro': 'Escola inexistente'}),
                    status=404,
                    mimetype='application/json'
                )
            return response

    @app.route('/escolas')
    def get_lista_escolas():
        query = {'status': 'ativo'}
        fields = {'_id': True, 'nome': True,'status':True}
        try:
            limit = int(request.args.get('limit', 5))
            # busca por nome
            nome = request.args['nome']
            query = { '$text': { '$search': nome },'status': 'ativo'}
            cursor = db.escolas.find(query, fields).limit(limit)
        except KeyError:
            fields.update({k: True for k in ['endereco',
                                             'bairro', 'lat', 'lon']})
            cursor = db.escolas.find(query, fields)
        
        response = list(cursor)
        return jsonify(response), 200

    @app.route('/escola/<int:id_escola>')
    def get_detalhe_escola(id_escola):
        query = {'_id': id_escola, 'status': 'ativo'}
        fields = {'_id': False, 'status': False}
        escola = db.escolas.find_one(query, fields)
        if 'idades' in escola:
            escola['idades'] = [idades.get(x, x) for x in escola['idades']]
        if 'refeicoes' in escola:
            escola['refeicoes'] = [refeicoes.get(x, x) for x in escola['refeicoes']]
        if escola:
            response = jsonify(escola), 200
        else:
            response = jsonify({'erro': 'Escola inexistente'}), 404
        return response

    @app.route('/escola/<int:id_escola>/cardapios')
    @app.route('/escola/<int:id_escola>/cardapios/<data>')
    def get_cardapio_escola(id_escola, data=None):
        escola = db.escolas.find_one({'_id': id_escola}, {'_id': False})
        if escola:
            query = {
                'status': 'PUBLICADO',
                'agrupamento': str(escola['agrupamento']),
                'tipo_atendimento': escola['tipo_atendimento'],
                'tipo_unidade': escola['tipo_unidade']
            }

            if request.args.get('idade'):
                query['idade'] = idades_reversed.get(request.args['idade'])

            query = fill_data_query(query, data, request)

            fields = {
                '_id': False,
                'status': False,
                'cardapio_original': False
            }

            _cardapios = []
            cardapios = db.cardapios.find(query, fields).sort([('data', -1)]).limit(15)
            for c in cardapios:
                c['idade'] = idades[c['idade']]
                c['cardapio'] = {refeicoes[k]: v for k, v in c['cardapio'].items()}
                _cardapios.append(c)
            cardapios = _cardapios

            response = jsonify(cardapios), 200
        else:
            response = jsonify({'erro': 'Escola inexistente'}), 404

        return response

    def cardapios_from_db(page, limit, cardapios):
        if page and limit:
            cardapios = cardapios.skip(limit*(page-1)).limit(limit)
        elif limit:
            cardapios = cardapios.limit(limit)
        return cardapios

    def update_data(data, request):
        if request.args.get('data_inicial'):
            data.update({'$gte': request.args['data_inicial']})
        if request.args.get('data_final'):
            data.update({'$lte': request.args['data_final']})
        return data

    def fill_cardapios_idade(dictionary, lista_cardapios, idades, refeicoes):
        for dictionary in lista_cardapios:
            dictionary['idade'] = idades[c['idade']]
            dictionary['cardapio'] = {
                                     refeicoes[k]: v for k,
                                     v in c['cardapio'].items()}
        return dictionary

    @app.route('/cardapios')
    @app.route('/cardapios/<data>')
    def get_cardapios(data=None):
        query = {
            'status': 'PUBLICADO'
        }

        query = copy_for(query, request, 'agrupamento')
        query = copy_for(query, request, 'tipo_atendimento')
        query = copy_for(query, request, 'tipo_unidade')

        if request.args.get('idade'):
            query['idade'] = idades_reversed.get(request.args['idade'])

        query = fill_data_query(query, data, request)
        limit = int(request.args.get('limit', 0))
        page = int(request.args.get('page', 0))
        fields = {
            '_id': False,
            'status': False,
            'cardapio_original': False,
        }
        cardapios = db.cardapios.find(query, fields).sort([('data', -1)])
        cardapios = cardapios_from_db(page, limit, cardapios)
        _cardapios = []
        cardapio_ordenado = []
        definicao_ordenacao = ['A - 0 A 1 MES', 'B - 1 A 3 MESES',
                               'C - 4 A 5 MESES', 'D - 0 A 5 MESES',
                               'D - 6 A 7 MESES',
                               'D - 6 MESES', 'D - 7 MESES',
                               'E - 8 A 11 MESES', 'X - 1A -1A E 11MES',
                               'F - 2 A 3 ANOS', 'G - 4 A 6 ANOS',
                               'I - 2 A 6 ANOS', 'W - EMEI DA CEMEI',
                               'N - 6 A 7 MESES PARCIAL',
                               'O - 8 A 11 MESES PARCIAL',
                               'Y - 1A -1A E 11MES PARCIAL',
                               'P - 2 A 3 ANOS PARCIAL',
                               'Q - 4 A 6 ANOS PARCIAL',
                               'H - ADULTO', 'Z - UNIDADES SEM FAIXA',
                               'S - FILHOS PRO JOVEM', 'V - PROFESSOR',
                               'U - PROFESSOR JANTAR CEI']

        for c in cardapios:
            _cardapios.append(c)

        for i in definicao_ordenacao:
            for c in _cardapios:
                if i == c['idade']:
                    cardapio_ordenado.append(c)
                    continue

        c = fill_cardapios_idade(c, cardapio_ordenado, idades, refeicoes)

        for c in cardapio_ordenado:
            for x in refeicoes:
                if refeicoes[x] in c['cardapio']:
                    c['cardapio'][refeicoes[x]] = sorted(c['cardapio']
                                                          [refeicoes[x]])

        response = jsonify(cardapio_ordenado), 200

        return response

    @app.route('/editor/cardapios', methods=['GET', 'POST'])
    def get_cardapios_editor():
        key = request.headers.get('key')
        if key != API_KEY:
            return ('', 401)
        if request.method == 'GET':
            query = {}

            if request.args.get('status'):
                query['status'] = {'$in': request.args.getlist('status')}
            else:
                query['status'] = 'PUBLICADO'

            query = copy_for(query, request, 'agrupamento')
            query = copy_for(query, request, 'tipo_atendimento')
            query = copy_for(query, request, 'tipo_unidade')
            query = copy_for(query, request, 'idade')

            data = {}
            data = update_data(data, request)
            if data:
                query['data'] = data

            limit = int(request.args.get('limit', 0))
            page = int(request.args.get('page', 0))
            cardapios = db.cardapios.find(query).sort([('data', -1)])
            if page and limit:
                cardapios = cardapios.skip(limit*(page-1)).limit(limit)
            elif limit:
                cardapios = cardapios.limit(limit)

            return jsonify(cardapios), 200

        elif request.method == 'POST':
            bulk = db.cardapios.initialize_ordered_bulk_op()
            for item in json_util.loads(request.data.decode("utf-8")):
                try:
                    _id = item['_id']
                    bulk.find({'_id': _id}).update({'$set': item})
                except:
                    bulk.insert(item)
            bulk.execute()
            return ('', 200)

    @app.route('/editor/escolas')
    def get_escolas_editor():
        key = request.headers.get('key')
        if key != API_KEY:
            return ('', 401)

        query = {'status': 'ativo'}
        cursor = db.escolas.find(query)
        response = list(cursor)
        return jsonify(response), 200

    @app.route('/editor/escola/<int:id_escola>', methods=['POST'])
    def edit_escola(id_escola):
        key = request.headers.get('key')
        if key != API_KEY:
            return ('', 401)

        try:
            payload = json_util.loads(request.data)
        except:
            return jsonify({'erro': 'Dados POST não é um JSON válido'}), 500

        db.escolas.update_one(
            {'_id': id_escola},
            {'$set': payload},
            upsert=False)
        return ('', 200)

    @app.route('/status')
    def get_api_status():
        return app.response_class(
            response=json_util.dumps({'status': 'ativo'}),
            status=200,
            mimetype='application/json'
        )

    return app

if __name__ == 'api': #this is not main
    app = create_app()
    app.run(host='0.0.0.0', debug=True)

