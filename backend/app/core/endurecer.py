"""Endurecimiento del proceso al arrancar (SPEC-0003 E17, RF-10).

El Secret Broker tiene secretos en memoria y Python no puede borrar un `str`. Esto cierra las dos
vías más baratas para sacarlos tras una intrusión:

- **Sin volcados de memoria** (`RLIMIT_CORE = 0`): un fallo no deja un *core dump* con los secretos.
- **Proceso no *dumpable*** (`prctl(PR_SET_DUMPABLE, 0)`): otro proceso del mismo usuario no puede
  hacerle `ptrace` ni leer `/proc/<pid>/mem` ni `/proc/<pid>/environ`.

Solo en Linux (la imagen). En otro sistema no hace nada; si algo falla, se registra y se sigue.
"""

import ctypes
import logging
import sys

logger = logging.getLogger("agentguard.endurecer")

PR_SET_DUMPABLE = 4


def endurecer_proceso() -> list[str]:
    """Devuelve lo que se aplicó, para registrarlo y probarlo."""
    if sys.platform != "linux":
        return []
    import resource

    aplicado: list[str] = []
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        aplicado.append("sin-core-dumps")
    except (OSError, ValueError) as error:
        logger.warning("No se pudo desactivar los core dumps (%s)", type(error).__name__)
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(PR_SET_DUMPABLE, 0, 0, 0, 0) == 0:
            aplicado.append("no-dumpable")
        else:
            logger.warning("prctl(PR_SET_DUMPABLE) falló (errno %d)", ctypes.get_errno())
    except (OSError, AttributeError) as error:
        logger.warning("No se pudo llamar a prctl (%s)", type(error).__name__)
    return aplicado
