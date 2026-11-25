"""Modelos del Detector de la Tríada Letal (SPEC-0002): entrada, herramienta y reporte."""

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Pata = Literal["datos_privados", "no_confiable", "salida_externa"]
PATAS: tuple[Pata, ...] = ("datos_privados", "no_confiable", "salida_externa")

Severidad = Literal["critica", "alta", "media", "baja", "ninguna"]
Origen = Literal["declarado", "anotacion", "regla"]
Clasificacion = Literal["declarada", "inferida", "sin_clasificar"]

MAX_HERRAMIENTAS = 500
MAX_NOMBRE = 128
MAX_DESCRIPCION = 20_000
MAX_PARAMETROS = 200


# --- Entrada: formato propio (D-01). `extra="forbid"`: un campo mal escrito ("pata") es un error,
# no algo que se ignora en silencio.


class Egreso(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowlist: list[str] = Field(max_length=200)


class HerramientaPropia(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=1, max_length=MAX_NOMBRE)
    descripcion: str = Field(default="", max_length=MAX_DESCRIPCION)
    parametros: list[str] = Field(default_factory=list, max_length=MAX_PARAMETROS)
    patas: list[Pata] | None = None  # None → se infiere; [] → declarada inofensiva
    egreso: Egreso | None = None  # con allowlist (aunque vacía) → salida restringida


class ManifiestoPropio(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agente: str | None = Field(default=None, max_length=MAX_NOMBRE)
    herramientas: list[HerramientaPropia] = Field(max_length=MAX_HERRAMIENTAS)


# --- Entrada: MCP `tools/list`. `extra="ignore"`: el estándar suma campos con cada versión.


class AnotacionesMcp(BaseModel):
    model_config = ConfigDict(extra="ignore")

    openWorldHint: bool | None = None  # nombre del estándar MCP


class HerramientaMcp(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=MAX_NOMBRE)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPCION)
    inputSchema: dict[str, Any] | None = None
    annotations: AnotacionesMcp | None = None


class ManifiestoMcp(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tools: list[HerramientaMcp] = Field(max_length=MAX_HERRAMIENTAS)


# --- Modelo interno: los dos formatos se llevan a esto antes de analizar (RF-02).


@dataclass(frozen=True)
class Herramienta:
    nombre: str
    descripcion: str
    parametros: tuple[str, ...]
    patas_declaradas: frozenset[Pata] | None  # None = no declaradas
    egreso_restringido: bool
    mundo_abierto: bool  # anotación MCP openWorldHint: true


# --- Reporte (salida de POST /api/v1/triada/analisis).


class Evidencia(BaseModel):
    herramienta: str
    origen: Origen
    regla: str | None = None
    fragmento: str | None = None  # solo el token que calzó, nunca la descripción (RF-07)


class ResumenHerramienta(BaseModel):
    nombre: str
    patas: list[Pata]
    clasificacion: Clasificacion
    egreso_restringido: bool
    multipata: bool


class Recomendacion(BaseModel):
    id: str
    texto: str


class Reporte(BaseModel):
    formato: Literal["mcp", "agentguard"]
    severidad: Severidad
    incompleto: bool
    severidad_peor_caso: Severidad | None
    faltan: list[Pata]
    patas: dict[Pata, list[Evidencia]]
    herramientas: list[ResumenHerramienta]
    recomendaciones: list[Recomendacion]
