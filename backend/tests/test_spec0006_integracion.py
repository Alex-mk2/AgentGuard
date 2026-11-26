"""SPEC-0006 D-01: el almacén de aprobaciones contra el Postgres local. Solo con
`pytest -m integracion`. Vacía la tabla `aprobaciones` (por eso exige localhost)."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr

from app.aprobacion import AlmacenPostgres, Motivo, Pendiente, Puerta, Solicitud
from app.base import ConexionPostgres
from app.core.config import Settings
from app.inyeccion import Sesion
from tests.conftest import url_integracion

pytestmark = pytest.mark.integracion

AHORA = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)


def conexion_local() -> ConexionPostgres:
    return ConexionPostgres(Settings(_env_file=None, database_url=SecretStr(url_integracion())))


@pytest.fixture
async def base() -> AsyncIterator[ConexionPostgres]:
    conexion = conexion_local()
    await conexion.abrir()
    await conexion.migrar()
    await conexion.execute("TRUNCATE aprobaciones")
    try:
        yield conexion
    finally:
        await conexion.cerrar()


def solicitud(id_solicitud: str, huella: bytes = b"h" * 32, agente: str = "soporte") -> Solicitud:
    return Solicitud(
        id=id_solicitud,
        agente=agente,
        sesion=b"s" * 32,
        sesion_corta="abcdefgh…",
        destino="github.crear_issue",
        metodo="POST",
        huella=huella,
        motivo="sesion_contaminada",
        origen="web",
        estado="pendiente",
        creada=AHORA,
        vence=AHORA + timedelta(minutes=15),
        senales={"iny.instruccion": 2},
        parametros={"titulo": "Falla ñandú", "n": 3},
    )


async def test_spec0006_d01_migraciones_idempotentes(base: ConexionPostgres) -> None:
    otra = conexion_local()
    await otra.abrir()
    try:
        assert await otra.migrar() == []  # ya aplicadas por el fixture
        fila = await otra.fetchrow(
            "SELECT count(*) AS n FROM migraciones WHERE nombre = $1", "001_aprobaciones.sql"
        )
        assert fila is not None and fila["n"] == 1
    finally:
        await otra.cerrar()


async def test_spec0006_d01_ida_y_vuelta(base: ConexionPostgres) -> None:
    almacen = AlmacenPostgres(base)
    creada, nueva = await almacen.crear(solicitud("id-uno-0123456789abcdef"), 20, 1000, AHORA)
    assert nueva is True
    leida = await almacen.obtener(creada.id)
    assert leida == creada  # bytea, jsonb y timestamptz vuelven iguales
    assert (await almacen.listar(AHORA))[0].parametros == {"titulo": "Falla ñandú", "n": 3}
    assert await almacen.contar() == {"pendiente": 1}


async def test_spec0006_e4_indice_unico_con_concurrencia(base: ConexionPostgres) -> None:
    almacen = AlmacenPostgres(base)
    resultados = await asyncio.gather(
        *(
            almacen.crear(solicitud(f"id-{n:02d}-0123456789abcdef"), 20, 1000, AHORA)
            for n in range(8)
        )
    )
    assert sum(1 for _, nueva in resultados if nueva) == 1
    assert len({creada.id for creada, _ in resultados}) == 1


async def test_spec0006_e8_un_boleto_una_vez_con_concurrencia(base: ConexionPostgres) -> None:
    almacen = AlmacenPostgres(base)
    creada, _ = await almacen.crear(solicitud("id-boleto-0123456789abcdef"), 20, 1000, AHORA)
    decidida = await almacen.decidir(
        creada.id, "aprobada", "ok", "admin", AHORA, AHORA + timedelta(minutes=5)
    )
    assert decidida is not None and decidida.parametros is None
    usos = await asyncio.gather(
        *(
            almacen.consumir(creada.id, "soporte", creada.sesion, creada.huella, AHORA)
            for _ in range(10)
        )
    )
    assert usos.count(True) == 1


async def test_spec0006_e9_e11_condiciones(base: ConexionPostgres) -> None:
    almacen = AlmacenPostgres(base)
    creada, _ = await almacen.crear(solicitud("id-cond-0123456789abcdef"), 20, 1000, AHORA)
    # Pendiente: no se consume.
    assert not await almacen.consumir(creada.id, "soporte", creada.sesion, creada.huella, AHORA)
    await almacen.decidir(creada.id, "aprobada", None, "admin", AHORA, AHORA + timedelta(minutes=5))
    assert not await almacen.consumir(creada.id, "otro", creada.sesion, creada.huella, AHORA)
    assert not await almacen.consumir(creada.id, "soporte", b"x" * 32, creada.huella, AHORA)
    assert not await almacen.consumir(creada.id, "soporte", creada.sesion, b"x" * 32, AHORA)
    tarde = AHORA + timedelta(minutes=6)
    assert not await almacen.consumir(creada.id, "soporte", creada.sesion, creada.huella, tarde)
    assert await almacen.vencer(tarde) == 1
    assert (await almacen.obtener(creada.id)).estado == "vencida"  # type: ignore[union-attr]

    otra, _ = await almacen.crear(solicitud("id-canc-0123456789abcdef", b"k" * 32), 20, 1000, AHORA)
    assert await almacen.cancelar_sesion(otra.sesion) == 1
    cancelada = await almacen.obtener(otra.id)
    assert (
        cancelada is not None and cancelada.estado == "cancelada" and cancelada.parametros is None
    )
    # Vencida para decidir.
    tercera, _ = await almacen.crear(
        solicitud("id-venc-0123456789abcdef", b"v" * 32), 20, 1000, AHORA
    )
    assert (
        await almacen.decidir(
            tercera.id, "aprobada", None, "admin", AHORA + timedelta(minutes=15), AHORA
        )
        is None
    )


async def test_spec0006_rf02_tope(base: ConexionPostgres) -> None:
    from app.aprobacion.almacen import Saturada

    almacen = AlmacenPostgres(base)
    await almacen.crear(solicitud("id-tope1-0123456789abcdef", b"1" * 32), 1, 1000, AHORA)
    with pytest.raises(Saturada):
        await almacen.crear(solicitud("id-tope2-0123456789abcdef", b"2" * 32), 1, 1000, AHORA)
    # La idéntica se devuelve aunque el tope esté lleno.
    _, nueva = await almacen.crear(
        replace(solicitud("id-tope3-0123456789abcdef", b"1" * 32)), 1, 1000, AHORA
    )
    assert nueva is False


async def test_spec0006_puerta_con_postgres(base: ConexionPostgres) -> None:
    puerta = Puerta(AlmacenPostgres(base))
    sesion = Sesion("a" * 32, "soporte", False, None, None, 0.0)
    datos = {"accion": "github.crear_issue", "metodo": "POST", "valores": {"titulo": "x"}}
    motivo = Motivo("sesion_contaminada", "web")
    with pytest.raises(Pendiente) as pendiente:
        await puerta.exigir(
            "soporte", sesion, "github.crear_issue", "POST", datos, {}, motivo, None
        )
    id_solicitud = pendiente.value.solicitud.id
    await puerta.decidir(id_solicitud, True, None)
    await puerta.exigir(
        "soporte", sesion, "github.crear_issue", "POST", datos, {}, motivo, id_solicitud
    )
    assert (await puerta.consultar(id_solicitud, "soporte")).estado == "usada"
