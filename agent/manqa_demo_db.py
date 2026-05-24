# agent/manqa_demo_db.py — Base de datos independiente para la demo de Manq'a
# Proyecto Kallpa — Demo Manq'a / Wayna Hub

import os
import sqlite3
import re
from datetime import datetime

# Determinar la ruta absoluta de la base de datos en la raíz del proyecto
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "manqa_demo.db")


def init_manqa_db():
    """Inicializa la base de datos y crea las tablas si no existen."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        # Tabla: emprendedores
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS emprendedores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT,
                telefono TEXT UNIQUE,
                negocio TEXT,
                fase TEXT DEFAULT 'Registro',
                estado TEXT DEFAULT 'Activo',
                creado_en DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Tabla: ventas_mensuales
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ventas_mensuales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                emprendedor_id INTEGER,
                monto REAL,
                mes TEXT,
                observacion TEXT,
                creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (emprendedor_id) REFERENCES emprendedores(id)
            )
        """)

        # Tabla: refuerzos
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS refuerzos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                emprendedor_id INTEGER,
                area TEXT,
                motivo TEXT,
                prioridad TEXT DEFAULT 'Media',
                creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (emprendedor_id) REFERENCES emprendedores(id)
            )
        """)

        # Tabla: asesorias
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS asesorias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                emprendedor_id INTEGER,
                tema TEXT,
                estado TEXT DEFAULT 'Pendiente',
                creado_en DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (emprendedor_id) REFERENCES emprendedores(id)
            )
        """)

        # Tabla: mensajes (Historial de logs de WhatsApp simulado)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mensajes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telefono TEXT,
                mensaje TEXT,
                tipo TEXT,
                direccion TEXT,
                creado_en DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()


def registrar_mensaje(telefono: str, mensaje: str, tipo: str, direccion: str):
    """Guarda un registro de mensaje (entrante o saliente) en la tabla mensajes."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO mensajes (telefono, mensaje, tipo, direccion) VALUES (?, ?, ?, ?)",
            (telefono, mensaje, tipo, direccion)
        )
        conn.commit()


def obtener_o_crear_emprendedor_por_telefono(telefono: str) -> dict:
    """Busca un emprendedor por teléfono. Si no existe, lo crea con valores por defecto."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM emprendedores WHERE telefono = ?", (telefono,))
        row = cursor.fetchone()
        if row:
            return dict(row)

        cursor.execute(
            "INSERT INTO emprendedores (nombre, telefono, negocio, fase, estado) VALUES (?, ?, ?, ?, ?)",
            ("Pendiente", telefono, "Pendiente", "Registro", "Activo")
        )
        conn.commit()

        cursor.execute("SELECT * FROM emprendedores WHERE telefono = ?", (telefono,))
        row = cursor.fetchone()
        return dict(row)


def extraer_nombre_y_negocio(mensaje: str) -> tuple[str | None, str | None]:
    """
    Parsea de forma robusta el nombre y el negocio a partir del mensaje.
    Ejemplo: "Hola soy Ana y tengo una pasteleria"
    - soy Ana -> Nombre: Ana
    - tengo una pasteleria -> Negocio: Pasteleria
    """
    mensaje_lc = mensaje.lower().strip()
    nombre = None
    negocio = None

    # Regex para extraer nombre tras "soy"
    # Captura palabras hasta encontrarse con conectores o puntuación
    match_nombre = re.search(r'\bsoy\s+([a-záéíóúñ\s]{2,30}?)(?:\b(y|tengo|con|en|de|desde|mi)\b|[.,;]|$)', mensaje_lc, re.IGNORECASE)
    if match_nombre:
        nombre = match_nombre.group(1).strip().title()
    else:
        # Fallback simple
        match_nombre_simple = re.search(r'\bsoy\s+([a-záéíóúñ]+)', mensaje_lc, re.IGNORECASE)
        if match_nombre_simple:
            nombre = match_nombre_simple.group(1).strip().capitalize()

    # Regex para extraer negocio tras "tengo"
    match_negocio = re.search(r'\btengo\s+(?:un\s+|una\s+|mi\s+)?([a-záéíóúñ\s]{2,50}?)(?:\b(y|soy|en|desde|con|para)\b|[.,;]|$)', mensaje_lc, re.IGNORECASE)
    if match_negocio:
        negocio = match_negocio.group(1).strip().capitalize()
    else:
        # Fallback simple
        match_negocio_simple = re.search(r'\btengo\s+(?:un\s+|una\s+)?([a-záéíóúñ]+)', mensaje_lc, re.IGNORECASE)
        if match_negocio_simple:
            negocio = match_negocio_simple.group(1).strip().capitalize()

    return nombre, negocio


