"""SPEC-0003 E2 y RF-05: el secreto no vuelve al agente, en ninguna de sus formas."""

import base64
import json
from urllib.parse import quote

import pytest

from app.egresos.limpieza import REEMPLAZO, limpiar, limpiar_cabeceras, variantes
from tests.secretos_util import SECRETO

FORMAS = variantes(SECRETO)


@pytest.mark.parametrize(
    "forma",
    [
        SECRETO,
        base64.b64encode(SECRETO.encode()).decode(),
        base64.urlsafe_b64encode(SECRETO.encode()).decode().rstrip("="),
        quote(SECRETO, safe=""),
    ],
)
def test_spec0003_e2_cada_forma_se_limpia(forma: str) -> None:
    datos, limpiado = limpiar(f'{{"eco": "{forma}"}}'.encode(), FORMAS)
    assert limpiado
    assert forma.encode() not in datos
    assert REEMPLAZO in datos


def test_spec0003_e2_secreto_con_caracteres_especiales_en_json() -> None:
    especial = 'clave/con"comillas\\y-barras'
    reflejado = json.dumps({"eco": especial}).encode()
    datos, limpiado = limpiar(reflejado, variantes(especial))
    assert limpiado and b"comillas" not in datos


def test_spec0003_e2_sin_secreto_no_toca_nada() -> None:
    original = b'{"number": 42}'
    assert limpiar(original, FORMAS) == (original, False)


def test_spec0003_rf05_allowlist_de_cabeceras() -> None:
    cabeceras, limpiado = limpiar_cabeceras(
        [
            ("Content-Type", "application/json"),
            ("Set-Cookie", "sesion=abc"),
            ("X-Debug-Auth", f"Bearer {SECRETO}"),
            ("X-RateLimit-Remaining", "4999"),
            ("Location", f"https://api.ejemplo/x?token={SECRETO}"),
        ],
        FORMAS,
    )
    assert set(cabeceras) == {"content-type", "x-ratelimit-remaining", "location"}
    assert SECRETO not in cabeceras["location"]
    assert limpiado
