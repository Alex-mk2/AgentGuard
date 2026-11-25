"""SPEC-0003 RF-01: validación de `acciones.json` y módulo apagado si es inválido."""

from pathlib import Path
from typing import Any

import pytest

from app.secretos.broker import crear_broker
from app.secretos.config import ConfiguracionBrokerInvalida, cargar_configuracion
from tests.secretos_util import CONFIG, config, entorno, escribir


def accion(**cambios: Any) -> dict[str, Any]:
    datos = dict(CONFIG["acciones"][1])
    datos.update(cambios)
    return datos


def test_spec0003_rf01_config_valida(tmp_path: Path) -> None:
    configuracion = cargar_configuracion(escribir(tmp_path, CONFIG))
    assert [a.id for a in configuracion.acciones] == ["github.crear_issue", "eco.query"]


@pytest.mark.parametrize(
    ("cambios", "mensaje"),
    [
        ({"url": "https://{host}.ejemplo/x"}, "host"),
        ({"url": "https://eco.ejemplo/x?fijo=1"}, "query"),
        ({"url": "https://usuario:clave@eco.ejemplo/x"}, "usuario"),
        ({"url": "ftp://eco.ejemplo/x"}, "https"),
        ({"url": "https://eco.ejemplo/pre{q}"}, "segmento completo"),
        ({"url": "https://eco.ejemplo/{otro}"}, "no coinciden"),
        ({"inyeccion": {"cabecera": "X", "query": "k"}}, "una de las dos"),
        ({"inyeccion": {"query": "k", "formato": "sin hueco"}}, "exactamente una vez"),
        ({"inyeccion": {"query": "k", "formato": "{secreto}{secreto}"}}, "exactamente una vez"),
        ({"inyeccion": {"cabecera": "Host"}}, "no se puede usar"),
        ({"inyeccion": {"query": "q"}}, "choca"),
        ({"parametros": {"q": {"en": "query", "patron": "("}}}, "expresión regular"),
        ({"parametros": {"Q": {"en": "query"}}}, "nombre de parámetro"),
        ({"timeout_s": 120}, "timeout_s"),
        ({"secreto": "Con-Mayus"}, "secreto"),
    ],
)
def test_spec0003_rf01_acciones_invalidas(
    tmp_path: Path, cambios: dict[str, Any], mensaje: str
) -> None:
    datos = config(acciones=[accion(**cambios)], agentes=[])
    with pytest.raises(ConfiguracionBrokerInvalida, match=mensaje):
        cargar_configuracion(escribir(tmp_path, datos))


def test_spec0003_rf01_agente_con_accion_inexistente(tmp_path: Path) -> None:
    datos = config(agentes=[{"id": "x", "acciones": ["no.existe"]}])
    with pytest.raises(ConfiguracionBrokerInvalida, match="no existen"):
        cargar_configuracion(escribir(tmp_path, datos))


def test_spec0003_rf01_ids_repetidos(tmp_path: Path) -> None:
    datos = config(acciones=[accion(), accion()], agentes=[])
    with pytest.raises(ConfiguracionBrokerInvalida, match="repetidos"):
        cargar_configuracion(escribir(tmp_path, datos))


def test_spec0003_rf01_json_roto_y_archivo_inexistente(tmp_path: Path) -> None:
    with pytest.raises(ConfiguracionBrokerInvalida, match="no es JSON"):
        cargar_configuracion(escribir(tmp_path, "{roto"))
    with pytest.raises(ConfiguracionBrokerInvalida, match="no se pudo leer"):
        cargar_configuracion(tmp_path / "no-existe.json")


def test_spec0003_rf01_invalida_apaga_el_modulo_sin_tumbar_la_app(tmp_path: Path) -> None:
    broker = crear_broker(escribir(tmp_path, "{roto"), entorno())
    assert not broker.configurado
    assert broker.estado()["error"] is not None


def test_spec0003_e8_http_solo_local_y_con_permiso(tmp_path: Path) -> None:
    local = config(acciones=[accion(url="http://localhost:9000/consulta")], agentes=[])
    externo = config(acciones=[accion(url="http://eco.ejemplo/consulta")], agentes=[])
    assert not crear_broker(escribir(tmp_path, local), entorno()).configurado
    assert crear_broker(escribir(tmp_path, local), entorno(), http_local=True).configurado
    assert not crear_broker(escribir(tmp_path, externo), entorno(), http_local=True).configurado


def test_spec0003_rf01_sin_ruta_queda_apagado() -> None:
    broker = crear_broker(None, entorno())
    assert not broker.configurado
    assert broker.estado()["configurado"] is False
