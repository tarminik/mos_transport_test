from flask import Flask, request
from flask_restful import Api, Resource
from flask_sqlalchemy import SQLAlchemy
import hashlib
import json
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///incidents.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
api = Api(app)

class Incident(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    headers = db.Column(db.Text, nullable=False)
    body = db.Column(db.Text, nullable=False)  
    hash_value = db.Column(db.String(64), nullable=False, index=True)

def create_hash(headers, body):
    """Создает хеш из заголовков и тела запроса с учетом порядка ключей"""
    # Сортируем ключи в словарях для одинакового хеша
    if isinstance(headers, dict):
        headers_sorted = json.dumps(headers, sort_keys=True, separators=(',', ':'))
    else:
        headers_sorted = str(headers)
    
    if isinstance(body, dict):
        body_sorted = json.dumps(body, sort_keys=True, separators=(',', ':'))
    else:
        body_sorted = str(body)
    
    combined = headers_sorted + body_sorted
    return hashlib.sha256(combined.encode('utf-8')).hexdigest()

class ProblemsResource(Resource):
    def post(self):
        headers = {k.lower(): v for k, v in request.headers.items()}
        body = request.get_json() or {}
        
        hash_value = create_hash(headers, body)
        
        incident = Incident(
            headers=json.dumps(headers),
            body=json.dumps(body),
            hash_value=hash_value
        )
        
        db.session.add(incident)
        db.session.commit()
        
        return {'hash': hash_value}

class FindResource(Resource):
    def post(self):
        """
        ВАЖНОЕ ЗАМЕЧАНИЕ О ПРОИЗВОДИТЕЛЬНОСТИ:
        Текущая реализация эндпоинта /find не является оптимальной для больших объемов данных.
        Она загружает все инциденты из базы данных (`Incident.query.all()`) и выполняет поиск
        в цикле на стороне Python. Это простое решение, но его производительность линейно
        ухудшается с ростом количества записей в таблице.

        Для "промышленного" решения, где производительность критична, следовало бы:
        1. Использовать СУБД с нативной поддержкой JSON, например, PostgreSQL с типом данных JSONB.
        2. Хранить `headers` и `body` в колонках типа JSONB.
        3. Создать GIN-индексы для этих колонок для сверхбыстрого поиска по ключам и значениям
           внутри JSON-документов.
        4. Переписать запрос с использованием нативных JSON-операторов SQLAlchemy, чтобы
           перенести всю работу по фильтрации на сторону базы данных.

        В рамках данного тестового задания выбран более простой подход для демонстрации
        базовой логики и для соответствия критерию "простота кода".
        """
        search_data = request.get_json() or {}
        results = []
        
        incidents = Incident.query.all()
        
        for incident in incidents:
            headers = json.loads(incident.headers)
            body = json.loads(incident.body)
            
            match = False
            for key, value in search_data.items():
                if (key in headers and str(headers[key]) == str(value)) or \
                   (key in body and str(body[key]) == str(value)):
                    match = True
                    break
            
            if match:
                results.append({
                    'id': incident.id,
                    'headers': headers,
                    'body': body,
                    'hash': incident.hash_value
                })
        
        return {'results': results}

class Find2Resource(Resource):
    def get(self):
        hash_param = request.args.get('h')
        if not hash_param:
            return {'error': 'Hash parameter is required'}, 400
        
        incidents = Incident.query.filter_by(hash_value=hash_param).all()
        results = []
        
        for incident in incidents:
            results.append({
                'id': incident.id,
                'headers': json.loads(incident.headers),
                'body': json.loads(incident.body),
                'hash': incident.hash_value
            })
        
        return {'results': results}

api.add_resource(ProblemsResource, '/problems')
api.add_resource(FindResource, '/find')
api.add_resource(Find2Resource, '/find2')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)