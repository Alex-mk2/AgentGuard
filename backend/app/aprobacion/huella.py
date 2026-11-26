"""Huellas (SPEC-0006 E8, RF-04): lo que ata un boleto a una acción exacta y a una sesión."""

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from app.inyeccion import Sesion


def huella(datos: Mapping[str, Any]) -> bytes:
    """SHA-256 del JSON canónico: claves ordenadas, sin espacios, UTF-8. La misma llamada da
    siempre la misma huella, y cualquier valor distinto da otra."""
    texto = json.dumps(datos, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(texto.encode("utf-8")).digest()


def huella_sesion(sesion: Sesion) -> bytes:
    """El id de sesión es una capacidad del runtime: se guarda su hash, nunca el id. Lleva la hora
    de creación porque la sesión implícita reusa su id (`implicita:<agente>`) al vencer, y un
    boleto de la anterior no debe servir en la nueva."""
    texto = f"{sesion.id}\n{sesion.creada.isoformat()}"
    return hashlib.sha256(texto.encode("utf-8")).digest()
