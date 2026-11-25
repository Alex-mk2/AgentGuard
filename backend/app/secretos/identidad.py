"""Tokens de agente y de administración (SPEC-0003 H2, RF-04, E4).

Se guardan como SHA-256 y se comparan en tiempo constante contra **todos** los agentes, sin cortar
al primero que calce: el tiempo de respuesta no dice si un agente existe. Los tokens son aleatorios
y largos, así que no hace falta un hash lento (bcrypt).
"""

import hashlib
import hmac
import logging
from collections.abc import Mapping, MutableMapping, Sequence

from app.secretos.config import Agente

logger = logging.getLogger("agentguard.secretos")

PREFIJO_AGENTE = "AGENTGUARD_AGENTE_"
VARIABLE_ADMIN = "AGENTGUARD_ADMIN_TOKEN"
MINIMO_TOKEN = 16
_RELLENO = hashlib.sha256(b"agentguard: agente sin token cargado").digest()


def variable_de_agente(id_agente: str) -> str:
    """`soporte-web` → `AGENTGUARD_AGENTE_SOPORTE_WEB`."""
    return PREFIJO_AGENTE + id_agente.upper().replace("-", "_")


def _hash(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()


def _leer(entorno: Mapping[str, str], variable: str) -> bytes | None:
    valor = entorno.get(variable, "")
    if isinstance(entorno, MutableMapping) and variable in entorno:
        del entorno[variable]  # igual que los secretos: no queda en os.environ
    if not valor:
        return None
    if len(valor) < MINIMO_TOKEN:
        logger.warning(
            "Se ignora %s: el token debe tener al menos %d caracteres", variable, MINIMO_TOKEN
        )
        return None
    return _hash(valor)


class Identidades:
    def __init__(self, agentes: Sequence[Agente], entorno: Mapping[str, str]) -> None:
        self._agentes: dict[str, bytes | None] = {
            agente.id: _leer(entorno, variable_de_agente(agente.id)) for agente in agentes
        }
        self._admin = _leer(entorno, VARIABLE_ADMIN)

    def agente(self, token: str | None) -> str | None:
        """El id del agente dueño del token, o `None`."""
        recibido = _hash(token or "")
        encontrado: str | None = None
        for id_agente, guardado in self._agentes.items():
            # Sin `break` y con relleno para los agentes sin token: mismo trabajo en todo caso.
            coincide = hmac.compare_digest(recibido, guardado or _RELLENO)
            if coincide and guardado is not None and token:
                encontrado = id_agente
        return encontrado

    def es_admin(self, token: str | None) -> bool:
        coincide = hmac.compare_digest(_hash(token or ""), self._admin or _RELLENO)
        return coincide and self._admin is not None and bool(token)

    def token_cargado(self, id_agente: str) -> bool:
        return self._agentes.get(id_agente) is not None

    @property
    def admin_cargado(self) -> bool:
        return self._admin is not None
