# agent/manqa_demo_routes.py — Rutas de la demo de Manq'a
# Proyecto Kallpa — Demo Manq'a / Wayna Hub

import re
import csv
import io
import urllib.parse
from datetime import datetime
from fastapi import APIRouter, Form, Request, HTTPException, Response
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# Importar funciones de base de datos
from agent.manqa_demo_db import (
    registrar_mensaje,
    obtener_o_crear_emprendedor_por_telefono,
    actualizar_emprendedor_desde_mensaje,
    registrar_venta,
    registrar_refuerzo,
    registrar_asesoria,
    obtener_resumen,
    listar_emprendedores,
    listar_ultimos_mensajes,
    reset_demo_db
)

router = APIRouter()

# Configurar el motor de plantillas
templates = Jinja2Templates(directory="templates")


class MensajeJSON(BaseModel):
    telefono: str
    mensaje: str


def procesar_mensaje_texto(telefono: str, mensaje: str) -> tuple[str, str]:
    """
    Analiza el texto del mensaje entrante para clasificarlo, aplicar la lógica
    de negocio y generar una respuesta automática del bot.
    Retorna: (tipo_detectado, respuesta_bot)
    """
    telefono = telefono.strip()
    mensaje = mensaje.strip()
    mensaje_lc = mensaje.lower()
    
    # 1. Asegurar que existe el emprendedor
    emp = obtener_o_crear_emprendedor_por_telefono(telefono)
    emprendedor_id = emp["id"]
    
    # Evaluar si el perfil está incompleto (para lanzar advertencia/nota en la respuesta del bot)
    perfil_incompleto = (emp.get("nombre") == "Pendiente" or emp.get("negocio") == "Pendiente")
    
    # Registrar el mensaje del usuario en la BD (entrante)
    registrar_mensaje(telefono, mensaje, tipo="entrante", direccion="entrante")
    
    tipo_detectado = "general"
    respuesta_bot = ""
    
    # Regla 1: Registro/Actualización ("soy" o "tengo")
    if "soy" in mensaje_lc or "tengo" in mensaje_lc:
        emp_actualizado = actualizar_emprendedor_desde_mensaje(telefono, mensaje)
        nombre = emp_actualizado.get("nombre") or "Pendiente"
        negocio = emp_actualizado.get("negocio") or "Pendiente"
        tipo_detectado = "registro"
        respuesta_bot = f"👋 ¡Hola, {nombre}! He registrado tu emprendimiento de tipo '{negocio}'. Ahora podré ayudarte a registrar tus ventas, solicitar refuerzos y asesorías."
        
    # Regla 2: Ventas ("vend", "vendi", "vendí" o "venta")
    elif any(keyword in mensaje_lc for keyword in ["vend", "vendi", "vendí", "venta"]):
        # Buscar el primer número en el mensaje
        match_numero = re.search(r'\d+(?:[.,]\d+)?', mensaje)
        if match_numero:
            monto_str = match_numero.group(0).replace(",", ".")
            try:
                monto = float(monto_str)
                # Determinar mes en español
                meses = [
                    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
                    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
                ]
                mes_actual = meses[datetime.now().month - 1]
                
                registrar_venta(emprendedor_id, monto, mes_actual, observacion=mensaje)
                tipo_detectado = "venta"
                respuesta_bot = f"💰 ¡Excelente! Registré una venta de {monto:,.2f} Bs para el mes de {mes_actual}."
                if perfil_incompleto:
                    respuesta_bot += " ⚠️ Tu perfil está incompleto. Completa tu nombre y negocio escribiendo algo como: 'Hola soy Ana y tengo una pasteleria'."
            except ValueError:
                tipo_detectado = "general"
                respuesta_bot = "Parece que mencionaste una venta, pero no pude entender la cantidad. Intenta algo como: 'Vendi 2500 Bs este mes'."
        else:
            tipo_detectado = "general"
            respuesta_bot = "Parece que quieres registrar una venta. Recuerda incluir el monto. Ejemplo: 'Vendi 2500 Bs'."

    # Regla 3: Refuerzos ("apoyo", "ayuda" o "refuerzo")
    elif any(keyword in mensaje_lc for keyword in ["apoyo", "ayuda", "refuerzo"]):
        # Detectar el área
        areas_mapeo = {
            "finanzas": "Finanzas",
            "marketing": "Marketing",
            "comercializacion": "Comercialización",
            "comercialización": "Comercialización",
            "produccion": "Producción",
            "producción": "Producción",
            "ventas": "Ventas",
            "gestion": "Gestión",
            "gestión": "Gestión"
        }
        
        area_detectada = "General"
        for kw, area_nombre in areas_mapeo.items():
            if kw in mensaje_lc:
                area_detectada = area_nombre
                break
                
        registrar_refuerzo(emprendedor_id, area_detectada, motivo=mensaje, prioridad="Alta" if "urgente" in mensaje_lc else "Media")
        tipo_detectado = "refuerzo"
        # Mapeado a término institucional: "apoyo" en vez de "refuerzo" en la interacción
        respuesta_bot = f"🛠️ Registré tu solicitud de apoyo en el área de *{area_detectada}*. Un asesor de Manq'a Wayna Hub revisará tu caso."
        if perfil_incompleto:
            respuesta_bot += " ⚠️ Tu perfil está incompleto. Completa tu nombre y negocio escribiendo algo como: 'Hola soy Ana y tengo una pasteleria'."

    # Regla 4: Asesorías ("asesoria", "asesoría", "cita", "reunion" o "reunión")
    elif any(keyword in mensaje_lc for keyword in ["asesoria", "asesoría", "cita", "reunion", "reunión"]):
        registrar_asesoria(emprendedor_id, tema=mensaje, estado="Pendiente")
        tipo_detectado = "asesoria"
        respuesta_bot = f"📅 Agendé una solicitud de asesoría técnica sobre el tema: '{mensaje}'. Coordinaremos contigo para agendar fecha y hora."
        if perfil_incompleto:
            respuesta_bot += " ⚠️ Tu perfil está incompleto. Completa tu nombre y negocio escribiendo algo como: 'Hola soy Ana y tengo una pasteleria'."

    # Regla 5: Fallback General
    else:
        tipo_detectado = "general"
        respuesta_bot = (
            "🤖 Hola, soy el bot de seguimiento Manq'a. No logré identificar tu solicitud.\n\n"
            "Puedes intentar escribir:\n"
            "• 'Hola soy Ana y tengo una pasteleria'\n"
            "• 'Vendi 1200 Bs esta semana'\n"
            "• 'Necesito ayuda en marketing y ventas'\n"
            "• 'Quiero programar una asesoria comercial'"
        )

    # Registrar la respuesta del bot en la BD (saliente)
    registrar_mensaje(telefono, respuesta_bot, tipo=tipo_detectado, direccion="saliente")
    
    return tipo_detectado, respuesta_bot


