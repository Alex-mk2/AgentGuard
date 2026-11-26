"""SPEC-0006: la puerta con el almacén en memoria y un reloj falso (sin red ni base)."""

import asyncio
from collections.abc import Awaitable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.aprobacion import Motivo, Pendiente, Puerta, Rechazada, crear_puerta
from app.aprobacion.config import ConfiguracionAprobacion
from app.aprobacion.huella import huella, huella_sesion
from app.core.errores import ServicioNoDisponible
from app.inyeccion import Sesion
from tests.dobles.aprobaciones import AlmacenMemoria

CONTAMINADA = Motivo("sesion_contaminada", "web")
DATOS = {"accion": "github.crear_issue", "metodo": "POST", "valores": {"titulo": "Falla"}}
PARAMETROS = {"titulo": "Falla"}


class Reloj:
    def __init__(self) -> None:
        self.ahora = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.ahora

    def avanzar(self, minutos: float) -> None:
        self.ahora += timedelta(minutes=minutos)


def sesion(id_sesion: str = "a" * 32, agente: str = "soporte") -> Sesion:
    return Sesion(id_sesion, agente, False, None, None, 0.0)


@pytest.fixture
def reloj() -> Reloj:
    return Reloj()


@pytest.fixture
def almacen() -> AlmacenMemoria:
    return AlmacenMemoria()


@pytest.fixture
def puerta(almacen: AlmacenMemoria, reloj: Reloj) -> Puerta:
    return Puerta(almacen, reloj=reloj)


async def pedir(
    puerta: Puerta,
    boleto: str | None = None,
    actual: Sesion | None = None,
    datos: dict[str, Any] | None = None,
    agente: str = "soporte",
    parametros: dict[str, Any] | None = None,
) -> None:
    await puerta.exigir(
        agente,
        actual or SESION,
        "github.crear_issue",
        "POST",
        datos or DATOS,
        PARAMETROS if parametros is None else parametros,
        CONTAMINADA,
        boleto,
    )


SESION = sesion()


async def pendiente(puerta: Puerta, **kwargs: Any) -> str:
    with pytest.raises(Pendiente) as error:
        await pedir(puerta, **kwargs)
    return error.value.solicitud.id


async def aprobada(puerta: Puerta) -> str:
    id_solicitud = await pendiente(puerta)
    await puerta.decidir(id_solicitud, True, "ok")
    return id_solicitud


async def rechazo(llamada: Awaitable[Any]) -> int:
    with pytest.raises(Rechazada) as error:
        await llamada
    return error.value.codigo


# --- huellas (RF-04)


def test_spec0006_rf04_huella_canonica() -> None:
    assert huella({"a": 1, "b": "x"}) == huella({"b": "x", "a": 1})
    assert huella({"a": 1}) != huella({"a": 2})
    assert huella({"valores": {"titulo": "á"}}) == huella({"valores": {"titulo": "á"}})


def test_spec0006_e8_la_implicita_renacida_es_otra_sesion() -> None:
    primera = Sesion("implicita:soporte", "soporte", True, None, None, 0.0)
    segunda = Sesion(
        "implicita:soporte",
        "soporte",
        True,
        None,
        None,
        0.0,
        creada=primera.creada + timedelta(seconds=1),
    )
    assert huella_sesion(primera) != huella_sesion(segunda)


# --- H1: queda en pausa


async def test_spec0006_e3_sin_boleto_queda_pendiente(puerta: Puerta, reloj: Reloj) -> None:
    with pytest.raises(Pendiente) as error:
        await pedir(puerta)
    solicitud = error.value.solicitud
    assert solicitud.estado == "pendiente"
    assert solicitud.vence == reloj.ahora + timedelta(minutes=15)
    assert error.value.contenido() == {"aprobacion": solicitud.para_agente()}
    assert error.value.cabeceras() == {"Retry-After": "5"}
    assert set(solicitud.para_agente()) == {"id", "estado", "vence"}


async def test_spec0006_e4_la_identica_devuelve_la_misma(puerta: Puerta) -> None:
    primera = await pendiente(puerta)
    assert await pendiente(puerta) == primera
    otra = await pendiente(puerta, datos={**DATOS, "valores": {"titulo": "Otra"}})
    assert otra != primera


async def test_spec0006_rf02_tope_por_agente_y_total(almacen: AlmacenMemoria, reloj: Reloj) -> None:
    puerta = Puerta(
        almacen,
        ConfiguracionAprobacion(max_pendientes_agente=2, max_pendientes=3),
        reloj=reloj,
    )
    for numero in range(2):
        await pendiente(puerta, datos={**DATOS, "valores": {"n": numero}})
    assert await rechazo(pedir(puerta, datos={**DATOS, "valores": {"n": 9}})) == 429
    await pendiente(puerta, agente="otro", actual=sesion(agente="otro"))
    assert await rechazo(pedir(puerta, agente="tercero", actual=sesion(agente="tercero"))) == 429


