from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.routes import current_user
from app.config import settings
from app.database import Base, get_db, set_session_factory_override
from app.main import app
from app.models import Preference, ReportingBias, User


def _seed_default_user(session_factory) -> None:
    db = session_factory()
    try:
        user = db.query(User).filter_by(line_user_id="test-user").first()
        if user:
            return
        user = User(line_user_id="test-user", display_name="Test User", daily_calorie_target=1800)
        db.add(user)
        db.flush()
        db.add(Preference(user_id=user.id))
        db.add(ReportingBias(user_id=user.id))
        db.commit()
    finally:
        db.close()


@pytest.fixture
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    _seed_default_user(TestingSessionLocal)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    def override_current_user():
        db = TestingSessionLocal()
        try:
            user = db.query(User).filter_by(line_user_id="test-user").first()
            if not user:
                _seed_default_user(TestingSessionLocal)
                user = db.query(User).filter_by(line_user_id="test-user").one()
            return user
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[current_user] = override_current_user
    app.state._testing_session_factory = TestingSessionLocal
    set_session_factory_override(TestingSessionLocal)
    original_passcode = settings.observability_admin_passcode
    original_ttl = settings.observability_admin_session_ttl_hours
    original_ai_builder_token = settings.ai_builder_token
    settings.observability_admin_passcode = "test-admin-passcode"
    settings.observability_admin_session_ttl_hours = 12
    settings.ai_builder_token = None

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    set_session_factory_override(None)
    settings.observability_admin_passcode = original_passcode
    settings.observability_admin_session_ttl_hours = original_ttl
    settings.ai_builder_token = original_ai_builder_token
    if hasattr(app.state, "_testing_session_factory"):
        delattr(app.state, "_testing_session_factory")
    engine.dispose()


@pytest.fixture
def db_session_factory(client):
    return app.state._testing_session_factory


@pytest.fixture
def admin_headers(client):
    response = client.post(
        "/api/admin/login",
        json={"passcode": "test-admin-passcode", "label": "pytest-admin"},
    )
    assert response.status_code == 200
    token = response.json()["payload"]["session"]["token"]
    return {"X-Admin-Session": token}
