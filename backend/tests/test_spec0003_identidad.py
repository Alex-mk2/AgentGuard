"""SPEC-0003 RF-02, RF-04, RF-08 y E4: fuente de secretos y tokens."""

import pytest

from app.secretos.config import Agente
from app.secretos.fuentes import FuenteEntorno
from app.secretos.identidad import Identidades, variable_de_agente
from tests.secretos_util import SECRETO, TOKEN_ADMIN, TOKEN_LECTOR, TOKEN_SOPORTE, entorno

AGENTES = [Agente(id="soporte", acciones=[]), Agente(id="lector", acciones=[])]


async def test_spec0003_rf08_fuente_de_entorno() -> None:
    fuente = FuenteEntorno(entorno())
    assert fuente.nombres() == {"github_token", "eco_key"}
    obtenido = await fuente.obtener("github_token")
    assert obtenido is not None and obtenido.get_secret_value() == SECRETO
    assert await fuente.obtener("no_existe") is None


def test_spec0003_rf02_retira_los_secretos_del_entorno() -> None:
    variables = entorno(OTRA="se queda")
    FuenteEntorno(variables)
    Identidades(AGENTES, variables)
    assert variables == {"OTRA": "se queda"}  # ni secretos ni tokens quedan en el entorno


@pytest.mark.parametrize("valor", ["Zq7x", "Zq7xW9k2\nsalto", "Zq7xW9k2\rretorno"])
def test_spec0003_borde_secretos_rechazados(valor: str, caplog: pytest.LogCaptureFixture) -> None:
    fuente = FuenteEntorno({"AGENTGUARD_SECRETO_MALO": valor})
    assert fuente.nombres() == frozenset()
    assert fuente.rechazados == {"malo"}
    assert valor not in caplog.text


def test_spec0003_borde_secreto_vacio_no_cargado() -> None:
    fuente = FuenteEntorno({"AGENTGUARD_SECRETO_VACIO": ""})
    assert fuente.nombres() == frozenset()
    assert fuente.rechazados == frozenset()


def test_spec0003_rf02_repr_sin_valores() -> None:
    assert SECRETO not in repr(FuenteEntorno(entorno()))


def test_spec0003_e4_tokens() -> None:
    identidades = Identidades(AGENTES, entorno())
    assert identidades.agente(TOKEN_SOPORTE) == "soporte"
    assert identidades.agente(TOKEN_LECTOR) == "lector"
    assert identidades.agente("otro-token-cualquiera-123") is None
    assert identidades.agente("") is None
    assert identidades.agente(None) is None
    assert identidades.es_admin(TOKEN_ADMIN)
    assert not identidades.es_admin(TOKEN_SOPORTE)
    assert not identidades.es_admin(None)


def test_spec0003_e4_sin_token_cargado_nadie_entra() -> None:
    identidades = Identidades(AGENTES, {})
    assert identidades.agente("") is None
    assert not identidades.es_admin("")
    assert not identidades.token_cargado("soporte")


def test_spec0003_e4_token_corto_se_ignora() -> None:
    identidades = Identidades(AGENTES, {"AGENTGUARD_AGENTE_SOPORTE": "corto"})
    assert identidades.agente("corto") is None


def test_spec0003_variable_de_agente() -> None:
    assert variable_de_agente("soporte-web") == "AGENTGUARD_AGENTE_SOPORTE_WEB"
