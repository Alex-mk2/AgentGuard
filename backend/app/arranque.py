"""Punto de entrada de la imagen: `python -m app.arranque` (SPEC-0003 E17).

Reemplaza al `sh -c "exec uvicorn ..."`: la app ya no necesita una shell para arrancar. Endurece el
proceso antes de cargar cualquier secreto y lanza uvicorn con un solo worker (los límites y el
estado viven en memoria, SPEC-0001) y sin su log de acceso, que registra la IP (RF-08).
"""

import logging
import os

import uvicorn

from app.core.endurecer import endurecer_proceso

logger = logging.getLogger("agentguard.arranque")


def puerto(entorno: dict[str, str] | None = None) -> int:
    valor = (entorno if entorno is not None else dict(os.environ)).get("PORT", "8000")
    if not valor.isdigit() or not 1 <= int(valor) <= 65535:
        raise SystemExit("PORT debe ser un número entre 1 y 65535")
    return int(valor)


def main() -> None:
    aplicado = endurecer_proceso()
    logging.basicConfig(level=logging.INFO)
    logger.info("Proceso endurecido: %s", ", ".join(aplicado) or "nada (no es Linux)")
    uvicorn.run(
        "app.main:crear_app",
        factory=True,
        # Dentro del contenedor debe escuchar en todas las interfaces; afuera, compose solo
        # publica el puerto en 127.0.0.1.
        host="0.0.0.0",  # nosec B104
        port=puerto(),
        workers=1,
        access_log=False,
    )


if __name__ == "__main__":
    main()
