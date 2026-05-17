# agent/brain.py — Cerebro del agente Kallpa con Google Gemini
# Proyecto Kallpa — Fundación Kallpa

"""
Lógica de IA del agente usando Google Gemini.
Soporta Function Calling para registrar costos, precios y generar análisis.
"""

import os
import yaml
import logging
from typing import Callable
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("kallpa")

# Cliente Gemini — usa v1beta para mayor estabilidad en producción
_api_key = os.getenv("GEMINI_API_KEY")
if not _api_key:
    logger.critical("GEMINI_API_KEY no está configurada. El agente no podrá responder.")

client = genai.Client(
    api_key=_api_key,
    http_options=types.HttpOptions(api_version="v1alpha")
)

# gemini-2.5-flash — modelo que funciona con esta cuenta
MODELO = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def cargar_config_prompts() -> dict:
    """Lee la configuración desde config/prompts.yaml."""
    try:
        with open("config/prompts.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.error("config/prompts.yaml no encontrado")
        return {}


def construir_system_prompt(contexto: dict) -> str:
    """
    Construye el system prompt dinámico con los datos actuales del emprendedor.
    Esto permite que Gemini siempre tenga contexto fresco.
    """
    config = cargar_config_prompts()
    template = config.get("system_prompt", "Eres un asistente de plan de negocios. Responde en español.")

    nombre_agente = contexto.get("nombre_agente", "Kallpa")

    # ── Estado del emprendedor ──────────────────────────────
    if contexto.get("es_nuevo") or not contexto.get("nombre_emprendedor"):
        estado = "NUEVO USUARIO — No tiene perfil aún. Preséntate y pide su nombre y el nombre de su negocio."
    elif not contexto.get("costos"):
        estado = f"Emprendedor: {contexto['nombre_emprendedor']} | Negocio: {contexto['nombre_negocio']} | AÚN NO tiene costos registrados."
    else:
        n_costos = len(contexto["costos"])
        estado = f"Emprendedor: {contexto['nombre_emprendedor']} | Negocio: {contexto['nombre_negocio']} | Costos registrados: {n_costos}"

    # ── Lista de costos ─────────────────────────────────────
    costos = contexto.get("costos", [])
    if costos:
        fijos = [c for c in costos if c["tipo"] == "fijo"]
        variables = [c for c in costos if c["tipo"] == "variable"]
        lineas_costos = []
        if fijos:
            lineas_costos.append("FIJOS:")
            for c in fijos:
                lineas_costos.append(f"  - {c['nombre']}: Bs. {c['monto']}")
        if variables:
            lineas_costos.append("VARIABLES (por unidad/mes):")
            for c in variables:
                lineas_costos.append(f"  - {c['nombre']}: Bs. {c['monto']}")
        costos_registrados = "\n".join(lineas_costos)
    else:
        costos_registrados = "Ninguno aún."

    # ── Info de precio ──────────────────────────────────────
    precio = contexto.get("precio_actual", 0)
    unidades = contexto.get("unidades_mes", 0)
    if precio > 0:
        info_precio = f"Precio actual: Bs. {precio} | Unidades/mes: {unidades}"
    else:
        info_precio = "No registrado aún."

    # Reemplazar variables en el template
    system_prompt = template.format(
        nombre_agente=nombre_agente,
        estado_emprendedor=estado,
        costos_registrados=costos_registrados,
        info_precio=info_precio
    )

    return system_prompt


async def generar_respuesta(
    mensaje: str,
    historial: list[dict],
    contexto: dict,
    ejecutar_herramienta: Callable
) -> tuple[str, dict | None]:
    """
    Genera una respuesta usando Gemini con Function Calling.

    Args:
        mensaje: Mensaje nuevo del usuario
        historial: Historial de conversación
        contexto: Datos del emprendedor (nombre, costos, precio, etc.)
        ejecutar_herramienta: Función async para ejecutar las tools

    Returns:
        Tuple (texto_respuesta, resultado_tool)
        resultado_tool es None si no se ejecutó ninguna tool
    """
    if not mensaje or len(mensaje.strip()) < 2:
        config = cargar_config_prompts()
        return config.get("fallback_message", "Disculpa, no entendí. ¿Puedes repetirlo?"), None

    system_prompt = construir_system_prompt(contexto)

    try:
        from agent.tools import HERRAMIENTAS_GEMINI

        # Construir historial en formato del nuevo SDK
        contents = []
        for msg in historial:
            role = "user" if msg["role"] == "user" else "model"
            contents.append(types.Content(
                role=role,
                parts=[types.Part(text=msg["content"])]
            ))
        # Agregar mensaje actual
        contents.append(types.Content(
            role="user",
            parts=[types.Part(text=mensaje)]
        ))

        config_gen = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=HERRAMIENTAS_GEMINI,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True)
        )

        resultado_tool = None
        max_iteraciones = 5

        for _ in range(max_iteraciones):
            response = await client.aio.models.generate_content(
                model=MODELO,
                contents=contents,
                config=config_gen
            )

            # Verificar function calls
            tiene_function_call = False
            for part in response.candidates[0].content.parts:
                if part.function_call:
                    tiene_function_call = True
                    func_name = part.function_call.name
                    func_args = dict(part.function_call.args)

                    logger.info(f"Gemini llama: {func_name}({func_args})")

                    resultado = await ejecutar_herramienta(func_name, func_args)
                    resultado_tool = resultado

                    logger.info(f"Resultado: {resultado}")

                    # Agregar respuesta del modelo y resultado de la tool al historial
                    contents.append(response.candidates[0].content)
                    contents.append(types.Content(
                        role="user",
                        parts=[types.Part(
                            function_response=types.FunctionResponse(
                                name=func_name,
                                response=resultado
                            )
                        )]
                    ))
                    break

            if not tiene_function_call:
                break

        # Extraer texto final
        texto = ""
        for part in response.candidates[0].content.parts:
            if part.text:
                texto += part.text

        if not texto:
            config = cargar_config_prompts()
            texto = config.get("error_message", "Lo siento, tuve un problema. Intenta de nuevo.")

        return texto, resultado_tool

    except Exception as e:
        logger.error(f"Error Gemini API [{type(e).__name__}]: {e}", exc_info=True)
        config = cargar_config_prompts()
        return config.get("error_message", "Lo siento, tuve un problema técnico."), None
