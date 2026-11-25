"""SPEC-0003 E16, E17 y reglas de arquitectura: límite, endurecimiento y `httpx` aislado."""

import ast
import sys
from pathlib import Path

import pytest

from app.arranque import puerto
from app.core.endurecer import endurecer_proceso
from app.secretos.limite import LimitePorAgente

APP = Path(__file__).resolve().parents[1] / "app"


def test_spec0003_e16_ventana_deslizante() -> None:
    ahora = [1000.0]
    limite = LimitePorAgente(reloj=lambda: ahora[0])
    assert limite.permitir("a", 2) is None
    assert limite.permitir("a", 2) is None
    espera = limite.permitir("a", 2)
    assert espera is not None and espera == pytest.approx(60)
    assert limite.permitir("b", 2) is None  # cada agente con su propio límite
    ahora[0] += 60
    assert limite.permitir("a", 2) is None  # la ventana se liberó


@pytest.mark.skipif(sys.platform != "linux", reason="RLIMIT_CORE y prctl solo existen en Linux")
def test_spec0003_e17_endurecer_en_linux() -> None:
    if sys.platform == "linux":  # mypy: `resource` solo existe en Linux
        import resource

        aplicado = endurecer_proceso()
        assert "sin-core-dumps" in aplicado
        assert resource.getrlimit(resource.RLIMIT_CORE) == (0, 0)


@pytest.mark.skipif(sys.platform == "linux", reason="comprueba el camino de otros sistemas")
def test_spec0003_e17_endurecer_fuera_de_linux_no_falla() -> None:
    assert endurecer_proceso() == []


def test_spec0003_e17_puerto() -> None:
    assert puerto({}) == 8000
    assert puerto({"PORT": "9000"}) == 9000
    for malo in ("0", "70000", "8000; rm -rf /", ""):
        with pytest.raises(SystemExit):
            puerto({"PORT": malo})


def test_spec0003_httpx_solo_en_el_ejecutor() -> None:
    permitido = APP / "secretos" / "ejecutor.py"
    infractores = []
    for archivo in APP.rglob("*.py"):
        arbol = ast.parse(archivo.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            modulos = (
                [alias.name for alias in nodo.names]
                if isinstance(nodo, ast.Import)
                else [nodo.module or ""]
                if isinstance(nodo, ast.ImportFrom)
                else []
            )
            if any(m.split(".")[0] == "httpx" for m in modulos) and archivo != permitido:
                infractores.append(str(archivo.relative_to(APP)))
    assert infractores == []
