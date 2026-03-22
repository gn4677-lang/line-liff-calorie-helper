from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


MODULES_TO_RELOAD = [
    "agentic.backend.app.config",
    "agentic.backend.app.database",
    "agentic.backend.app.models",
    "agentic.backend.app.store",
    "agentic.backend.app.state",
    "agentic.backend.app.guardrails",
    "agentic.backend.app.providers",
    "agentic.backend.app.prompts",
    "agentic.backend.app.loop",
    "agentic.backend.app.runtime",
    "agentic.backend.app.identity",
    "agentic.backend.app.cohort",
    "agentic.backend.app.routes",
    "agentic.backend.app.main",
    "agentic.backend.app.worker",
]


@pytest.fixture(scope="session")
def agentic_env(tmp_path_factory: pytest.TempPathFactory):
    db_path = tmp_path_factory.mktemp("agentic-db") / "agentic-test.db"
    os.environ["AGENTIC_DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    os.environ["AGENTIC_AGENTIC_ENABLED"] = "true"
    os.environ["AGENTIC_FRONTEND_DIST_DIR"] = str((Path.cwd() / "agentic" / "frontend" / "dist").resolve())
    os.environ["AGENTIC_ROLLOUT_PCT"] = "0"
    os.environ.pop("AGENTIC_BUILDER_SPACE_TOKEN", None)
    for name in MODULES_TO_RELOAD:
        sys.modules.pop(name, None)
    importlib.invalidate_caches()
    modules = {
        "database": importlib.import_module("agentic.backend.app.database"),
        "main": importlib.import_module("agentic.backend.app.main"),
        "runtime": importlib.import_module("agentic.backend.app.runtime"),
        "worker": importlib.import_module("agentic.backend.app.worker"),
        "cohort": importlib.import_module("agentic.backend.app.cohort"),
        "contracts": importlib.import_module("agentic.backend.app.contracts"),
        "store": importlib.import_module("agentic.backend.app.store"),
        "models": importlib.import_module("backend.app.models"),
    }
    return modules


@pytest.fixture()
def client(agentic_env):
    with TestClient(agentic_env["main"].app) as test_client:
        yield test_client


@pytest.fixture()
def db_session(agentic_env):
    session_local = agentic_env["database"].SessionLocal
    with session_local() as db:
        yield db
