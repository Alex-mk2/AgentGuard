"""SPEC-0001 RF-05: solo `app/base` importa `asyncpg` (context.md §2)."""

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"


def _modulos_importados(archivo: Path) -> set[str]:
    arbol = ast.parse(archivo.read_text(encoding="utf-8"))
    nombres: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            nombres.update(alias.name.split(".")[0] for alias in nodo.names)
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            nombres.add(nodo.module.split(".")[0])
    return nombres


def test_spec0001_rf05_asyncpg_solo_en_base() -> None:
    infractores = [
        str(archivo.relative_to(APP))
        for archivo in APP.rglob("*.py")
        if "asyncpg" in _modulos_importados(archivo) and archivo.parent.name != "base"
    ]
    assert infractores == []
