# agent/main.py — Servidor FastAPI del agente Kallpa
# Proyecto Kallpa — Fundación Kallpa

"""
Servidor principal. Recibe mensajes de WhatsApp, genera respuestas
con Gemini y sirve el dashboard financiero por web.
"""

import os
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from dotenv import load_dotenv

from agent.brain import generar_respuesta
from agent.memory import inicializar_db, guardar_mensaje, obtener_historial
from agent.memory_negocio import (
    inicializar_db_negocio, obtener_emprendedor, crear_emprendedor,
    obtener_contexto_completo, obtener_costos, obtener_precio
)
from agent.calculadora import calcular_resumen, formatear_bolivianos
from agent.tools import ejecutar_herramienta
from agent.providers import obtener_proveedor

load_dotenv()

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
log_level = logging.DEBUG if ENVIRONMENT == "development" else logging.INFO
logging.basicConfig(level=log_level)
logger = logging.getLogger("kallpa")

proveedor = obtener_proveedor()
PORT = int(os.getenv("PORT", 8000))
BASE_URL = os.getenv("BASE_URL", f"http://localhost:{PORT}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await inicializar_db()
    await inicializar_db_negocio()
    logger.info(f"Kallpa arrancado en puerto {PORT}")
    yield


app = FastAPI(title="Kallpa — Plan de Negocios IA", version="1.0.0", lifespan=lifespan)


@app.get("/")
async def health():
    return {"status": "ok", "agente": "Kallpa", "fundacion": "Fundación Kallpa"}


@app.get("/diagnostico")
async def diagnostico():
    """Endpoint de diagnóstico — prueba la conexión a Gemini y muestra configuración."""
    import os
    from google import genai
    from google.genai import types as gtypes

    gemini_key = os.getenv("GEMINI_API_KEY", "")
    whapi_token = os.getenv("WHAPI_TOKEN", "")
    modelo = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    resultado = {
        "gemini_key_presente": bool(gemini_key),
        "gemini_key_primeros_chars": gemini_key[:12] + "..." if gemini_key else "NO CONFIGURADA",
        "whapi_token_presente": bool(whapi_token),
        "modelo": modelo,
        "base_url": os.getenv("BASE_URL", "no configurada"),
        "environment": os.getenv("ENVIRONMENT", "no configurado"),
        "gemini_test": None,
        "gemini_error": None,
    }

    if not gemini_key:
        resultado["gemini_error"] = "GEMINI_API_KEY no está configurada en las variables de entorno"
        return resultado

    try:
        test_client = genai.Client(api_key=gemini_key)
        response = await test_client.aio.models.generate_content(
            model=modelo,
            contents=[gtypes.Content(role="user", parts=[gtypes.Part(text="Di solo: OK")])]
        )
        resultado["gemini_test"] = "✅ Gemini responde correctamente"
        resultado["gemini_respuesta"] = response.candidates[0].content.parts[0].text
    except Exception as e:
        resultado["gemini_test"] = "❌ Error al conectar con Gemini"
        resultado["gemini_error"] = f"[{type(e).__name__}] {str(e)}"

    return resultado


@app.get("/webhook")
async def webhook_verificacion(request: Request):
    resultado = await proveedor.validar_webhook(request)
    if resultado is not None:
        return PlainTextResponse(str(resultado))
    return {"status": "ok"}


@app.post("/webhook")
async def webhook_handler(request: Request):
    """Recibe mensajes de WhatsApp y responde con el agente Kallpa."""
    # Parsear el webhook — si esto falla, no podemos hacer nada
    try:
        mensajes = await proveedor.parsear_webhook(request)
    except Exception as e:
        logger.error(f"Error parseando webhook: {e}", exc_info=True)
        return {"status": "ok"}

    # Procesar cada mensaje de forma independiente y resiliente
    for msg in mensajes:
        if msg.es_propio or not msg.texto:
            continue

        telefono = msg.telefono
        texto = msg.texto.strip()
        logger.info(f"[{telefono}] Mensaje recibido: {texto}")

        try:
            # Asegurar que el emprendedor existe en DB
            emp = await obtener_emprendedor(telefono)
            if not emp:
                logger.info(f"[{telefono}] Usuario nuevo — creando perfil")
                await crear_emprendedor(telefono)

            # Obtener contexto completo e historial
            contexto = await obtener_contexto_completo(telefono)
            historial = await obtener_historial(telefono)

            # Generar respuesta con Gemini
            respuesta_texto, resultado_tool = await generar_respuesta(
                mensaje=texto,
                historial=historial,
                contexto=contexto,
                ejecutar_herramienta=lambda n, a: ejecutar_herramienta(n, a, telefono)
            )

            # Guardar en historial
            await guardar_mensaje(telefono, "user", texto)
            await guardar_mensaje(telefono, "assistant", respuesta_texto)

            # Enviar respuesta de texto
            enviado = await proveedor.enviar_mensaje(telefono, respuesta_texto)
            if enviado:
                logger.info(f"[{telefono}] Whapi ACEPTÓ el envío")
            else:
                logger.error(
                    f"[{telefono}] Whapi RECHAZÓ el envío — revisar plan/restricciones "
                    f"de Whapi para este número"
                )

            # Si el dashboard fue solicitado, enviar también el resumen y el link
            if resultado_tool and resultado_tool.get("necesita_enviar_dashboard"):
                resumen_wa = resultado_tool.get("resumen_whatsapp", "")
                if resumen_wa:
                    await proveedor.enviar_mensaje(telefono, resumen_wa)
                url_dashboard = f"{BASE_URL}/dashboard/{telefono}"
                await proveedor.enviar_mensaje(
                    telefono,
                    f"📲 *Ver dashboard completo:*\n{url_dashboard}"
                )

            logger.info(f"[{telefono}] Respuesta enviada OK")

        except Exception as e:
            # Un error en un mensaje no debe tumbar todo el webhook
            logger.error(f"[{telefono}] Error procesando mensaje: {e}", exc_info=True)
            # Intentar avisar al usuario aunque algo haya fallado
            try:
                await proveedor.enviar_mensaje(
                    telefono,
                    "Tuve un problemita técnico. Intenta de nuevo en un momento."
                )
            except Exception as e2:
                logger.error(f"[{telefono}] No se pudo ni enviar el mensaje de error: {e2}")

    # Siempre devolver 200 para que Whapi no reintente indefinidamente
    return {"status": "ok"}


@app.get("/dashboard/{telefono}", response_class=HTMLResponse)
async def dashboard(telefono: str):
    """Dashboard financiero visual del emprendedor."""
    try:
        ctx = await obtener_contexto_completo(telefono)

        if ctx["es_nuevo"] or not ctx["nombre_negocio"]:
            return HTMLResponse("<h2>Este emprendedor aún no tiene datos registrados.</h2>", status_code=404)

        costos = await obtener_costos(telefono)
        precio_cfg = await obtener_precio(telefono)

        if not costos:
            return HTMLResponse(
                f"<h2>Hola {ctx['nombre_emprendedor']}! Aún no tienes costos registrados. "
                f"Escríbele a {ctx['nombre_agente']} en WhatsApp para empezar.</h2>"
            )

        costos_dict = [{"nombre": c.nombre, "monto": c.monto, "tipo": c.tipo, "categoria": c.categoria or "general"} for c in costos]
        precio_actual = precio_cfg.precio_actual if precio_cfg else 0
        unidades_mes = precio_cfg.unidades_mes if precio_cfg else 0

        resumen = calcular_resumen(costos_dict, precio_actual, unidades_mes)

        # ── Construir filas de costos ──────────────────────
        filas = ""
        for c in costos_dict:
            badge = "badge-fijo" if c["tipo"] == "fijo" else "badge-variable"
            filas += f"""<tr>
                <td>{c['nombre']}</td>
                <td><span class="badge {badge}">{c['tipo'].upper()}</span></td>
                <td>{c['categoria']}</td>
                <td style="text-align:right">{c['monto']:,.2f}</td>
            </tr>"""

        # ── Clases CSS según salud ──────────────────────────
        margen = resumen["margen_ganancia"]
        clase_margen = "highlight" if margen >= 20 else ("warning" if margen >= 5 else "danger")
        clase_utilidad = "highlight" if resumen["utilidad_mes"] > 0 else "danger"

        ps = resumen["precio_sugerido"]
        pa = resumen["precio_actual"]
        if pa > 0 and pa >= ps * 0.95:
            clase_ps = "highlight"
            dif_texto = "✅ Tu precio está bien"
        elif pa > 0:
            dif_texto = f"⬆️ Subir Bs. {(ps - pa):,.2f} para alcanzar el margen objetivo"
            clase_ps = "warning"
        else:
            dif_texto = "Precio no registrado"
            clase_ps = ""

        # ── Interpretación automática ───────────────────────
        nombre_agente = ctx["nombre_agente"]
        nombre_negocio = ctx["nombre_negocio"]
        pe_u = resumen["punto_equilibrio_unidades"]

        if margen >= 20:
            interpretacion = (
                f"¡Excelente trabajo, {ctx['nombre_emprendedor']}! Tu negocio {nombre_negocio} tiene "
                f"un margen de ganancia saludable del {margen:.1f}%. "
                f"Necesitas vender al menos {pe_u:.0f} unidades al mes para cubrir todos tus costos. "
                f"Sigue así y considera reinvertir parte de tus ganancias para crecer."
            )
        elif margen >= 5:
            interpretacion = (
                f"Tu negocio {nombre_negocio} está en camino, pero hay oportunidades de mejora. "
                f"Con un margen del {margen:.1f}%, te recomendamos revisar si puedes reducir algún costo "
                f"o ajustar el precio hacia los Bs. {ps:,.2f} sugeridos. "
                f"Tu punto de equilibrio es {pe_u:.0f} unidades/mes."
            )
        else:
            interpretacion = (
                f"Atención: con el precio actual, {nombre_negocio} tiene un margen bajo del {margen:.1f}%. "
                f"Es importante revisar tus costos y considerar subir el precio a Bs. {ps:,.2f} "
                f"para alcanzar un margen saludable del 30%. "
                f"Habla con {nombre_agente} en WhatsApp para explorar opciones."
            )

        # ── Cargar template HTML ────────────────────────────
        with open("templates/dashboard.html", "r", encoding="utf-8") as f:
            html = f.read()

        pe_u_str = f"{pe_u:.0f}" if pe_u != float("inf") else "∞"
        pe_m_str = f"{resumen['punto_equilibrio_monto']:,.2f}" if resumen["punto_equilibrio_monto"] != float("inf") else "∞"

        html = (html
            .replace("{{nombre_negocio}}", nombre_negocio)
            .replace("{{nombre_agente}}", nombre_agente)
            .replace("{{salud}}", resumen["salud"])
            .replace("{{salud_emoji}}", resumen["salud_emoji"])
            .replace("{{salud_texto}}", resumen["salud"].upper())
            .replace("{{margen_ganancia}}", f"{margen:.1f}")
            .replace("{{total_fijos}}", f"{resumen['total_fijos']:,.2f}")
            .replace("{{n_fijos}}", str(len(resumen["costos_fijos"])))
            .replace("{{cv_unitario}}", f"{resumen['cv_unitario']:,.2f}")
            .replace("{{n_variables}}", str(len(resumen["costos_variables"])))
            .replace("{{precio_actual}}", f"{precio_actual:,.2f}")
            .replace("{{precio_sugerido}}", f"{ps:,.2f}")
            .replace("{{margen_objetivo}}", f"{resumen['margen_objetivo']:.0f}")
            .replace("{{diferencia_precio}}", dif_texto)
            .replace("{{clase_precio_sugerido}}", clase_ps)
            .replace("{{clase_margen}}", clase_margen)
            .replace("{{punto_equilibrio}}", pe_u_str)
            .replace("{{pe_monto}}", pe_m_str)
            .replace("{{utilidad_mes}}", f"{resumen['utilidad_mes']:,.2f}")
            .replace("{{clase_utilidad}}", clase_utilidad)
            .replace("{{unidades_mes}}", f"{unidades_mes:.0f}")
            .replace("{{filas_costos}}", filas)
            .replace("{{interpretacion}}", interpretacion)
            .replace("{{fecha}}", datetime.now().strftime("%d/%m/%Y %H:%M"))
        )

        return HTMLResponse(html)

    except Exception as e:
        logger.error(f"Error en dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))
