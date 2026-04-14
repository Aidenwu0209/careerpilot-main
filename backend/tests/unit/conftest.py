"""Unit test fixtures — override DB path to avoid locking the main test DB."""
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base

_UNIT_TEST_DB = Path(tempfile.gettempdir()) / "careerpilot_unit_test.db"

os.environ.setdefault("DATABASE_URL", f"sqlite+pysqlite:///{_UNIT_TEST_DB}")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("OCR_PROVIDER", "mock")
os.environ.setdefault("RAGFLOW_PROVIDER", "mock")
os.environ.setdefault("GRAPH_PROVIDER", "mock")
os.environ.setdefault("STORAGE_PROVIDER", "local")

_unit_engine = create_engine(
    os.environ["DATABASE_URL"], connect_args={"check_same_thread": False}, echo=False
)
_UnitSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_unit_engine)

# Patch the global engine/SessionLocal used by app.main.lifespan
import app.db.session as _db_mod
_db_mod.engine = _unit_engine
_db_mod.SessionLocal = _UnitSessionLocal

from app.main import create_app  # noqa: E402


@pytest.fixture(autouse=True)
def _prepare_unit_db():
    """Create fresh DB tables before each test and clean up after."""
    _unit_engine.dispose()
    try:
        if _UNIT_TEST_DB.exists():
            _UNIT_TEST_DB.unlink()
    except PermissionError:
        pass
    Base.metadata.create_all(bind=_unit_engine)
    yield
    try:
        _UnitSessionLocal.close_all_sessions()
    except Exception:
        pass
    _unit_engine.dispose()
    try:
        if _UNIT_TEST_DB.exists():
            _UNIT_TEST_DB.unlink()
    except PermissionError:
        pass


@pytest.fixture()
def client(_prepare_unit_db):
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db_session(_prepare_unit_db):
    """Provide a DB session after running app lifespan (which seeds demo data)."""
    app = create_app()
    with TestClient(app):
        session = _UnitSessionLocal()
        try:
            yield session
        finally:
            session.close()
