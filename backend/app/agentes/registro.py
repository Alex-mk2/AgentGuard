"""Registro de agentes compartido por los módulos (SPEC-0004 RF-06, E14).

Une las definiciones, los tokens y **un solo** límite por minuto: un agente no lo esquiva
repartiendo sus llamadas entre el broker y el egreso web.
"""

from collections.abc import Mapping, Sequence

from app.agentes.identidad import Identidades
from app.agentes.limite import LimitePorAgente
from app.agentes.modelo import Agente


class RegistroAgentes:
    def __init__(self, agentes: Sequence[Agente], entorno: Mapping[str, str]) -> None:
        self.definiciones: dict[str, Agente] = {agente.id: agente for agente in agentes}
        self.identidades = Identidades(agentes, entorno)
        self.limite = LimitePorAgente()

    def identificar(self, token: str | None) -> Agente | None:
        id_agente = self.identidades.agente(token)
        return None if id_agente is None else self.definiciones.get(id_agente)

    def es_admin(self, token: str | None) -> bool:
        return self.identidades.es_admin(token)

    def permitir(self, agente: Agente) -> float | None:
        """`None` si puede seguir; si no, los segundos que debe esperar (`429`)."""
        return self.limite.permitir(agente.id, agente.max_por_minuto)


def token_bearer(authorization: str | None) -> str | None:
    """El token de `Authorization: Bearer <token>`, o `None`."""
    if authorization is None:
        return None
    esquema, _, token = authorization.partition(" ")
    return token.strip() if esquema.lower() == "bearer" and token.strip() else None
