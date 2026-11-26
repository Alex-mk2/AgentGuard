"""Configuración tipada desde variables de entorno y `.env` (SPEC-0001 RF-01 y RF-02)."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ_REPO = Path(__file__).resolve().parents[3]
# El .env vive en la raíz del repo. En la imagen no existe: valen solo las variables de entorno.
ENV_RAIZ = RAIZ_REPO / ".env"


class ConfiguracionInvalida(Exception):
    """Falta una variable o tiene un valor inválido. El mensaje nunca incluye los valores."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file_encoding="utf-8", extra="ignore")

    # Obligatoria: vacía cuenta como faltante (E4). Trae la clave de Postgres.
    database_url: SecretStr = Field(min_length=1)

    # Opcionales
    frontend_origin: str = ""  # CORS solo en desarrollo; uno o varios, separados por comas (RF-07)
    frontend_dist: Path = RAIZ_REPO / "frontend" / "dist"  # si no existe, solo se sirve la API
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Secret Broker (SPEC-0003). Sin archivo, el módulo queda apagado y responde 503.
    secretos_config: Path | None = None
    # Solo desarrollo y pruebas: permite acciones http:// hacia localhost (E8).
    secretos_http_local: bool = False

    # Control de egresos (SPEC-0004). Sin archivo, toda salida de red está bloqueada (D-01).
    egresos_config: Path | None = None

    # Contención de prompt injection (SPEC-0005). Opcional: sin archivo, valores por defecto.
    inyeccion_config: Path | None = None

    @property
    def origenes_frontend(self) -> list[str]:
        return [origen.strip() for origen in self.frontend_origin.split(",") if origen.strip()]


def cargar_settings(env_file: Path | None = ENV_RAIZ) -> Settings:
    """Lee la configuración. Relanza los errores nombrando solo la variable y el tipo de error:
    el `ValidationError` de pydantic incluye el valor recibido, y DATABASE_URL trae la clave
    (E3)."""
    try:
        return Settings(_env_file=env_file)
    except ValidationError as error:
        problemas = ", ".join(
            f"{str(detalle['loc'][0]).upper()} ({detalle['type']})"
            for detalle in error.errors(include_input=False)
        )
        raise ConfiguracionInvalida(f"Configuración inválida: {problemas}") from None
