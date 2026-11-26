"""Módulo 5: Human-in-the-Loop Gate (SPEC-0006). Lo público del módulo.

Pausa las acciones irreversibles, las del plano de control y las de una sesión contaminada hasta
que una persona las apruebe. La aprobación vale una vez y solo para esa acción exacta.
"""

from app.aprobacion.almacen import Almacen, AlmacenPostgres
from app.aprobacion.modelos import Motivo, Solicitud
from app.aprobacion.puerta import (
    CABECERA_APROBACION,
    Pendiente,
    Puerta,
    Rechazada,
    crear_puerta,
)
from app.aprobacion.rutas import router

__all__ = [
    "CABECERA_APROBACION",
    "Almacen",
    "AlmacenPostgres",
    "Motivo",
    "Pendiente",
    "Puerta",
    "Rechazada",
    "Solicitud",
    "crear_puerta",
    "router",
]
