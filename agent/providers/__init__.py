# agent/providers/__init__.py — Factory de proveedores — Kallpa
import os
from agent.providers.base import ProveedorWhatsApp

def obtener_proveedor() -> ProveedorWhatsApp:
    proveedor = os.getenv("WHATSAPP_PROVIDER", "whapi").lower()
    if proveedor == "whapi":
        from agent.providers.whapi import ProveedorWhapi
        return ProveedorWhapi()
    else:
        raise ValueError(f"Proveedor no soportado: {proveedor}")
