"""Functional tests for GET /health (requires running PostgreSQL)."""


def test_health_returns_200(test_client):
    # Given: the FastAPI app is running (via TestClient)
    # When: GET /health is called
    response = test_client.get("/health")

    # Then: 200 OK
    assert response.status_code == 200


def test_health_returns_healthy_status(test_client):
    # Given / When
    response = test_client.get("/health")
    data = response.json()

    # Then: status is "healthy"
    assert data["status"] == "healthy"


def test_health_includes_environment(test_client):
    # Given / When
    response = test_client.get("/health")
    data = response.json()

    # Then: environment field is present
    assert "environment" in data
    assert isinstance(data["environment"], str)


def test_health_includes_database_field(test_client):
    # Given / When
    response = test_client.get("/health")
    data = response.json()

    # Then: database connectivity field is present
    assert "database" in data
    assert data["database"] in ("connected", "unreachable")