async def test_spec0006_rf05_parametros_saneados_y_truncados(puerta: Puerta) -> None:
    invisible = chr(0x200B) + chr(0x202E)
    largo = "x" * 5000
    with pytest.raises(Pendiente) as error:
        await pedir(
            puerta,
            parametros={"titulo": f"ho{invisible}la", "cuerpo": largo, "n": 3, "anidado": {"a": 1}},
        )
    mostrados = error.value.solicitud.parametros
    assert mostrados is not None
    assert mostrados["titulo"] == "hola"
    assert mostrados["cuerpo"].startswith("x" * 2048) and mostrados["cuerpo"].endswith("(truncado)")
    assert len(mostrados["cuerpo"]) < 2100
    assert mostrados["n"] == 3
    assert mostrados["anidado"] == '{"a": 1}'


async def test_spec0006_e5_senales_de_la_sesion(puerta: Puerta) -> None:
    actual = sesion()
    actual.senales["iny.instruccion"] += 2
    with pytest.raises(Pendiente) as error:
        await pedir(puerta, actual=actual)
    assert error.value.solicitud.senales == {"iny.instruccion": 2}


# --- H3: el boleto vale una vez y solo para esa acción


async def test_spec0006_e8_boleto_aprobado_vale_una_vez(puerta: Puerta) -> None:
    boleto = await aprobada(puerta)
    await pedir(puerta, boleto=boleto)  # vuelve: se ejecuta
    assert await rechazo(pedir(puerta, boleto=boleto)) == 403


async def test_spec0006_e8_reintentos_simultaneos_solo_uno(puerta: Puerta) -> None:
    boleto = await aprobada(puerta)
    resultados = await asyncio.gather(
        *(pedir(puerta, boleto=boleto) for _ in range(10)), return_exceptions=True
    )
    assert sum(1 for r in resultados if r is None) == 1
    assert all(isinstance(r, Rechazada) for r in resultados if r is not None)


@pytest.mark.parametrize(
    "cambio",
    [
        {"datos": {**DATOS, "valores": {"titulo": "Otro"}}},
        {"actual": sesion("b" * 32)},
        {"agente": "otro", "actual": sesion(agente="otro")},
    ],
    ids=["otro-parametro", "otra-sesion", "otro-agente"],
)
async def test_spec0006_e9_cualquier_diferencia_403(puerta: Puerta, cambio: dict[str, Any]) -> None:
    boleto = await aprobada(puerta)
    with pytest.raises(Rechazada) as error:
        await pedir(puerta, boleto=boleto, **cambio)
    assert (error.value.codigo, error.value.detalle) == (
        403,
        "Aprobación no válida para esta acción",
    )
    await pedir(puerta, boleto=boleto)  # el boleto sigue sirviendo para lo aprobado


async def test_spec0006_e9_pendiente_negada_vencida_o_inventada(
    puerta: Puerta, reloj: Reloj
) -> None:
    pendiente_id = await pendiente(puerta)
    assert await rechazo(pedir(puerta, boleto=pendiente_id)) == 403
    await puerta.decidir(pendiente_id, False, None)
    assert await rechazo(pedir(puerta, boleto=pendiente_id)) == 403

    boleto = await aprobada(puerta)
    reloj.avanzar(5.1)  # E11: 5 min para usar el boleto
    assert await rechazo(pedir(puerta, boleto=boleto)) == 403

    assert await rechazo(pedir(puerta, boleto="inventado-" + "x" * 20)) == 403
    assert await rechazo(pedir(puerta, boleto="corto")) == 403


async def test_spec0006_e12_aprobar_no_limpia_la_sesion(puerta: Puerta) -> None:
    boleto = await aprobada(puerta)
    await pedir(puerta, boleto=boleto)
    # La siguiente acción con efecto de la misma sesión pide su propia aprobación.
    nueva = await pendiente(puerta)
    assert nueva != boleto


# --- H2: decidir


async def test_spec0006_e6_decidir(puerta: Puerta, reloj: Reloj) -> None:
    id_solicitud = await pendiente(puerta)
    decidida = await puerta.decidir(id_solicitud, True, "revisado")
    assert decidida.estado == "aprobada" and decidida.nota == "revisado"
    assert decidida.decidida_por == "admin"
    assert decidida.parametros is None  # E14: se borran al decidir
    assert decidida.vence == reloj.ahora + timedelta(minutes=5)
    assert await rechazo(puerta.decidir(id_solicitud, False, None)) == 409
    assert await rechazo(puerta.decidir("no-existe", True, None)) == 404


