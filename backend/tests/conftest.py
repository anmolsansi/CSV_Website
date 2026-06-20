import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("TEST_AUTH", "true")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("FRONTEND_URL", "http://localhost:5173")
os.environ.setdefault("ENVIRONMENT", "test")

from app.database import Base, get_db
from app.main import app


@pytest.fixture(scope="session")
def engine():
    test_db_url = os.environ.get("DATABASE_URL", "sqlite:///./test.db")
    eng = create_engine(test_db_url, connect_args={"check_same_thread": False} if "sqlite" in test_db_url else {})
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)


@pytest.fixture()
def db_session(engine):
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    yield session
    session.rollback()
    session.close()


@pytest.fixture()
def client(engine):
    TestSession = sessionmaker(bind=engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_client(client):
    resp = client.post("/auth/dev-login", json={"email": "test@jobgrid.dev"})
    assert resp.status_code == 200
    return client
