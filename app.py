from flask import Flask, request
from flask_restful import Api, Resource
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_, func
from sqlalchemy.dialects.postgresql import JSONB
import hashlib
import json
import os

app = Flask(__name__)
# Определяем, используется ли PostgreSQL, по наличию 'postgresql' в URI
IS_POSTGRES = 'postgresql' in os.getenv('DATABASE_URL', '')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///incidents.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
api = Api(app)

# Определяем тип данных для JSON в зависимости от окружения.
# Для тестов (SQLite) используем стандартный JSON, для прода (PostgreSQL) - эффективный JSONB.
JsonType = JSONB if IS_POSTGRES else db.JSON

class Incident(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    headers = db.Column(JsonType, nullable=False)
    body = db.Column(JsonType, nullable=False)  
    hash_value = db.Column(db.String(64), nullable=False, index=True)

def create_hash(headers, body):
    """Создает хеш из заголовков и тела запроса с учетом порядка ключей"""
    headers_sorted = json.dumps(headers, sort_keys=True, separators=(',', ':'))
    body_sorted = json.dumps(body, sort_keys=True, separators=(',', ':'))
    
    combined = headers_sorted + body_sorted
    return hashlib.sha256(combined.encode('utf-8')).hexdigest()

class ProblemsResource(Resource):
    def post(self):
        headers = {k.lower(): v for k, v in request.headers.items()}
        body = request.get_json() or {}
        
        hash_value = create_hash(headers, body)
        
        incident = Incident(
            headers=headers,
            body=body,
            hash_value=hash_value
        )
        
        db.session.add(incident)
        db.session.commit()
        
        return {'hash': hash_value}

class FindResource(Resource):
    def post(self):
        search_data = request.get_json() or {}
        if not search_data:
            return {'results': []}

        filters = []
        for key, value in search_data.items():
            str_value = str(value)
            if IS_POSTGRES:
                # Используем .astext для PostgreSQL
                filters.append(Incident.body[key].astext == str_value)
                filters.append(Incident.headers[key].astext == str_value)
            else:
                # Используем json_extract и CAST для SQLite
                filters.append(func.cast(func.json_extract(Incident.body, f'$.{key}'), db.Text) == str_value)
                filters.append(func.cast(func.json_extract(Incident.headers, f'$.{key}'), db.Text) == str_value)

        incidents = Incident.query.filter(or_(*filters)).all()
        
        results = [
            {
                'id': incident.id,
                'headers': incident.headers,
                'body': incident.body,
                'hash': incident.hash_value
            } for incident in incidents
        ]
        
        return {'results': results}

class Find2Resource(Resource):
    def get(self):
        hash_param = request.args.get('h')
        if not hash_param:
            return {'error': 'Hash parameter is required'}, 400
        
        incidents = Incident.query.filter_by(hash_value=hash_param).all()
        
        results = [
            {
                'id': incident.id,
                'headers': incident.headers,
                'body': incident.body,
                'hash': incident.hash_value
            } for incident in incidents
        ]
        
        return {'results': results}

api.add_resource(ProblemsResource, '/problems')
api.add_resource(FindResource, '/find')
api.add_resource(Find2Resource, '/find2')

if __name__ == '__main__':
    # ВАЖНО: db.create_all() нужно вызывать внутри app_context,
    # чтобы он имел доступ к конфигурации приложения.
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)
