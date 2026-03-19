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
from app.database import Base, get_db
from app.main import app
from app.models import Preference, ReportingBias, User


@pytest.fixture
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)

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
                user = User(line_user_id="test-user", display_name="Test User", daily_calorie_target=1800)
                db.add(user)
                db.flush()
                db.add(Preference(user_id=user.id))
                db.add(ReportingBias(user_id=user.id))
                db.commit()
                db.refresh(user)
            return user
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[current_user] = override_current_user

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
