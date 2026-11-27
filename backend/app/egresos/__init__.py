"""Módulo 3: Sealed Tools y control de egresos (SPEC-0004). Lo público del módulo.

Es el único punto de salida de red de AgentGuard: allowlist, DLP, IP públicas y envío.
"""

from app.egresos.limpieza import decodificar_cuerpo, limpiar, limpiar_cabeceras, variantes
from app.egresos.modelos import (
    Bloqueado,
    ErrorExterno,
    PeticionSaliente,
    RespuestaExterna,
    Valor,
)
from app.egresos.red import Resolutor
from app.egresos.rutas import router
from app.egresos.salida import USER_AGENT_POR_DEFECTO, Salida, Transporte, crear_salida
from app.egresos.web import EgresoWeb

__all__ = [
    "USER_AGENT_POR_DEFECTO",
    "Bloqueado",
    "EgresoWeb",
    "ErrorExterno",
    "PeticionSaliente",
    "Resolutor",
    "RespuestaExterna",
    "Salida",
    "Transporte",
    "Valor",
    "crear_salida",
    "decodificar_cuerpo",
    "limpiar",
    "limpiar_cabeceras",
    "router",
    "variantes",
]
