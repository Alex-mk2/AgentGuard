"""Aplicación FastAPI. Arranque: `uvicorn app.main:crear_app --factory --no-access-log`."""

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.base import ConexionPostgres
from app.core import salud, version
from app.core.config import Settings, cargar_settings
from app.core.errores import registrar_manejadores
from app.core.registro import RegistroAcceso, configurar_logging
from app.core.salud import Dependencia
from app.core.tope import TopePeticion
from app.core.web import FrontendEstatico, frontend_disponible
from app.triada import router as router_triada

PREFIJO_API = "/api/v1"


def crear_app(
    settings: Settings | None = None,
    dependencias: Sequence[Dependencia] | None = None,
) -> FastAPI:
    """Sin argumentos usa la configuración y la base reales; los tests pasan settings y dobles.

    Cada módulo nuevo agrega aquí su router bajo `PREFIJO_API`, antes del montaje del frontend.
    """
    settings = settings or cargar_settings()
    configurar_logging(settings.log_level)
    if dependencias is None:
        dependencias = [ConexionPostgres(settings)]

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
        # Abrir no conecta: si la base está caída la app arranca igual (RF-04).
        for dependencia in dependencias:
            await dependencia.abrir()
        app.state.dependencias = dependencias
        try:
            yield
        finally:
            for dependencia in dependencias:
                await dependencia.cerrar()

    app = FastAPI(title="AgentGuard", version=version.VERSION, lifespan=ciclo_de_vida)
    app.state.settings = settings
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

    # Siempre al final: el frontend responde solo lo que ninguna ruta de la API tomó (RF-03).
    if frontend_disponible(settings.frontend_dist):
        app.mount("/", FrontendEstatico(directory=settings.frontend_dist), name="frontend")
    return app
