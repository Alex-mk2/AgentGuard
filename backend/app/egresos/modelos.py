"""Tipos de la salida de red (SPEC-0004). Sin `httpx`: los demás módulos los usan sin conocerlo."""

from dataclasses import dataclass, field
from typing import Any

Valor = str | int | bool


@dataclass(frozen=True)
class PeticionSaliente:
    metodo: str
    url: str
    cabeceras: dict[str, str] = field(repr=False)  # puede llevar el secreto: fuera del repr
    # Lo que escribió el agente, para el DLP (H2). Sin valor por defecto: quien arma una petición
    # tiene que decidir qué revisa. Nunca incluye la credencial que inyecta AgentGuard.
    del_agente: tuple[str, ...] = field(repr=False)
    json: Any = None
    timeout_s: float = 10


@dataclass(frozen=True)
class RespuestaExterna:
    estado: int
    cabeceras: list[tuple[str, str]]
    cuerpo: bytes


class ErrorExterno(Exception):
    """El destino no respondió bien. `codigo`: 502 o 504. Sin detalles de la petición."""

    def __init__(self, codigo: int, motivo: str) -> None:
        super().__init__(motivo)
        self.codigo = codigo
        self.motivo = motivo


class Bloqueado(Exception):
    """La salida no se permite (403). `detalle` nunca trae lo que escribió el agente (RF-05)."""

    def __init__(self, resultado: str, detalle: Any, reglas: tuple[str, ...] = ()) -> None:
        super().__init__(resultado)
        self.resultado, self.detalle, self.reglas = resultado, detalle, reglas
