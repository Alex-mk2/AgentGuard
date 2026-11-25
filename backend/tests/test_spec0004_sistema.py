"""SPEC-0004, arquitectura: dependencias en un solo sentido (`secretos → egresos → agentes`) y
ningún módulo entra al interior de otro (context.md §2)."""

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
MODULOS = ("agentes", "egresos", "secretos", "triada")


def _importados(archivo: Path) -> set[str]:
    importados: set[str] = set()
    for nodo in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"))):
        if isinstance(nodo, ast.Import):
            importados |= {alias.name for alias in nodo.names}
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            importados.add(nodo.module)
    return importados


def test_spec0004_dependencias_en_un_sentido() -> None:
    prohibido = {
        "agentes": {"egresos", "secretos", "triada"},
        "egresos": {"secretos", "triada"},
        "secretos": {"triada"},
        "triada": {"agentes", "egresos", "secretos"},
    }
    infractores = []
    for modulo, vetados in prohibido.items():
        for archivo in (APP / modulo).rglob("*.py"):
            for importado in _importados(archivo):
                partes = importado.split(".")
                if partes[0] == "app" and len(partes) > 1 and partes[1] in vetados:
                    infractores.append(f"{archivo.relative_to(APP)} → {importado}")
    assert infractores == []


def test_spec0004_solo_lo_publico_de_otro_modulo() -> None:
    """Desde otro módulo (o `main`) se importa `app.<modulo>`, nunca `app.<modulo>.<interior>`."""
    infractores = []
    for archivo in APP.rglob("*.py"):
        propio = archivo.relative_to(APP).parts[0]
        for importado in _importados(archivo):
            partes = importado.split(".")
            if (
                partes[0] == "app"
                and len(partes) > 2
                and partes[1] in MODULOS
                and partes[1] != propio
            ):
                infractores.append(f"{archivo.relative_to(APP)} → {importado}")
    assert infractores == []
