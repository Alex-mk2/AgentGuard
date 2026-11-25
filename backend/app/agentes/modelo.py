"""Definición de un agente (SPEC-0003 RF-01, SPEC-0004 RF-06). Compartida por los módulos."""

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

ID_AGENTE = r"^[a-z0-9][a-z0-9_-]{0,63}$"
# `host`, `*.dominio` o con `:puerto`. Aquí solo la forma: el módulo de egresos la interpreta y
# avisa si la allowlist global no la cubre (de todos modos, la salida revisa la global).
_ENTRADA_WEB = re.compile(r"^(\*\.)?[a-z0-9.-]{1,253}(:\d{1,5})?$")


class Agente(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=ID_AGENTE)
    acciones: list[str] = Field(max_length=200)
    max_por_minuto: int = Field(default=30, ge=1, le=10_000)
    # Hosts que puede pedir por el egreso web (SPEC-0004 H4). Vacío: no tiene egreso web.
    web: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("web")
    @classmethod
    def _forma_web(cls, web: list[str]) -> list[str]:
        if any(not _ENTRADA_WEB.match(entrada) for entrada in web):
            raise ValueError("cada entrada de `web`: host, `*.dominio` o `host:puerto`")
        return web
