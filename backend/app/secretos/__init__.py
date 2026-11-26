"""Módulo 2: Secret Broker (SPEC-0003). Los demás módulos y `main` usan solo esto."""

from app.secretos.broker import SecretBroker, crear_broker
from app.secretos.rutas import router

__all__ = ["SecretBroker", "crear_broker", "router"]