async def test_spec0006_e11_vencida_no_se_decide(puerta: Puerta, reloj: Reloj) -> None:
    id_solicitud = await pendiente(puerta)
    reloj.avanzar(15)
    assert await rechazo(puerta.decidir(id_solicitud, True, None)) == 409
    consultada = await puerta.consultar(id_solicitud, "soporte")
    assert consultada.estado == "vencida"
    listada = await puerta.listar()
    assert [s.estado for s in listada] == ["vencida"] and listada[0].parametros is None


async def test_spec0006_e10_consultar_solo_el_dueno(puerta: Puerta) -> None:
    id_solicitud = await pendiente(puerta)
    assert (await puerta.consultar(id_solicitud, "soporte")).estado == "pendiente"
    assert await rechazo(puerta.consultar(id_solicitud, "otro")) == 404
    assert await rechazo(puerta.consultar("no-existe", "soporte")) == 404


async def test_spec0006_e11_cerrar_la_sesion_cancela(puerta: Puerta) -> None:
    id_solicitud = await pendiente(puerta)
    boleto = await aprobada(puerta)
    otra = await pendiente(puerta, actual=sesion("c" * 32))
    puerta.cancelar_sesion(SESION)
    await puerta.esperar_tareas()
    assert (await puerta.consultar(id_solicitud, "soporte")).estado == "cancelada"
    assert (await puerta.consultar(boleto, "soporte")).estado == "cancelada"
    assert (await puerta.consultar(otra, "soporte")).estado == "pendiente"


# --- RF-01 y base caída


async def test_spec0006_rf01_sin_almacen_o_invalida_niega(almacen: AlmacenMemoria) -> None:
    assert await rechazo(pedir(Puerta(None))) == 403
    assert await rechazo(pedir(Puerta(almacen, error="roto"))) == 403
    assert almacen.filas == {}


def test_spec0006_rf01_configuracion(tmp_path: Path, almacen: AlmacenMemoria) -> None:
    assert crear_puerta(None, almacen).error is None
    ruta = tmp_path / "aprobacion.json"
    ruta.write_text('{"minutos_decision": 30, "notificar": "slack.aviso"}', encoding="utf-8")
    puerta = crear_puerta(ruta, almacen)
    assert puerta.error is None and puerta.config.minutos_decision == 30
    ruta.write_text('{"minutos_decision": 0, "otro": "secreto-no-se-refleja"}', encoding="utf-8")
    invalida = crear_puerta(ruta, almacen)
    assert invalida.error is not None and "secreto-no-se-refleja" not in invalida.error
    ruta.write_text("{no es json", encoding="utf-8")
    assert crear_puerta(ruta, almacen).error is not None
    assert crear_puerta(tmp_path / "no-existe.json", almacen).error is not None


async def test_spec0006_d01_base_caida_503(puerta: Puerta, almacen: AlmacenMemoria) -> None:
    almacen.caida = True
    with pytest.raises(ServicioNoDisponible):
        await pedir(puerta)
    estado = await puerta.estado()
    assert estado["contadores"] is None and any("base" in aviso for aviso in estado["avisos"])


# --- H4: notificación


async def test_spec0006_e13_notifica_sin_parametros(almacen: AlmacenMemoria, reloj: Reloj) -> None:
    puerta = Puerta(almacen, ConfiguracionAprobacion(notificar="slack.aviso"), reloj=reloj)
    enviados: list[tuple[str, str]] = []

    async def notificador(accion: str, texto: str) -> None:
        enviados.append((accion, texto))

    puerta.notificador = notificador
    await pendiente(puerta, parametros={"titulo": "dato-privado-del-cliente"})
    await pendiente(puerta, parametros={"titulo": "dato-privado-del-cliente"})  # misma: no repite
    await puerta.esperar_tareas()
    assert len(enviados) == 1
    accion, texto = enviados[0]
    assert accion == "slack.aviso"
    assert "soporte" in texto and "github.crear_issue" in texto and "web" in texto
    assert "dato-privado" not in texto


async def test_spec0006_e13_un_aviso_que_falla_no_afecta(
    almacen: AlmacenMemoria, reloj: Reloj, caplog: pytest.LogCaptureFixture
) -> None:
    puerta = Puerta(almacen, ConfiguracionAprobacion(notificar="slack.aviso"), reloj=reloj)

    async def roto(accion: str, texto: str) -> None:
        raise RuntimeError("detalle-interno")

    puerta.notificador = roto
    id_solicitud = await pendiente(puerta)
    await puerta.esperar_tareas()
    assert (await puerta.consultar(id_solicitud, "soporte")).estado == "pendiente"
    assert "RuntimeError" in caplog.text and "detalle-interno" not in caplog.text


async def test_spec0006_e15_estado_cuenta(puerta: Puerta) -> None:
    await pendiente(puerta, datos={**DATOS, "valores": {"titulo": "Otra"}})
    boleto = await aprobada(puerta)
    await pedir(puerta, boleto=boleto)
    estado = await puerta.estado()
    assert estado["configurado"] is True
    assert estado["contadores"] == {"pendiente": 1, "usada": 1}
