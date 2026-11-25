"""Acceso a PostgreSQL. Los demás módulos usan solo lo que se exporta aquí."""

from app.base.conexion import ConexionPostgres

__all__ = ["ConexionPostgres"]
