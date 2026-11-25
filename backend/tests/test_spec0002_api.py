"""SPEC-0002 RF-01 y RF-06: el endpoint, sus errores y el tope global de 1 MB."""

from collections.abc import Iterator

from fastapi.testclient import TestClient

from app.core.tope import MAX_BYTES_PETICION

RUTA = "/api/v1/triada/analisis"


def test_spec0002_rf01_analisis_200(cliente: TestClient) -> None:
    respuesta = cliente.post(RUTA, json={"tools": [{"name": "run_sql"}]})
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["formato"] == "mcp"
    assert cuerpo["severidad"] == "baja"
    assert set(cuerpo["patas"]) == {"datos_privados", "no_confiable", "salida_externa"}


def test_spec0002_e15_forma_desconocida_422(cliente: TestClient) -> None:
    respuesta = cliente.post(RUTA, json={"cosa": 1})
    assert respuesta.status_code == 422
    assert "herramientas" in respuesta.json()["detail"][0]["msg"]


def test_spec0002_e15_json_roto_422(cliente: TestClient) -> None:
    respuesta = cliente.post(
        RUTA, content=b"{no es json", headers={"content-type": "application/json"}
    )
    assert respuesta.status_code == 422


def test_spec0002_rf07_422_no_refleja_el_valor(cliente: TestClient) -> None:
    respuesta = cliente.post(RUTA, json={"herramientas": [{"nombre": "a", "patas": ["SECRETO-X"]}]})
    assert respuesta.status_code == 422
    assert "SECRETO-X" not in respuesta.text


def test_spec0002_rf06_mas_de_1mb_413_por_content_length(cliente: TestClient) -> None:
    grande = b'{"tools": [], "relleno": "' + b"a" * MAX_BYTES_PETICION + b'"}'
    respuesta = cliente.post(RUTA, content=grande, headers={"content-type": "application/json"})
    assert respuesta.status_code == 413
    assert respuesta.json() == {"detail": "La petición supera el máximo de 1 MB"}


def test_spec0002_rf06_mas_de_1mb_413_sin_content_length(cliente: TestClient) -> None:
    def trozos() -> Iterator[bytes]:  # chunked: sin Content-Length
        yield b'{"tools": [], "relleno": "'
        for _ in range(20):
            yield b"a" * 65_536
        yield b'"}'

    respuesta = cliente.post(RUTA, content=trozos(), headers={"content-type": "application/json"})
    assert respuesta.status_code == 413


def test_spec0002_rf06_justo_bajo_el_tope_pasa(cliente: TestClient) -> None:
    respuesta = cliente.post(RUTA, json={"tools": [], "relleno": "a" * 1000})
    assert respuesta.status_code == 200
