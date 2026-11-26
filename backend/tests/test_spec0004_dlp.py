"""SPEC-0004 H2: DLP determinista sobre lo que escribe el agente.

Las credenciales falsas se arman concatenando en tiempo de ejecución: así no quedan literales que
disparen gitleaks ni el secret scanning de GitHub (criterio de éxito).
"""

import base64
import os
import time
from urllib.parse import quote

import pytest

from app.egresos.dlp import Dlp, decodificados, digito_verificador, luhn
from app.egresos.limpieza import variantes

AWS = "AKIA" + "Z" * 16
GITHUB = "gh" + "p_" + "a1B2" * 9
GITHUB_FINO = "github" + "_pat_" + "x" * 30
SLACK = "xo" + "xb-" + "1234567890-abcdef"
GOOGLE = "AI" + "za" + "S" * 35
STRIPE = "sk" + "_live_" + "q" * 24
JWT = "ey" + "J" + "hbGciOiJIUzI1NiJ9" + ".ey" + "J" + "zdWIiOiIxMjM0In0" + ".abcdefghijkl"
PEM = "-----BEGIN " + "RSA PRIVATE KEY-----\nMIIB..."
TARJETA = "4111 1111 1111 1111"
RUT = "12.345.678-5"


def bloquea(texto: str, dlp: Dlp | None = None) -> tuple[str, ...]:
    return (dlp or Dlp()).revisar([texto]).bloquean


@pytest.mark.parametrize("credencial", [AWS, GITHUB, GITHUB_FINO, SLACK, GOOGLE, STRIPE, JWT, PEM])
def test_spec0004_e5_credenciales_conocidas(credencial: str) -> None:
    assert bloquea(f"mira esto: {credencial} gracias") == ("dlp.credencial",)


@pytest.mark.parametrize(
    "texto", [TARJETA, "4111-1111-1111-1111", "4111111111111111", "378282246310005"]
)
def test_spec0004_e5_tarjeta_con_luhn(texto: str) -> None:
    assert bloquea(f"pago {texto}.") == ("dlp.tarjeta",)


@pytest.mark.parametrize(
    "texto", ["4111 1111 1111 1112", "pedido 1234567890123", "12345678901234567890123"]
)
def test_spec0004_e5_numeros_que_no_son_tarjeta(texto: str) -> None:
    assert bloquea(texto) == ()


@pytest.mark.parametrize(
    "texto", [RUT, "12345678-5", "RUT: 9.999.999-3", "10.000.013-k", "10000013-K"]
)
def test_spec0004_e5_rut_valido(texto: str) -> None:
    assert bloquea(texto) == ("dlp.rut",)


@pytest.mark.parametrize(
    "texto", ["12.345.678-4", "12345678", "versión 1.234.567-2b", "a12345678-5"]
)
def test_spec0004_e5_rut_invalido_o_sin_guion(texto: str) -> None:
    assert "dlp.rut" not in bloquea(texto)


def test_spec0004_digito_verificador_y_luhn() -> None:
    assert digito_verificador(12345678) == "5"
    assert digito_verificador(10000013) == "k"
    assert luhn("4111111111111111") and not luhn("4111111111111112")


def test_spec0004_e5_marcadores_sin_mayusculas() -> None:
    dlp = Dlp(marcadores=["CONFIDENCIAL", "canario-7f3a9c2e"])
    assert bloquea("documento confidencial de la empresa", dlp) == ("dlp.marcador",)
    assert bloquea("la clave es CANARIO-7F3A9C2E", dlp) == ("dlp.marcador",)
    assert bloquea("nada que ver", dlp) == ()


def test_spec0004_e5_secreto_cargado_en_todas_sus_formas() -> None:
    secreto = "secreto-falso-de-prueba-no-real-1234567890abcdef"  # gitleaks:allow
    dlp = Dlp()
    dlp.registrar_sensibles(variantes(secreto))
    for forma in (secreto, base64.b64encode(secreto.encode()).decode(), quote(secreto, safe="")):
        assert bloquea(f"x {forma} y", dlp) == ("dlp.secreto_cargado",)


@pytest.mark.parametrize(
    "codificar",
    [
        lambda texto: base64.b64encode(texto.encode()).decode(),
        lambda texto: base64.urlsafe_b64encode(texto.encode()).decode().rstrip("="),
        lambda texto: texto.encode().hex(),
        lambda texto: quote(texto),
    ],
)
def test_spec0004_e8_una_capa_de_codificacion(codificar: object) -> None:
    assert callable(codificar)
    assert bloquea(f"dato={codificar('tarjeta ' + TARJETA)}") == ("dlp.tarjeta",)
    assert bloquea(codificar(AWS)) == ("dlp.credencial",)


def test_spec0004_e8_dos_capas_no_se_decodifican() -> None:
    """Límite documentado: lo decodificado no se vuelve a decodificar."""
    doble = base64.b64encode(base64.b64encode(("tarjeta " + TARJETA).encode())).decode()
    assert bloquea(doble) == ()


def test_spec0004_e7_modo_observar() -> None:
    dlp = Dlp(modos={"dlp.tarjeta": "observar"})
    hallazgos = dlp.revisar([TARJETA, AWS])
    assert hallazgos.bloquean == ("dlp.credencial",)
    assert hallazgos.observan == ("dlp.tarjeta",)


def test_spec0004_d02_secreto_cargado_no_se_puede_observar() -> None:
    dlp = Dlp(modos={"dlp.secreto_cargado": "observar"})
    assert dlp.modos["dlp.secreto_cargado"] == "bloquear"


def test_spec0004_e6_resultado_sin_el_valor() -> None:
    hallazgos = Dlp().revisar([f"{TARJETA} {AWS} {RUT}"])
    assert hallazgos.bloquean == ("dlp.credencial", "dlp.tarjeta", "dlp.rut")
    assert TARJETA not in repr(hallazgos) and AWS not in repr(hallazgos)


def test_spec0004_e8_decodificados_ignora_basura() -> None:
    assert decodificados("texto normal sin nada") == []
    assert decodificados("a" * 40) == []  # base64 válido pero no legible: se descarta


def test_spec0004_texto_limpio_no_bloquea() -> None:
    assert bloquea("Falla el login en la página de inicio desde el 12-05") == ()


@pytest.mark.skipif(not os.environ.get("CI"), reason="el tiempo solo se exige en el CI")
def test_spec0004_rf04_un_mega_en_menos_de_100_ms() -> None:
    dlp = Dlp(marcadores=["CONFIDENCIAL"])
    texto = ("lorem ipsum 12345 dolor sit amet, aGVsbG8gd29ybGQ= consectetur " * 16_000)[:1_000_000]
    inicio = time.perf_counter()
    dlp.revisar([texto])
    assert time.perf_counter() - inicio < 0.1
