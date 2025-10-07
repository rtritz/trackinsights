import pytest
from app import create_app
from backend import db


@pytest.fixture
def app():
    app = create_app()
    app.config['TESTING'] = True
    # Use in-memory SQLite for tests
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.app_context():
        db.create_all()
        # insert a sample athlete
        from backend.queries import add_athlete
        add_athlete('Test', 'Athlete', school='UnitTest High')
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def test_home_status(client):
    rv = client.get('/')
    assert rv.status_code == 200


def test_api_athletes(client):
    rv = client.get('/api/athletes')
    assert rv.status_code == 200
    data = rv.get_json()
    assert isinstance(data, list)
    assert len(data) >= 1