# ── Rutas ──────────────────────────────────────────────────

@router.get("/manqa/panel", response_class=HTMLResponse)
def get_panel(request: Request, last_response: str = None, last_type: str = None, reset: str = None):
    """Ruta principal que sirve la interfaz del panel administrativo con diseño cálido."""
    resumen = obtener_resumen()
    emprendedores = listar_emprendedores()
    mensajes = listar_ultimos_mensajes(30)
    
    # Mapeo y formateo de datos para adaptarlo a la nueva estructura institucional
    casos_prioritarios = 0
    for emp in emprendedores:
        # Formatear monto
        emp["ventas_total_fmt"] = f"{emp['ventas_total']:,.2f} Bs"
        
        # Mapear alerta a Prioridad (Rojo -> Alta, Amarillo -> Media, Verde -> Normal)
        if emp["ventas_total"] < 500:
            emp["prioridad"] = "Alta"
            emp["prioridad_class"] = "alta"
            casos_prioritarios += 1
        elif emp["refuerzos_count"] > 0:
            emp["prioridad"] = "Media"
            emp["prioridad_class"] = "media"
            casos_prioritarios += 1
        else:
            emp["prioridad"] = "Normal"
            emp["prioridad_class"] = "normal"
            
        # Calcular Acción Sugerida
        if emp["nombre"] == "Pendiente" or emp["negocio"] == "Pendiente":
            emp["accion_sugerida"] = "Completar perfil"
        elif emp["refuerzos_count"] > 0:
            emp["accion_sugerida"] = "Agendar asesoría"
        elif emp["ventas_total"] < 500:
            emp["accion_sugerida"] = "Revisar caso"
        else:
            emp["accion_sugerida"] = "Continuar seguimiento"

    # Guardar conteo de casos prioritarios en el resumen
    resumen["casos_prioritarios"] = casos_prioritarios

    # Generar "Casos que requieren seguimiento" con tono humano y cálido
    casos_seguimiento = []
    
    # 1. Perfiles incompletos
    incompletos = [e for e in emprendedores if e["nombre"] == "Pendiente" or e["negocio"] == "Pendiente"]
    for e in incompletos:
        casos_seguimiento.append({
            "mensaje": f"El emprendedor con teléfono {e['telefono']} inició el registro pero su perfil está incompleto. Se recomienda contactarle para completar sus datos y poder ofrecerle acompañamiento.",
            "accion": "Completar perfil",
            "telefono": e["telefono"]
        })
        
    # 2. Ventas bajas (Alta prioridad)
    bajas_ventas = [e for e in emprendedores if e["nombre"] != "Pendiente" and e["ventas_total"] < 500]
    for e in bajas_ventas:
        casos_seguimiento.append({
            "mensaje": f"{e['nombre']} ({e['telefono']}) completó su registro pero reportó ventas bajas ({e['ventas_total']:,.2f} Bs). Se sugiere contactarle y revisar su plan de negocios.",
            "accion": "Revisar caso",
            "telefono": e["telefono"]
        })
        
    # 3. Solicitud de apoyo (Media prioridad)
    apoyo = [e for e in emprendedores if e["nombre"] != "Pendiente" and e["refuerzos_count"] > 0 and e["ventas_total"] >= 500]
    for e in apoyo:
        casos_seguimiento.append({
            "mensaje": f"{e['nombre']} ({e['telefono']}) solicitó apoyo técnico. Se sugiere agendar una asesoría comercial esta semana.",
            "accion": "Agendar asesoría",
            "telefono": e["telefono"]
        })
        
    # Mensaje por defecto si está todo bien
    if not casos_seguimiento:
        casos_seguimiento.append({
            "mensaje": "Todos los emprendedores activos se encuentran al día con sus registros y no presentan alertas pendientes. ¡Buen trabajo de seguimiento!",
            "accion": "Continuar seguimiento",
            "telefono": ""
        })
    else:
        # Cap a un máximo de 2 para mantener limpio el diseño
        casos_seguimiento = casos_seguimiento[:2]
        
    return templates.TemplateResponse(
        request,
        "panel_manqa.html",
        {
            "resumen": resumen,
            "emprendedores": emprendedores,
            "mensajes": mensajes,
            "last_response": last_response,
            "last_type": last_type,
            "reset": reset,
            "casos_seguimiento": casos_seguimiento
        }
    )


