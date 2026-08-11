from fastapi.testclient import TestClient
from vencertia.api import app

def test_health():
    r=TestClient(app).get('/health')
    assert r.status_code==200 and r.json()['ok'] is True
