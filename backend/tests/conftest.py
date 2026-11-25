"""Fixtures compartidas (SPEC-0001 H5): settings de prueba, doble de Postgres y cliente."""

import os
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings
from app.main import crear_app
from tests.dobles.dependencias import DobleDependencia

HOSTS_LOCALES = {"localhost", "127.0.0.1", "::1"}


@pytest.fixture
def settings_prueba(tmp_path: Path) -> Settings:
    """Sin frontend: `frontend_dist` apunta a una carpeta vacía."""
    return Settings(
        _env_file=None,
        database_url=SecretStr("postgresql://prueba:clave-de-prueba@prueba.invalid/agentguard"),
        frontend_dist=tmp_path / "sin-dist",
    )


@pytest.fixture
def postgres() -> DobleDependencia:
    """Configurable por test: `postgres.comportamiento = "caida"`."""
    return DobleDependencia("postgres")


@pytest.fixture
def app(settings_prueba: Settings, postgres: DobleDependencia) -> FastAPI:
    return crear_app(settings_prueba, [postgres])


@pytest.fixture
def cliente(app: FastAPI) -> Iterator[TestClient]:
    # raise_server_exceptions=False: el test ve la respuesta que recibiría el cliente real.
    with TestClient(app, raise_server_exceptions=False) as cliente:
        yield cliente


def url_integracion() -> str:
    """URL del Postgres local para las pruebas `integracion` (E16).

    Se niega a devolver una URL que no sea localhost: estas pruebas pueden vaciar la base.
    """
    url = os.environ.get("INTEGRACION_DATABASE_URL", "")
    if not url:
        pytest.skip("INTEGRACION_DATABASE_URL no está definida")
    host = urlsplit(url).hostname or ""
    if host not in HOSTS_LOCALES:
        pytest.fail(f"INTEGRACION_DATABASE_URL debe apuntar a localhost, no a {host!r}")
    return url
