"""SPEC-0002 RF-03/RF-04: cada regla tiene un caso que la activa y otro que no la activa por error.

`test_spec0002_toda_regla_tiene_prueba` obliga a sumar aquí el caso de cada regla nueva.
"""

import pytest

from app.triada.clasificar import clasificar
from app.triada.modelos import Herramienta
from app.triada.reglas import REGLAS


def herramienta(
    nombre: str, descripcion: str = "", parametros: tuple[str, ...] = ()
) -> Herramienta:
    return Herramienta(
        nombre=nombre,
        descripcion=descripcion,
        parametros=parametros,
        patas_declaradas=None,
        egreso_restringido=False,
        mundo_abierto=False,
    )


def reglas_que_calzan(h: Herramienta) -> set[str]:
    return {e.regla for _, e in clasificar(h).evidencias if e.regla}


# (regla, herramienta que la activa, herramienta parecida que NO debe activarla)
CASOS: list[tuple[str, Herramienta, Herramienta]] = [
    ("P-BD", herramienta("run_sql"), herramienta("run_report", "Genera un informe")),
    (
        "P-BD",
        herramienta("consultar", "Lee la base de datos"),
        herramienta("consultar", "Lee la base"),
    ),
    ("P-CONSULTA", herramienta("query_orders"), herramienta("web_query")),
    ("P-ARCHIVO", herramienta("read_file"), herramienta("readme_viewer")),
    ("P-ARCHIVO", herramienta("list_allowed_directories"), herramienta("list_allowed_roles")),
    (
        "P-RUTA",
        herramienta("abrir", parametros=("file_path",)),
        herramienta("abrir", parametros=("paths_count_x",)),
    ),
    ("P-PERSONAS", herramienta("search_customers"), herramienta("search_products")),
    (
        "P-USUARIO",
        herramienta("get_user_profile"),
        herramienta("ayuda", "Responde lo que pide el user"),
    ),
    ("P-SECRETO", herramienta("get_secret"), herramienta("get_status")),
    ("P-CORREO", herramienta("read_inbox"), herramienta("send_email")),
    ("P-NUBE", herramienta("list_drive_files"), herramienta("driver_status")),
    ("U-WEB", herramienta("browse_page"), herramienta("show_page")),
    ("U-DESCARGA", herramienta("fetch"), herramienta("fetcher_stats", "Estadísticas")),
    (
        "U-BUSQUEDA-WEB",
        herramienta("search", "Search the web"),
        herramienta("search", "Search orders"),
    ),
    ("U-CORREO", herramienta("leer_correo"), herramienta("enviar_correo")),
    ("U-TERCEROS", herramienta("get_ticket"), herramienta("create_ticket")),
    ("U-SUBIDA", herramienta("read_attachment"), herramienta("read_note")),
    ("U-MENSAJERIA", herramienta("read_slack_history"), herramienta("send_slack_message")),
    (
        "E-URL",
        herramienta("abrir", parametros=("url",)),
        herramienta("abrir", parametros=("urlencode_mode",)),
    ),
    ("E-ENVIO", herramienta("send_report"), herramienta("sender_stats_x")),
    (
        "E-HTTP",
        herramienta("call_api", "Hace un HTTP POST"),
        herramienta("call_api", "Llama a una función"),
    ),
    ("E-PETICION", herramienta("http_request"), herramienta("requested_items", "Cuenta pedidos")),
    ("E-CORREO", herramienta("send_email"), herramienta("read_email")),
    ("E-MENSAJERIA", herramienta("post_to_slack"), herramienta("read_slack_history")),
    ("E-PUBLICO", herramienta("create_issue"), herramienta("create_invoice")),
]


@pytest.mark.parametrize(("regla", "activa", "no_activa"), CASOS, ids=[c[0] for c in CASOS])
def test_spec0002_rf03_regla(regla: str, activa: Herramienta, no_activa: Herramienta) -> None:
    assert regla in reglas_que_calzan(activa)
    assert regla not in reglas_que_calzan(no_activa)


def test_spec0002_rf04_toda_regla_tiene_prueba() -> None:
    probadas = {caso[0] for caso in CASOS}
    assert {regla.id for regla in REGLAS} == probadas


def test_spec0002_rf04_ids_unicos_y_con_prefijo_de_pata() -> None:
    ids = [regla.id for regla in REGLAS]
    assert len(ids) == len(set(ids))
    prefijo = {"datos_privados": "P-", "no_confiable": "U-", "salida_externa": "E-"}
    assert all(regla.id.startswith(prefijo[regla.pata]) for regla in REGLAS)
