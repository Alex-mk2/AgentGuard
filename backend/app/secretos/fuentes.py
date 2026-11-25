"""De dónde salen los secretos (SPEC-0003 RF-02, RF-08, D-01).

`FuenteSecretos` es la interfaz: un gestor externo o credenciales de vida corta (specs futuras) se
suman como otra fuente sin tocar el broker. Esta spec trae `FuenteEntorno`.
"""

import logging
from collections.abc import Mapping, MutableMapping
from typing import Protocol

from pydantic import SecretStr

logger = logging.getLogger("agentguard.secretos")

PREFIJO_SECRETO = "AGENTGUARD_SECRETO_"
MINIMO_CARACTERES = 8  # caso borde: limpiar uno más corto borraría texto legítimo, y es débil


class FuenteSecretos(Protocol):
    async def obtener(self, nombre: str) -> SecretStr | None:
        """El secreto en el momento de usarlo; `None` si no está disponible."""
        ...

    def nombres(self) -> frozenset[str]:
        """Los nombres disponibles. Nunca los valores."""
        ...


class FuenteEntorno:
    """`AGENTGUARD_SECRETO_GITHUB_TOKEN` → secreto `github_token`.

    Se leen una vez al crear la fuente. Si el entorno es mutable (el `os.environ` real), las
    variables se retiran después de leerlas: ni un subproceso ni un volcado de `os.environ` las ve.
    """

    def __init__(self, entorno: Mapping[str, str]) -> None:
        self._secretos: dict[str, SecretStr] = {}
        self.rechazados: frozenset[str] = frozenset()
        rechazados: set[str] = set()
        for variable in [v for v in entorno if v.startswith(PREFIJO_SECRETO)]:
            nombre = variable.removeprefix(PREFIJO_SECRETO).lower()
            valor = entorno[variable]
            if isinstance(entorno, MutableMapping):
                del entorno[variable]
            if not valor:
                continue  # vacío = no cargado (caso borde)
            if len(valor) < MINIMO_CARACTERES or "\r" in valor or "\n" in valor:
                # Solo el nombre de la variable: nunca el valor ni su largo.
                logger.warning("Se ignora %s: muy corto o con saltos de línea", variable)
                rechazados.add(nombre)
                continue
            self._secretos[nombre] = SecretStr(valor)
        self.rechazados = frozenset(rechazados)

    async def obtener(self, nombre: str) -> SecretStr | None:
        return self._secretos.get(nombre)

    def nombres(self) -> frozenset[str]:
        return frozenset(self._secretos)

    def __repr__(self) -> str:
        return f"FuenteEntorno(nombres={sorted(self._secretos)})"
