"""Identidad de los agentes, compartida por los módulos (SPEC-0004 RF-06). Solo esto es público.

No importa ningún módulo de dominio: los módulos dependen de este paquete, nunca al revés.
"""

from app.agentes.identidad import Identidades, variable_de_agente
from app.agentes.limite import LimitePorAgente
from app.agentes.modelo import Agente
from app.agentes.registro import RegistroAgentes, token_bearer

__all__ = [
    "Agente",
    "Identidades",
    "LimitePorAgente",
    "RegistroAgentes",
    "token_bearer",
    "variable_de_agente",
]
