"""Aplicación FastAPI. Arranque: `python -m app.arranque` (o `uvicorn app.main:crear_app --factory
--no-access-log` en desarrollo)."""

import asyncio
import logging
import os
from collections.abc import AsyncIterator, Mapping, MutableMapping, Sequence
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.aprobacion import Almacen, AlmacenPostgres, Puerta, crear_puerta
from app.aprobacion import router as router_aprobacion
from app.base import ConexionPostgres
from app.core import salud, version
from app.core.config import Settings, cargar_settings
from app.core.errores import ServicioNoDisponible, registrar_manejadores
from app.core.registro import RegistroAcceso, configurar_logging
from app.core.salud import Dependencia
from app.core.tope import TopePeticion
from app.core.web import FrontendEstatico, frontend_disponible
from app.egresos import EgresoWeb, Resolutor, Transporte, crear_salida
from app.egresos import router as router_egresos
from app.inyeccion import crear_contencion
from app.inyeccion import router as router_inyeccion
from app.secretos import SecretBroker, crear_broker
from app.secretos import router as router_secretos
from app.triada import router as router_triada

PREFIJO_API = "/api/v1"
# La migración del arranque no puede demorar el health: si la base no responde en este tiempo,
# se reintenta antes de la primera consulta (SPEC-0006 D-01).
MIGRAR_AL_ARRANCAR_S = 5.0

logger = logging.getLogger("agentguard")


def crear_app(
    settings: Settings | None = None,
    dependencias: Sequence[Dependencia] | None = None,
    entorno: Mapping[str, str] | MutableMapping[str, str] | None = None,
    transporte_saliente: Transporte | None = None,
    resolutor: Resolutor | None = None,
    aprobaciones: Almacen | None = None,
) -> FastAPI:
    """Sin argumentos usa la configuración y la base reales; los tests pasan settings y dobles.

    `entorno` es de donde el Secret Broker lee secretos y tokens (por defecto `os.environ`, del que
    los retira al leerlos); `transporte_saliente` y `resolutor` permiten simular las APIs externas y
    el DNS en las pruebas; `aprobaciones`, el almacén de solicitudes (por defecto, Postgres).

    Cada módulo nuevo agrega aquí su router bajo `PREFIJO_API`, antes del montaje del frontend.
    """
    settings = settings or cargar_settings()
    configurar_logging(settings.log_level)
    conexion = ConexionPostgres(settings)
    migrar_al_arrancar = dependencias is None
    if dependencias is None:
        dependencias = [conexion]
    # Con dependencias de prueba y sin almacén, la conexión nunca se abre: lo que pide aprobación
    # responde 503, que es lo que pasaría con la base caída.
    puerta = crear_puerta(settings.aprobacion_config, aprobaciones or AlmacenPostgres(conexion))
    # Toda salida de red pasa por aquí (SPEC-0004 RF-02); el broker y el egreso web la comparten.
    salida = crear_salida(
        settings.egresos_config,
        resolutor,
        transporte_saliente,
        settings.secretos_http_local,
        entorno,
    )
    # La contención no conoce el registro de agentes: se crea antes y la comparten el broker y
    # el egreso web (SPEC-0005 RF-03).
    contencion = crear_contencion(settings.inyeccion_config)
    broker = crear_broker(
        settings.secretos_config,
        os.environ if entorno is None else entorno,
        salida,
        settings.secretos_http_local,
        contencion,
        puerta,
    )
    egreso_web = EgresoWeb(salida, broker.agentes, contencion, puerta)
    _conectar_puerta(puerta, broker)
    # SPEC-0006 E11: cerrar o vencer una sesión cancela sus solicitudes pendientes.
    contencion.al_cerrar(puerta.cancelar_sesion)

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
        # Abrir no conecta: si la base está caída la app arranca igual (RF-04).
        for dependencia in dependencias:
            await dependencia.abrir()
        app.state.dependencias = dependencias
        if migrar_al_arrancar:
            try:
                await asyncio.wait_for(conexion.migrar(), MIGRAR_AL_ARRANCAR_S)
            except (ServicioNoDisponible, TimeoutError):
                # Arranca igual (SPEC-0001 RF-04): migra antes de la primera consulta.
                logger.warning("Base caída al arrancar: las migraciones quedan para después")
        # Registra en el DLP las variantes de los secretos antes de la primera petición.
        await broker.preparar()
        try:
            yield
        finally:
            await puerta.esperar_tareas()
            for dependencia in dependencias:
                await dependencia.cerrar()
            await salida.cerrar()

    app = FastAPI(title="AgentGuard", version=version.VERSION, lifespan=ciclo_de_vida)
    app.state.settings = settings
    app.state.broker = broker
    app.state.egreso_web = egreso_web
    app.state.contencion = contencion
    app.state.puerta = puerta
    app.state.agentes = broker.agentes
    registrar_manejadores(app)
    # Orden: el último agregado envuelve a los demás. Tope adentro de CORS (el 413 sale con CORS) y
    # el registro de acceso afuera de todo (también registra los 413).
    app.add_middleware(TopePeticion)
    if settings.origenes_frontend:  # RF-07: sin origen configurado, sin CORS
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.origenes_frontend,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["*"],
        )
    app.add_middleware(RegistroAcceso)
    app.include_router(salud.router, prefix=PREFIJO_API)
    app.include_router(version.router, prefix=PREFIJO_API)
    app.include_router(router_triada, prefix=PREFIJO_API)  # módulo 1 (SPEC-0002)
    app.include_router(router_secretos, prefix=PREFIJO_API)  # módulo 2 (SPEC-0003)
    app.include_router(router_egresos, prefix=PREFIJO_API)  # módulo 3 (SPEC-0004)
    app.include_router(router_inyeccion, prefix=PREFIJO_API)  # módulo 4 (SPEC-0005)
    app.include_router(router_aprobacion, prefix=PREFIJO_API)  # módulo 5 (SPEC-0006)

    # Siempre al final: el frontend responde solo lo que ninguna ruta de la API tomó (RF-03).
    if frontend_disponible(settings.frontend_dist):
        app.mount("/", FrontendEstatico(directory=settings.frontend_dist), name="frontend")
    return app


def _conectar_puerta(puerta: Puerta, broker: SecretBroker) -> None:
    """SPEC-0006 E13, E15: la notificación es una acción del broker, que la puerta no conoce
    (RF-03). Una `notificar` que no sirve invalida la puerta: mejor negar que aprobar a ciegas."""
    if puerta.config.notificar is not None and puerta.error is None:
        problema = broker.problema_notificador(puerta.config.notificar)
        if problema is None:
            puerta.notificador = broker.notificar
        else:
            puerta.invalidar(problema)
    if broker.config is not None:
        usadas = {accion for agente in broker.config.agentes for accion in agente.acciones}
        puerta.avisos.extend(
            f"La acción «{accion.id}» pide aprobación siempre, pero ningún agente la usa."
            for accion in broker.config.acciones
            if accion.aprobacion == "siempre" and accion.id not in usadas
        )
