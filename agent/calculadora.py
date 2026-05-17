# agent/calculadora.py — Lógica financiera del plan de negocios
# Proyecto Kallpa — Fundación Kallpa

"""
Módulo de cálculos financieros para emprendedores.
Calcula: costos fijos/variables, punto de equilibrio,
margen de ganancia y precio de venta sugerido.
"""


def calcular_resumen(
    costos: list[dict],
    precio_actual: float,
    unidades_mes: float,
    margen_objetivo: float = 30.0
) -> dict:
    """
    Calcula el resumen financiero completo del emprendimiento.

    Args:
        costos: Lista de costos [{"nombre", "monto", "tipo", "categoria"}]
        precio_actual: Precio de venta actual por unidad
        unidades_mes: Unidades vendidas por mes
        margen_objetivo: Margen de ganancia objetivo en % (default 30%)

    Returns:
        Diccionario con todos los indicadores financieros
    """
    # ── Separar costos ──────────────────────────────────────
    costos_fijos = [c for c in costos if c["tipo"] == "fijo"]
    costos_variables = [c for c in costos if c["tipo"] == "variable"]

    total_fijos = sum(c["monto"] for c in costos_fijos)
    total_variables_mes = sum(c["monto"] for c in costos_variables)

    # Costo variable por unidad (si hay unidades, sino 0)
    cv_unitario = total_variables_mes / unidades_mes if unidades_mes > 0 else total_variables_mes

    # ── Costo total unitario ────────────────────────────────
    cf_unitario = total_fijos / unidades_mes if unidades_mes > 0 else total_fijos
    costo_total_unitario = cf_unitario + cv_unitario

    # ── Margen de contribución ──────────────────────────────
    margen_contribucion = precio_actual - cv_unitario

    # ── Punto de equilibrio ─────────────────────────────────
    if margen_contribucion > 0:
        punto_equilibrio_unidades = total_fijos / margen_contribucion
        punto_equilibrio_monto = punto_equilibrio_unidades * precio_actual
    else:
        punto_equilibrio_unidades = float("inf")
        punto_equilibrio_monto = float("inf")

    # ── Margen de ganancia actual ───────────────────────────
    if precio_actual > 0:
        margen_ganancia = ((precio_actual - costo_total_unitario) / precio_actual) * 100
    else:
        margen_ganancia = 0

    # ── Utilidad mensual ────────────────────────────────────
    utilidad_mes = (precio_actual - costo_total_unitario) * unidades_mes if unidades_mes > 0 else 0

    # ── Precio sugerido ─────────────────────────────────────
    # Fórmula: PS = Costo Total Unitario / (1 - Margen_objetivo%)
    if margen_objetivo < 100:
        precio_sugerido = costo_total_unitario / (1 - margen_objetivo / 100)
    else:
        precio_sugerido = costo_total_unitario * 2

    # ── Estado de salud financiera ──────────────────────────
    if margen_ganancia >= 20:
        salud = "buena"
        salud_emoji = "🟢"
    elif margen_ganancia >= 5:
        salud = "regular"
        salud_emoji = "🟡"
    else:
        salud = "crítica"
        salud_emoji = "🔴"

    return {
        # Costos
        "costos_fijos": costos_fijos,
        "costos_variables": costos_variables,
        "total_fijos": total_fijos,
        "total_variables_mes": total_variables_mes,
        "cv_unitario": cv_unitario,
        "cf_unitario": cf_unitario,
        "costo_total_unitario": costo_total_unitario,
        # Precio
        "precio_actual": precio_actual,
        "precio_sugerido": precio_sugerido,
        "unidades_mes": unidades_mes,
        # Indicadores
        "margen_contribucion": margen_contribucion,
        "margen_ganancia": margen_ganancia,
        "punto_equilibrio_unidades": punto_equilibrio_unidades,
        "punto_equilibrio_monto": punto_equilibrio_monto,
        "utilidad_mes": utilidad_mes,
        # Salud
        "salud": salud,
        "salud_emoji": salud_emoji,
        "margen_objetivo": margen_objetivo,
    }


def formatear_bolivianos(monto: float) -> str:
    """Formatea un monto en bolivianos."""
    if monto == float("inf"):
        return "∞"
    return f"Bs. {monto:,.2f}"


def generar_resumen_whatsapp(resumen: dict, nombre_agente: str, nombre_negocio: str) -> str:
    """
    Genera el resumen financiero formateado para enviar por WhatsApp.

    Returns:
        Texto formateado con los indicadores clave
    """
    pe_u = resumen["punto_equilibrio_unidades"]
    pe_m = resumen["punto_equilibrio_monto"]

    lineas = [
        f"📊 *Plan de Negocios — {nombre_negocio}*",
        f"Análisis generado por {nombre_agente} · Fundación Kallpa",
        "",
        f"*💰 COSTOS FIJOS (mensuales)*",
    ]

    for c in resumen["costos_fijos"]:
        lineas.append(f"  • {c['nombre']}: {formatear_bolivianos(c['monto'])}")
    lineas.append(f"  *Total: {formatear_bolivianos(resumen['total_fijos'])}*")

    lineas += [
        "",
        f"*📦 COSTOS VARIABLES (por unidad)*",
    ]
    for c in resumen["costos_variables"]:
        lineas.append(f"  • {c['nombre']}: {formatear_bolivianos(c['monto'])}")
    lineas.append(f"  *Total: {formatear_bolivianos(resumen['cv_unitario'])}/unidad*")

    lineas += [
        "",
        f"*🏷️ PRECIOS*",
        f"  Precio actual: {formatear_bolivianos(resumen['precio_actual'])}",
        f"  Precio sugerido ({resumen['margen_objetivo']:.0f}% margen): {formatear_bolivianos(resumen['precio_sugerido'])}",
        "",
        f"*📈 INDICADORES*",
        f"  Margen de ganancia: {resumen['margen_ganancia']:.1f}% {resumen['salud_emoji']}",
        f"  Punto de equilibrio: {pe_u:.0f} unidades/mes" if pe_u != float('inf') else "  Punto de equilibrio: No alcanzable con precio actual ⚠️",
        f"  Equivale a: {formatear_bolivianos(pe_m)}/mes" if pe_m != float('inf') else "",
        f"  Utilidad estimada: {formatear_bolivianos(resumen['utilidad_mes'])}/mes",
        "",
        f"*Salud financiera: {resumen['salud'].upper()} {resumen['salud_emoji']}*",
    ]

    # Quitar líneas vacías al final y líneas None
    lineas = [l for l in lineas if l is not None]
    return "\n".join(lineas)
