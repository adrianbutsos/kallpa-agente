# tests/test_local.py — Simulador de chat local para Kallpa
# Proyecto Kallpa — Fundación Kallpa

"""
Prueba el agente Kallpa en la terminal sin necesitar WhatsApp.
Simula la conversación completa de plan de negocios.
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.brain import generar_respuesta
from agent.memory import inicializar_db, guardar_mensaje, obtener_historial, limpiar_historial
from agent.memory_negocio import (
    inicializar_db_negocio, obtener_emprendedor, crear_emprendedor,
    obtener_contexto_completo
)
from agent.tools import ejecutar_herramienta

TELEFONO_TEST = "test-kallpa-001"


async def main():
    await inicializar_db()
    await inicializar_db_negocio()

    # Asegurar que el emprendedor de prueba existe
    emp = await obtener_emprendedor(TELEFONO_TEST)
    if not emp:
        await crear_emprendedor(TELEFONO_TEST)

    print()
    print("=" * 60)
    print("   Kallpa — Simulador de Plan de Negocios")
    print("   Fundación Kallpa")
    print("=" * 60)
    print()
    print("  Escribe como si fueras un emprendedor.")
    print("  Comandos especiales:")
    print("    'limpiar'  — borra historial y datos")
    print("    'dashboard'— muestra URL del dashboard")
    print("    'salir'    — termina el test")
    print()
    print("  Prueba escribir algo como:")
    print("  'Hola, quiero registrar los costos de mi negocio'")
    print()
    print("-" * 60)
    print()

    while True:
        try:
            mensaje = input("Tú: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nTest finalizado.")
            break

        if not mensaje:
            continue

        if mensaje.lower() == "salir":
            print("\nTest finalizado.")
            break

        if mensaje.lower() == "limpiar":
            await limpiar_historial(TELEFONO_TEST)
            print("[Historial borrado. Reinicia para limpiar también los datos del negocio]\n")
            continue

        if mensaje.lower() == "dashboard":
            print(f"\n🌐 Dashboard: http://localhost:8000/dashboard/{TELEFONO_TEST}\n")
            continue

        # Obtener contexto y historial
        contexto = await obtener_contexto_completo(TELEFONO_TEST)
        historial = await obtener_historial(TELEFONO_TEST)

        # Generar respuesta
        print(f"\n{contexto.get('nombre_agente', 'Kallpa')}: ", end="", flush=True)

        respuesta_texto, resultado_tool = await generar_respuesta(
            mensaje=mensaje,
            historial=historial,
            contexto=contexto,
            ejecutar_herramienta=lambda n, a: ejecutar_herramienta(n, a, TELEFONO_TEST)
        )

        print(respuesta_texto)

        # Mostrar resumen si se generó dashboard
        if resultado_tool and resultado_tool.get("necesita_enviar_dashboard"):
            print()
            print("─" * 60)
            print(resultado_tool.get("resumen_whatsapp", ""))
            print("─" * 60)
            print(f"🌐 Dashboard: http://localhost:8000/dashboard/{TELEFONO_TEST}")

        print()

        # Guardar en historial
        await guardar_mensaje(TELEFONO_TEST, "user", mensaje)
        await guardar_mensaje(TELEFONO_TEST, "assistant", respuesta_texto)


if __name__ == "__main__":
    asyncio.run(main())
