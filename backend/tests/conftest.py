import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.database.connection import Database
from app.database.repository import Repository
from app.main import create_app
from app.pipeline import GridPipeline


def make_settings(tmp_path, **kw) -> Settings:
    kw.setdefault("autostart_simulator", False)
    return Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", **kw)


@pytest.fixture
def settings(tmp_path):
    return make_settings(tmp_path)


@pytest.fixture
def db(settings):
    database = Database(settings.database_url)
    database.init_db()
    yield database
    database.dispose()


@pytest.fixture
def repo(db):
    return Repository(db)


@pytest.fixture
def pipeline(repo, settings):
    p = GridPipeline(repo, settings)
    p.bootstrap()
    return p


@pytest.fixture
def client(settings):
    """App with the background simulator OFF; tests advance it with pipeline.step()."""
    with TestClient(create_app(settings)) as c:
        yield c
