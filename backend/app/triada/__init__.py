"""Módulo 1: Detector de la Tríada Letal (SPEC-0002). Los demás módulos usan solo esto."""

from app.triada.analisis import analizar
from app.triada.rutas import router

__all__ = ["analizar", "router"]
