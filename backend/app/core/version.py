"""Versión de la app para la página de estado (SPEC-0001 RF-10)."""

import tomllib
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def leer_version(pyproject: Path = PYPROJECT) -> str:
    """La versión de `pyproject.toml`, o `desconocida` si el archivo no está."""
    try:
        with pyproject.open("rb") as archivo:
            return str(tomllib.load(archivo)["project"]["version"])
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "desconocida"


class Version(BaseModel):
    version: str


router = APIRouter(tags=["salud"])
VERSION = leer_version()


@router.get("/version")
async def version() -> Version:
    return Version(version=VERSION)
