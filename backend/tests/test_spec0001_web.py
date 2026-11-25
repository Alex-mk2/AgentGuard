"""SPEC-0001 H4: el monolito sirve el build de React (RF-03, E10, E13) sin path traversal."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import crear_app
from tests.dobles.dependencias import DobleDependencia

INDEX = "<!doctype html><title>AgentGuard</title>"


@pytest.fixture
def cliente_web(
    settings_prueba: Settings, postgres: DobleDependencia, tmp_path: Path
) -> Iterator[TestClient]:
    """`dist` de prueba dentro de tmp_path, con un secreto al lado (fuera de `dist`)."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX, encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / ".env").write_text("DATABASE_URL=secreto-fuera-de-dist", encoding="utf-8")
    settings = settings_prueba.model_copy(update={"frontend_dist": dist})
    with TestClient(crear_app(settings, [postgres]), raise_server_exceptions=False) as cliente:
        yield cliente


def test_spec0001_rf03_raiz_entrega_index(cliente_web: TestClient) -> None:
    respuesta = cliente_web.get("/")
    assert respuesta.status_code == 200
    assert respuesta.text == INDEX


def test_spec0001_rf03_sirve_assets(cliente_web: TestClient) -> None:
    respuesta = cliente_web.get("/assets/app.js")
    assert respuesta.status_code == 200
    assert respuesta.text == "console.log(1)"


def test_spec0001_e13_ruta_del_frontend_entrega_index(cliente_web: TestClient) -> None:
    respuesta = cliente_web.get("/modulos/triada")
    assert respuesta.status_code == 200
    assert respuesta.text == INDEX


def test_spec0001_e13_asset_inexistente_404(cliente_web: TestClient) -> None:
    assert cliente_web.get("/assets/falta.js").status_code == 404


def test_spec0001_e10_api_gana_al_frontend(cliente_web: TestClient) -> None:
    assert cliente_web.get("/api/v1/health").json() == {"estado": "ok"}
    respuesta = cliente_web.get("/api/v1/no-existe")
    assert respuesta.status_code == 404
    assert respuesta.json() == {"detail": "Not Found"}
    assert cliente_web.get("/api").status_code == 404


def test_spec0001_e10_metodo_no_permitido_con_frontend(cliente_web: TestClient) -> None:
    assert cliente_web.post("/api/v1/health").status_code == 405


@pytest.mark.parametrize(
    "ruta", ["/../.env", "/%2e%2e/.env", "/assets/..%2f..%2f.env", "/..%5c.env", "/.env"]
)
def test_spec0001_borde_no_sale_de_dist(cliente_web: TestClient, ruta: str) -> None:
    respuesta = cliente_web.get(ruta)
    assert "secreto-fuera-de-dist" not in respuesta.text


def test_spec0001_e2_sin_dist_solo_api(cliente: TestClient) -> None:
    assert cliente.get("/").status_code == 404
    assert cliente.get("/api/v1/health").status_code == 200
