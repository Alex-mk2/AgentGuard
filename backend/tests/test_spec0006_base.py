"""SPEC-0006: migraciones, consultas sin base y avisos de la contención al retirar una sesión."""

from pathlib import Path

import pytest
from pydantic import SecretStr

from app.base import ConexionPostgres
from app.base.migraciones import CARPETA, pendientes
from app.core.config import Settings
from app.core.errores import ServicioNoDisponible
from app.inyeccion.sesiones import Sesion, SesionDesconocida, Sesiones


def test_spec0006_d01_migraciones_en_orden(tmp_path: Path) -> None:
    for nombre in ("002_b.sql", "001_a.sql", "010_c.sql"):
        (tmp_path / nombre).write_text("SELECT 1;", encoding="utf-8")
    assert [a.name for a in pendientes(tmp_path, set())] == ["001_a.sql", "002_b.sql", "010_c.sql"]
    assert [a.name for a in pendientes(tmp_path, {"001_a.sql"})] == ["002_b.sql", "010_c.sql"]


def test_spec0006_d01_nombre_invalido_no_se_salta(tmp_path: Path) -> None:
    (tmp_path / "001_a.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "2_mal.sql").write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(ValueError, match=r"2_mal.sql"):
        pendientes(tmp_path, set())


def test_spec0006_d01_las_del_repo_tienen_buen_nombre() -> None:
    assert [a.name for a in pendientes(CARPETA, set())][:1] == ["001_aprobaciones.sql"]


async def test_spec0006_d01_sin_pool_503() -> None:
    settings = Settings(_env_file=None, database_url=SecretStr("postgresql://x@prueba.invalid/x"))
    conexion = ConexionPostgres(settings)  # nunca abierta
    with pytest.raises(ServicioNoDisponible):
        await conexion.fetch("SELECT 1")
    with pytest.raises(ServicioNoDisponible):
        await conexion.execute("SELECT 1")


class Reloj:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_spec0006_e11_avisos_al_cerrar_y_al_vencer() -> None:
    reloj = Reloj()
    sesiones = Sesiones(60, reloj)
    retiradas: list[Sesion] = []
    sesiones.al_retirar.append(retiradas.append)

    cerrada = sesiones.abrir("a", None, None)
    sesiones.cerrar(cerrada.id, "a")
    assert retiradas == [cerrada]

    vencida = sesiones.abrir("a", None, None)
    implicita = sesiones.resolver("a", None)
    reloj.t = 61
    with pytest.raises(SesionDesconocida):
        sesiones.resolver("a", vencida.id)
    nueva_implicita = sesiones.resolver("a", None)
    assert nueva_implicita is not implicita
    assert retiradas == [cerrada, vencida, implicita]

    sesiones.cerrar(nueva_implicita.id)  # administración: también la implícita
    assert retiradas[-1] is nueva_implicita


def test_spec0006_e11_un_aviso_que_falla_no_impide_cerrar() -> None:
    sesiones = Sesiones(60, Reloj())

    def roto(_: Sesion) -> None:
        raise RuntimeError("falla")

    sesiones.al_retirar.append(roto)
    sesion = sesiones.abrir("a", None, None)
    assert sesiones.cerrar(sesion.id, "a") is True
    assert list(sesiones.activas()) == []
