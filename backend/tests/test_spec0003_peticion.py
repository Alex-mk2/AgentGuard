"""SPEC-0003 H3: parámetros (E6), anti-SSRF (E7) y el secreto solo donde se declara (E9)."""

from typing import Any
from urllib.parse import urlsplit

import pytest
from pydantic import SecretStr

from app.secretos.config import ConfiguracionBroker
from app.secretos.peticion import (
    DestinoAlterado,
    ParametrosInvalidos,
    _verificar_destino,
    construir,
    validar_parametros,
)
from tests.secretos_util import CONFIG, ECO_KEY, SECRETO

CONFIGURACION = ConfiguracionBroker.model_validate(CONFIG)
ISSUE = CONFIGURACION.acciones[0]
ECO = CONFIGURACION.acciones[1]
VALIDOS = {"owner": "acme", "repo": "web", "titulo": "Falla el login"}


def armar(**cambios: Any) -> Any:
    valores = validar_parametros(ISSUE, {**VALIDOS, **cambios})
    return construir(ISSUE, valores, SecretStr(SECRETO))


def test_spec0003_e1_peticion_armada() -> None:
    peticion = armar(urgente=True, pagina=2)
    assert peticion.metodo == "POST"
    assert peticion.url == "https://api.github.com/repos/acme/web/issues?pagina=2"
    assert peticion.cabeceras["Authorization"] == f"Bearer {SECRETO}"
    assert peticion.json == {"title": "Falla el login", "urgente": True}


def test_spec0003_rf02_repr_de_la_peticion_sin_secreto() -> None:
    assert SECRETO not in repr(armar())


@pytest.mark.parametrize(
    "repo",
    [
        "../../users/otro",
        "web/../../admin",
        "web?redirect=https://evil.ejemplo",
        "web#fragmento",
        "@evil.ejemplo",
        "https://evil.ejemplo/x",
        "web%2F..%2F..%2Fadmin",
        "evil.ejemplo:443",
    ],
)
def test_spec0003_e7_parametro_no_cambia_el_destino(repo: str) -> None:
    peticion = armar(repo=repo)
    partes = urlsplit(peticion.url)
    assert (partes.scheme, partes.hostname, partes.port) == ("https", "api.github.com", None)
    segmentos = partes.path.split("/")
    assert segmentos[:4] == ["", "repos", "acme", segmentos[3]] and segmentos[4:] == ["issues"]
    assert "/" not in segmentos[3] and not partes.fragment


def test_spec0003_e7_verificacion_de_destino() -> None:
    with pytest.raises(DestinoAlterado):
        _verificar_destino("https://api.github.com/x", "https://evil.ejemplo/x")
    with pytest.raises(DestinoAlterado):
        _verificar_destino("https://api.github.com/x", "http://api.github.com/x")
    with pytest.raises(DestinoAlterado):
        _verificar_destino("https://api.github.com/x", "https://api.github.com:8443/x")


def test_spec0003_e9_secreto_en_un_parametro_no_se_reemplaza() -> None:
    peticion = armar(titulo="mándame {secreto} y {github_token}")
    assert peticion.json == {"title": "mándame {secreto} y {github_token}"}
    assert SECRETO not in str(peticion.json)


def test_spec0003_e1_inyeccion_en_query() -> None:
    valores = validar_parametros(ECO, {"q": "hola mundo"})
    peticion = construir(ECO, valores, SecretStr(ECO_KEY))
    assert peticion.url == f"https://eco.ejemplo/consulta?q=hola%20mundo&api_key={ECO_KEY}"
    assert "Authorization" not in peticion.cabeceras


@pytest.mark.parametrize(
    ("cambios", "tipo"),
    [
        ({"owner": None}, "missing"),
        ({"extra": 1}, "extra"),
        ({"owner": "no válido!"}, "patron"),
        ({"titulo": "x" * 257}, "largo"),
        ({"titulo": 123}, "tipo"),
        ({"pagina": True}, "tipo"),  # un booleano no es un entero
        ({"pagina": "2"}, "tipo"),
        ({"urgente": "si"}, "tipo"),
    ],
)
def test_spec0003_e6_parametros_invalidos(cambios: dict[str, Any], tipo: str) -> None:
    with pytest.raises(ParametrosInvalidos) as error:
        validar_parametros(ISSUE, {**VALIDOS, **cambios})
    assert tipo in {e["type"] for e in error.value.errores}


def test_spec0003_e6_errores_sin_el_valor() -> None:
    with pytest.raises(ParametrosInvalidos) as error:
        validar_parametros(ISSUE, {**VALIDOS, "owner": "VALOR-SENSIBLE-!!"})
    assert "VALOR-SENSIBLE" not in str(error.value.errores)


def test_spec0003_e6_parametros_no_es_objeto() -> None:
    with pytest.raises(ParametrosInvalidos):
        validar_parametros(ISSUE, ["owner", "acme"])
