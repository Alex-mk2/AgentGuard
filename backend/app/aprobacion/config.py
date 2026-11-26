"""`APROBACION_CONFIG` (SPEC-0006 RF-01). Sin archivo valen los valores por defecto.

Que `notificar` nombre una acción válida del broker lo revisa `main` al armar la app: este módulo
no conoce el broker (RF-03).
"""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

# Mismo patrón que los ids de acción del broker (SPEC-0003).
ID_ACCION = r"^[a-z0-9][a-z0-9._-]{0,63}$"


class ConfiguracionAprobacionInvalida(Exception):
    """El archivo no existe, no es JSON o no cumple el esquema. El mensaje no trae valores."""


class ConfiguracionAprobacion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    minutos_decision: int = Field(default=15, ge=1, le=1440)  # E11
    minutos_boleto: int = Field(default=5, ge=1, le=60)  # E11
    max_pendientes_agente: int = Field(default=20, ge=1, le=1000)  # RF-02
    max_pendientes: int = Field(default=1000, ge=1, le=100_000)  # RF-02
    notificar: str | None = Field(default=None, pattern=ID_ACCION)  # E13


def cargar_configuracion(ruta: Path) -> ConfiguracionAprobacion:
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except OSError as error:
        raise ConfiguracionAprobacionInvalida(f"no se pudo leer {ruta.name}") from error
    except json.JSONDecodeError as error:
        raise ConfiguracionAprobacionInvalida(
            f"{ruta.name} no es JSON válido (línea {error.lineno})"
        ) from None
    try:
        return ConfiguracionAprobacion.model_validate(datos)
    except ValidationError as error:
        problemas = "; ".join(
            f"{'.'.join(str(parte) for parte in detalle['loc']) or 'raíz'}: {detalle['msg']}"
            for detalle in error.errors(include_input=False, include_url=False)[:5]
        )
        raise ConfiguracionAprobacionInvalida(f"{ruta.name} inválido: {problemas}") from None