def actualizar_emprendedor_desde_mensaje(telefono: str, mensaje: str) -> dict:
    """Extrae el nombre y negocio del mensaje, y actualiza la información del emprendedor."""
    nombre, negocio = extraer_nombre_y_negocio(mensaje)
    emp = obtener_o_crear_emprendedor_por_telefono(telefono)

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        updates = []
        params = []
        if nombre:
            updates.append("nombre = ?")
            params.append(nombre)
        if negocio:
            updates.append("negocio = ?")
            params.append(negocio)

        # Si se detectó nombre o negocio, actualizamos la fase a 'Diagnóstico' para simular avance
        if nombre or negocio:
            updates.append("fase = ?")
            params.append("Diagnóstico")

        if updates:
            params.append(emp["id"])
            query = f"UPDATE emprendedores SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, params)
            conn.commit()

        # Refrescar y retornar
        cursor.execute("SELECT * FROM emprendedores WHERE telefono = ?", (telefono,))
        row = cursor.fetchone()
        return dict(row)


def registrar_venta(emprendedor_id: int, monto: float, mes: str, observacion: str = None):
    """Registra una venta mensual."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO ventas_mensuales (emprendedor_id, monto, mes, observacion) VALUES (?, ?, ?, ?)",
            (emprendedor_id, monto, mes, observacion)
        )
        # Si registra ventas, podemos subir la fase a 'Seguimiento'
        cursor.execute(
            "UPDATE emprendedores SET fase = 'Seguimiento' WHERE id = ? AND fase = 'Diagnóstico'",
            (emprendedor_id,)
        )
        conn.commit()


def registrar_refuerzo(emprendedor_id: int, area: str, motivo: str, prioridad: str = "Media"):
    """Registra una necesidad de refuerzo."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO refuerzos (emprendedor_id, area, motivo, prioridad) VALUES (?, ?, ?, ?)",
            (emprendedor_id, area, motivo, prioridad)
        )
        conn.commit()


def registrar_asesoria(emprendedor_id: int, tema: str, estado: str = "Pendiente"):
    """Registra una solicitud de asesoría."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO asesorias (emprendedor_id, tema, estado) VALUES (?, ?, ?)",
            (emprendedor_id, tema, estado)
        )
        conn.commit()


def obtener_resumen() -> dict:
    """Retorna las estadísticas clave para las tarjetas del panel."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM emprendedores")
        total_emp = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM ventas_mensuales")
        total_ventas = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM refuerzos")
        total_refuerzos = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM asesorias")
        total_asesorias = cursor.fetchone()[0]

        return {
            "total_emprendedores": total_emp,
            "ventas_registradas": total_ventas,
            "refuerzos_detectados": total_refuerzos,
            "asesorias_solicitadas": total_asesorias
        }


def listar_emprendedores() -> list[dict]:
    """Retorna la lista de emprendedores con sus ventas, refuerzos, asesorías y alerta."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Consulta agregada para calcular ventas, cantidad de refuerzos, asesorías y última acción por emprendedor
        query = """
            SELECT 
                e.id, 
                e.nombre, 
                e.telefono, 
                e.negocio, 
                e.fase, 
                e.estado,
                COALESCE((SELECT SUM(monto) FROM ventas_mensuales WHERE emprendedor_id = e.id), 0) AS ventas_total,
                (SELECT COUNT(*) FROM refuerzos WHERE emprendedor_id = e.id) AS refuerzos_count,
                (SELECT COUNT(*) FROM asesorias WHERE emprendedor_id = e.id) AS asesorias_count,
                COALESCE((SELECT tipo FROM mensajes WHERE telefono = e.telefono ORDER BY id DESC LIMIT 1), 'general') AS ultima_accion
            FROM emprendedores e
            ORDER BY e.creado_en DESC
        """
        cursor.execute(query)
        rows = cursor.fetchall()

        emprendedores = []
        for row in rows:
            d = dict(row)
            
            # Calcular alerta
            # - ventas_total < 500 = Rojo
            # - tiene refuerzos = Amarillo (y ventas_total >= 500)
            # - sin problemas = Verde
            if d["ventas_total"] < 500:
                alerta = "Rojo"
            elif d["refuerzos_count"] > 0:
                alerta = "Amarillo"
            else:
                alerta = "Verde"
                
            d["alerta"] = alerta
            
            # Formatear la última acción
            accion_map = {
                "registro": "Registro",
                "venta": "Venta",
                "refuerzo": "Refuerzo",
                "asesoria": "Asesoría",
                "general": "General"
            }
            d["ultima_accion_fmt"] = accion_map.get(d["ultima_accion"], "General")
            
            emprendedores.append(d)

        return emprendedores


def listar_ultimos_mensajes(limite: int = 20) -> list[dict]:
    """Retorna el historial de los últimos mensajes registrados."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM mensajes ORDER BY creado_en DESC LIMIT ?", (limite,))
        return [dict(row) for row in cursor.fetchall()]


def reset_demo_db():
    """Borra todos los datos de todas las tablas para reiniciar la demo."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM mensajes")
        cursor.execute("DELETE FROM asesorias")
        cursor.execute("DELETE FROM refuerzos")
        cursor.execute("DELETE FROM ventas_mensuales")
        cursor.execute("DELETE FROM emprendedores")
        conn.commit()
