import pytest
import json
from app import app, db, Incident, create_hash

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    client = app.test_client()

    with app.app_context():
        db.create_all()
        yield client
        db.drop_all()

def test_problems_endpoint(client):
    """
    Тестирование ручки /problems
    Проверяет:
    - Создание записи в БД
    - Корректность возвращаемого хеша
    - Правильность сохранения данных
    """
    headers = {'X-Test-Header': 'TestValue'}
    body = {'key': 'value', 'another_key': 123}

    response = client.post('/problems', headers=headers, json=body)

    assert response.status_code == 200
    response_data = response.get_json()
    assert 'hash' in response_data

    with app.app_context():
        incident = Incident.query.one()
        assert incident is not None
        
        saved_headers = json.loads(incident.headers)
        assert saved_headers['x-test-header'] == 'TestValue'
        
        assert json.loads(incident.body) == body
        assert response_data['hash'] == incident.hash_value


def test_hash_consistency_with_different_key_order(client):
    """
    Тестирование консистентности хеша при разном порядке ключей в JSON.
    Это проверка "задачи со звездочкой".
    """
    headers1 = {'q': 1, 't': 15}
    body1 = {'hello': 'world', 'z': '6.456'}

    headers2 = {'t': 15, 'q': 1}
    body2 = {'z': '6.456', 'hello': 'world'}

    hash1 = create_hash(headers1, body1)
    hash2 = create_hash(headers2, body2)

    assert hash1 == hash2

    # Также проверим через реальный эндпоинт
    response1 = client.post('/problems', headers=headers1, json=body1)
    response2 = client.post('/problems', headers=headers2, json=body2)

    hash_from_api1 = response1.get_json()['hash']
    hash_from_api2 = response2.get_json()['hash']
    
    assert hash_from_api1 == hash_from_api2

def test_find2_endpoint(client):
    """Тестирование ручки /find2 (поиск по хешу)."""
    headers = {'X-Custom-Header': 'find2_test'}
    body = {'data': 'unique_for_find2'}
    
    # Создаем инцидент
    response = client.post('/problems', headers=headers, json=body)
    assert response.status_code == 200
    hash_value = response.get_json()['hash']

    # Ищем по хешу
    response = client.get(f'/find2?h={hash_value}')
    assert response.status_code == 200
    results = response.get_json()['results']
    
    assert len(results) == 1
    found_incident = results[0]
    
    assert found_incident['hash'] == hash_value
    assert found_incident['body'] == body
    assert found_incident['headers']['x-custom-header'] == headers['X-Custom-Header']

def test_find_endpoint(client):
    """Тестирование ручки /find (поиск по ключу-значению)."""
    # Создаем несколько инцидентов для поиска
    client.post('/problems', headers={'X-Find-Test': '1'}, json={'id': 'abc', 'value': 100})
    client.post('/problems', headers={'id': 'def'}, json={'other_value': 200})
    client.post('/problems', headers={'X-Another': 'header'}, json={'id': 'ghi', 'value': 300})

    # 1. Поиск по ключу в теле
    response = client.post('/find', json={'id': 'abc'})
    results = response.get_json()['results']
    assert len(results) == 1
    assert results[0]['body']['id'] == 'abc'

    # 2. Поиск по ключу в заголовке
    response = client.post('/find', json={'id': 'def'})
    results = response.get_json()['results']
    assert len(results) == 1
    assert results[0]['headers']['id'] == 'def'

    # 3. Поиск по ключу, который есть в нескольких записях
    response = client.post('/find', json={'value': 300})
    results = response.get_json()['results']
    assert len(results) == 1
    assert results[0]['body']['value'] == 300

    # 4. Поиск по ключу, которого нет
    response = client.post('/find', json={'non_existent_key': 'value'})
    results = response.get_json()['results']
    assert len(results) == 0

    # 5. Поиск с несколькими ключами (должен работать как OR)
    response = client.post('/find', json={'id': 'abc', 'other_value': 200})
    results = response.get_json()['results']
    # Должен найти две записи
    assert len(results) == 2
    ids_found = {r['body'].get('id') or r['headers'].get('id') for r in results}
    assert ids_found == {'abc', 'def'}
