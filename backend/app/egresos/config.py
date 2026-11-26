"""Configuración de egresos: allowlist global y DLP (SPEC-0004 RF-01, D-01, D-02).

Archivo versionado, como `acciones.json`: cada destino nuevo pasa por un PR.
"""

import json
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.egresos.dlp import REGLAS, SIEMPRE_BLOQUEAN, Modo
from app.egresos.hosts import EntradaAllowlist, HostInvalido, parsear_entrada


class ConfiguracionEgresosInvalida(Exception):
    """El archivo no existe, no es JSON o no cumple el esquema. El mensaje no trae valores."""


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ConfiguracionDlp(_Estricto):
    modos: dict[str, Modo] = Field(default_factory=dict)
    marcadores: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def _validar(self) -> Self:
        for regla, modo in self.modos.items():
            if regla not in REGLAS:
                raise ValueError("hay una regla DLP desconocida en `modos`")
            if regla in SIEMPRE_BLOQUEAN and modo != "bloquear":
                raise ValueError(f"«{regla}» siempre bloquea")
        for marcador in self.marcadores:
            if not 4 <= len(marcador) <= 200 or not marcador.isprintable():
                raise ValueError("cada marcador: de 4 a 200 caracteres imprimibles")
        return self


class ConfiguracionEgresos(_Estricto):
    allowlist: list[str] = Field(max_length=500)
    dlp: ConfiguracionDlp = Field(default_factory=ConfiguracionDlp)

    @field_validator("allowlist")
    @classmethod
    def _entradas_validas(cls, allowlist: list[str]) -> list[str]:
        for posicion, texto in enumerate(allowlist):
            try:
                parsear_entrada(texto)
            except HostInvalido as error:
                raise ValueError(f"entrada {posicion}: {error}") from None
        return allowlist

    @property
    def entradas(self) -> tuple[EntradaAllowlist, ...]:
        return tuple(dict.fromkeys(parsear_entrada(texto) for texto in self.allowlist))


def cargar_configuracion(ruta: Path) -> ConfiguracionEgresos:
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except OSError as error:
        raise ConfiguracionEgresosInvalida(f"no se pudo leer {ruta.name}") from error
    except json.JSONDecodeError as error:
        raise ConfiguracionEgresosInvalida(
            f"{ruta.name} no es JSON válido (línea {error.lineno})"
        ) from None
    try:
        return ConfiguracionEgresos.model_validate(datos)
    except ValidationError as error:
        problemas = "; ".join(
            f"{'.'.join(str(parte) for parte in detalle['loc']) or 'raíz'}: {detalle['msg']}"
            for detalle in error.errors(include_input=False, include_url=False)[:5]
        )
        raise ConfiguracionEgresosInvalida(f"{ruta.name} inválido: {problemas}") from None
