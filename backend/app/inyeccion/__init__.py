"""Módulo 4: Contención de prompt injection y rogue actions (SPEC-0005). Lo público del módulo.

Inspecciona el contenido no confiable que entra al contexto del modelo y contiene las sesiones que
lo ingirieron: pierden las acciones con efecto, se haya detectado la inyección o no.
"""

from app.inyeccion.contencion import (
    CABECERA_SESION,
    Contencion,
    Contenida,
    crear_contencion,
)
from app.inyeccion.inspector import Resultado
from app.inyeccion.reglas import Tipo
from app.inyeccion.rutas import router
from app.inyeccion.sesiones import Sesion

__all__ = [
    "CABECERA_SESION",
    "Contencion",
    "Contenida",
    "Resultado",
    "Sesion",
    "Tipo",
    "crear_contencion",
    "router",
]
