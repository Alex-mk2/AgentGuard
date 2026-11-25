"""SPEC-0001 H3: contrato de errores (E7 a E10, D-02) y log sin IP ni query (RF-08)."""

import logging
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errores import ServicioNoDisponible


class Cuerpo(BaseModel):
    nombre: str


@pytest.fixture
def cliente_con_rutas(app: FastAPI) -> Iterator[TestClient]:
    """Rutas de prueba bajo /api/v1 que simulan lo que hará un módulo."""

    @app.post("/api/v1/prueba/validar")
    async def validar(cuerpo: Cuerpo) -> Cuerpo:
        return cuerpo

    @app.get("/api/v1/prueba/base-caida")
    async def base_caida() -> None:
        raise ServicioNoDisponible("postgres")

    @app.get("/api/v1/prueba/bug")
    async def bug() -> None:
        raise RuntimeError("clave-filtrada en la traza")

    with TestClient(app, raise_server_exceptions=False) as cliente:
        yield cliente


def test_spec0001_e7_cuerpo_invalido_422(cliente_con_rutas: TestClient) -> None:
    respuesta = cliente_con_rutas.post("/api/v1/prueba/validar", json={"otro": 1})
    assert respuesta.status_code == 422
    assert "detail" in respuesta.json()


def test_spec0001_e8_base_caida_503(cliente_con_rutas: TestClient) -> None:
    respuesta = cliente_con_rutas.get("/api/v1/prueba/base-caida")
    assert respuesta.status_code == 503
    assert respuesta.json() == {"detail": "Servicio no disponible temporalmente"}


def test_spec0001_e9_no_prevista_500_con_id_error(
    cliente_con_rutas: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR, logger="agentguard.errores"):
        respuesta = cliente_con_rutas.get("/api/v1/prueba/bug")
    assert respuesta.status_code == 500
    cuerpo = respuesta.json()
    assert cuerpo["detail"] == "Error interno"
    assert len(cuerpo["id_error"]) == 16
    assert "clave-filtrada" not in respuesta.text
    # La traza queda en el log con el mismo id_error.
    assert any(cuerpo["id_error"] in registro.getMessage() for registro in caplog.records)


def test_spec0001_e10_api_inexistente_404_json(cliente: TestClient) -> None:
    respuesta = cliente.get("/api/v1/no-existe")
    assert respuesta.status_code == 404
    assert respuesta.json() == {"detail": "Not Found"}


def test_spec0001_e10_metodo_no_permitido_405(cliente: TestClient) -> None:
    assert cliente.post("/api/v1/health").status_code == 405


def test_spec0001_rf08_log_de_acceso_sin_ip_ni_query(
    cliente: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="agentguard.acceso"):
        cliente.get("/api/v1/health?token=secreto")
    lineas = [r.getMessage() for r in caplog.records if r.name == "agentguard.acceso"]
    assert len(lineas) == 1
    assert lineas[0].startswith("GET /api/v1/health 200")
    assert "secreto" not in lineas[0]
    assert "testclient" not in lineas[0]  # el host que TestClient usa como "IP" del cliente
