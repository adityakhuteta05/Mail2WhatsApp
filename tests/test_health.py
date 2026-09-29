def test_health_check_endpoint(client, sample_account):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"]["status"] == "ok"
    assert data["active_gmail_accounts"] == 1
    assert "uptime_seconds" in data
    assert data["version"] == "1.0.0"


def test_readiness_probe(client):
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"ready": True}


def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Mail2WhatsApp"
    assert data["status"] == "online"
