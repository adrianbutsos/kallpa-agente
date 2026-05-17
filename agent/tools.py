# agent/tools.py — Ejecución de herramientas del agente Kallpa
# Proyecto Kallpa — Fundación Kallpa

"""
Funciones que Gemini puede llamar via Function Calling.
Cada función interactúa con la base de datos y retorna
un resultado que Gemini usa para continuar la conversación.
"""

import logging
from agent.memory_negocio import (
    actualizar_nombre_agente,
    actualizar_perfil,
    registrar_costo as db_registrar_costo,
    guardar_precio,
    obtener_contexto_completo,
)
from agent.calculadora import calcular_resumen, generar_resumen_whatsapp

logger = logging.getLogger("kallpa")


async def ejecutar_herramienta(nombre: str, args: dict, telefono: str) -> dict:
    """
    Ejecuta la herramienta solicitada por Gemini y retorna el resultado.

    Args:
        nombre: Nombre de la función a ejecutar
        args: Argumentos de la función
        telefono: Teléfono del emprendedor

    Returns:
        Diccionario con el resultado para enviar de vuelta a Gemini
    """
    try:
        if nombre == "registrar_perfil_emprendedor":
            await actualizar_perfil(
                telefono=telefono,
                nombre_emprendedor=args.get("nombre_emprendedor", ""),
                nombre_negocio=args.get("nombre_negocio", "")
            )
            return {
                "exito": True,
                "mensaje": f"Perfil guardado: {args.get('nombre_emprendedor')} — {args.get('nombre_negocio')}"
            }

        elif nombre == "registrar_costo":
            await db_registrar_costo(
                telefono=telefono,
                nombre=args.get("nombre", ""),
                monto=float(args.get("monto", 0)),
                tipo=args.get("tipo", "fijo"),
                categoria=args.get("categoria", "general")
            )
            return {
                "exito": True,
                "tipo": args.get("tipo"),
                "mensaje": f"Costo '{args.get('nombre')}' de Bs. {args.get('monto')} registrado como {args.get('tipo')}"
            }

        elif nombre == "registrar_precio_venta":
            await guardar_precio(
                telefono=telefono,
                precio_actual=float(args.get("precio_actual", 0)),
                unidades_mes=float(args.get("unidades_mes", 0))
            )
            return {
                "exito": True,
                "mensaje": f"Precio Bs. {args.get('precio_actual')} y {args.get('unidades_mes')} unidades/mes guardados"
            }

        elif nombre == "mostrar_dashboard":
            # Obtener datos completos y calcular
            ctx = await obtener_contexto_completo(telefono)
            if not ctx["costos"]:
                return {
                    "exito": False,
                    "mensaje": "Aún no hay costos registrados para calcular el análisis"
                }
            resumen = calcular_resumen(
                costos=ctx["costos"],
                precio_actual=ctx["precio_actual"],
                unidades_mes=ctx["unidades_mes"]
            )
            texto_wa = generar_resumen_whatsapp(
                resumen=resumen,
                nombre_agente=ctx["nombre_agente"],
                nombre_negocio=ctx["nombre_negocio"] or "tu negocio"
            )
            return {
                "exito": True,
                "resumen_whatsapp": texto_wa,
                "margen": resumen["margen_ganancia"],
                "salud": resumen["salud"],
                "precio_sugerido": resumen["precio_sugerido"],
                "punto_equilibrio": resumen["punto_equilibrio_unidades"],
                "necesita_enviar_dashboard": True
            }

        else:
            return {"exito": False, "mensaje": f"Herramienta '{nombre}' no reconocida"}

    except Exception as e:
        logger.error(f"Error ejecutando herramienta {nombre}: {e}")
        return {"exito": False, "error": str(e)}


# ── Definición de herramientas para Gemini (nuevo SDK google-genai) ──────────

from google.genai import types as genai_types

HERRAMIENTAS_GEMINI = [
    genai_types.Tool(
        function_declarations=[
            genai_types.FunctionDeclaration(
                name="registrar_perfil_emprendedor",
                description="Guarda el nombre del emprendedor y el nombre de su negocio en la base de datos.",
                parameters=genai_types.Schema(
                    type=genai_types.Type.OBJECT,
                    properties={
                        "nombre_emprendedor": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description="Nombre propio del emprendedor"
                        ),
                        "nombre_negocio": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description="Nombre del negocio o emprendimiento"
                        ),
                    },
                    required=["nombre_emprendedor", "nombre_negocio"]
                )
            ),
            genai_types.FunctionDeclaration(
                name="registrar_costo",
                description="Registra un costo del emprendimiento clasificándolo como fijo o variable.",
                parameters=genai_types.Schema(
                    type=genai_types.Type.OBJECT,
                    properties={
                        "nombre": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description="Nombre descriptivo del costo (ej: Alquiler del local, Harina)"
                        ),
                        "monto": genai_types.Schema(
                            type=genai_types.Type.NUMBER,
                            description="Monto en bolivianos"
                        ),
                        "tipo": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description="fijo = no cambia con producción; variable = cambia según producción",
                            enum=["fijo", "variable"]
                        ),
                        "categoria": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description="Categoría del costo (ej: operativo, insumos, personal, servicios)"
                        ),
                    },
                    required=["nombre", "monto", "tipo"]
                )
            ),
            genai_types.FunctionDeclaration(
                name="registrar_precio_venta",
                description="Registra el precio de venta actual del producto/servicio y las unidades vendidas por mes.",
                parameters=genai_types.Schema(
                    type=genai_types.Type.OBJECT,
                    properties={
                        "precio_actual": genai_types.Schema(
                            type=genai_types.Type.NUMBER,
                            description="Precio de venta actual por unidad en bolivianos"
                        ),
                        "unidades_mes": genai_types.Schema(
                            type=genai_types.Type.NUMBER,
                            description="Cantidad de unidades vendidas o producidas por mes"
                        ),
                    },
                    required=["precio_actual", "unidades_mes"]
                )
            ),
            genai_types.FunctionDeclaration(
                name="mostrar_dashboard",
                description="Calcula y muestra el análisis financiero completo: costos, margen, punto de equilibrio y precio sugerido.",
                parameters=genai_types.Schema(
                    type=genai_types.Type.OBJECT,
                    properties={}
                )
            ),
        ]
    )
]