@router.post("/manqa/demo/mensaje")
def post_demo_mensaje(telefono: str = Form(...), mensaje: str = Form(...)):
    """Formulario de simulación de WhatsApp. Procesa y redirige al panel."""
    if not telefono or not mensaje:
        raise HTTPException(status_code=400, detail="Teléfono y mensaje son obligatorios")
    
    tipo, respuesta = procesar_mensaje_texto(telefono, mensaje)
    
    # Redirigir al panel pasando la última respuesta en la Query String
    respuesta_encoded = urllib.parse.quote(respuesta)
    return RedirectResponse(
        url=f"/manqa/panel?last_response={respuesta_encoded}&last_type={tipo}",
        status_code=303
    )


@router.post("/manqa/demo/reset")
def post_demo_reset():
    """Borra todos los datos de la base de datos de la demo y redirige al panel."""
    reset_demo_db()
    return RedirectResponse(url="/manqa/panel?reset=success", status_code=303)


@router.post("/manqa/api/mensaje")
def post_api_mensaje(data: MensajeJSON):
    """API JSON para recibir mensajes (simula la entrada de un webhook)."""
    if not data.telefono or not data.mensaje:
        raise HTTPException(status_code=400, detail="telefono y mensaje son campos obligatorios")
    
    tipo, respuesta = procesar_mensaje_texto(data.telefono, data.mensaje)
    return {
        "status": "ok",
        "telefono": data.telefono,
        "mensaje_recibido": data.mensaje,
        "tipo_detectado": tipo,
        "respuesta_agente": respuesta
    }


@router.get("/manqa/api/resumen")
def get_api_resumen():
    """Retorna las estadísticas del panel en formato JSON."""
    return obtener_resumen()


@router.get("/manqa/api/emprendedores")
def get_api_emprendedores():
    """Retorna la lista de emprendedores en formato JSON."""
    # Retornamos la lista con las transformaciones de prioridad para mantener consistencia
    emprendedores = listar_emprendedores()
    for emp in emprendedores:
        if emp["ventas_total"] < 500:
            emp["prioridad"] = "Alta"
        elif emp["refuerzos_count"] > 0:
            emp["prioridad"] = "Media"
        else:
            emp["prioridad"] = "Normal"
            
        if emp["nombre"] == "Pendiente" or emp["negocio"] == "Pendiente":
            emp["accion_sugerida"] = "Completar perfil"
        elif emp["refuerzos_count"] > 0:
            emp["accion_sugerida"] = "Agendar asesoría"
        elif emp["ventas_total"] < 500:
            emp["accion_sugerida"] = "Revisar caso"
        else:
            emp["accion_sugerida"] = "Continuar seguimiento"
    return emprendedores


@router.get("/manqa/reporte.csv")
def get_reporte_csv():
    """Exporta y descarga un reporte CSV con el estado de los emprendedores."""
    # Obtenemos la lista con la nomenclatura del mockup
    raw_emprendedores = listar_emprendedores()
    
    # Crear un buffer en memoria
    output = io.StringIO()
    # Escribir BOM para que Excel reconozca caracteres especiales en Windows
    output.write('\ufeff')
    
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    
    # Cabeceras adaptadas
    writer.writerow([
        "Nombre", "Telefono", "Negocio", "Fase", 
        "Ventas Total (Bs)", "Necesidad de Apoyo", "Asesorias", "Alerta"
    ])
    
    # Filas
    for emp in raw_emprendedores:
        # Mapear prioridad
        if emp["ventas_total"] < 500:
            prioridad = "Alta"
        elif emp["refuerzos_count"] > 0:
            prioridad = "Media"
        else:
            prioridad = "Normal"
            
        writer.writerow([
            emp["nombre"],
            emp["telefono"],
            emp["negocio"],
            emp["fase"],
            emp["ventas_total"],
            emp["refuerzos_count"],
            emp["asesorias_count"],
            prioridad
        ])
        
    csv_data = output.getvalue()
    output.close()
    
    return Response(
        content=csv_data,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=reporte_emprendedores_manqa.csv",
            "Cache-Control": "no-cache"
        }
    )
