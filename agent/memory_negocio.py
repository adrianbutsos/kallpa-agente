# agent/memory_negocio.py — Datos del emprendedor y sus costos
# Proyecto Kallpa — Fundación Kallpa

"""
Almacena los datos financieros de cada emprendedor:
- Perfil (nombre, negocio, nombre del agente personalizado)
- Costos fijos y variables
- Precio de venta y unidades mensuales
"""

import os
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, Float, DateTime, Boolean, Integer, select
from dotenv import load_dotenv

load_dotenv()

DATABASE_NEGOCIO_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./kallpa.db")
if DATABASE_NEGOCIO_URL.startswith("postgresql://"):
    DATABASE_NEGOCIO_URL = DATABASE_NEGOCIO_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine_negocio = create_async_engine(DATABASE_NEGOCIO_URL, echo=False)
session_negocio = async_sessionmaker(engine_negocio, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Emprendedor(Base):
    """Perfil del emprendedor."""
    __tablename__ = "emprendedores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    nombre_agente: Mapped[str] = mapped_column(String(100), default="Kallpa")
    nombre_emprendedor: Mapped[str] = mapped_column(String(150), nullable=True)
    nombre_negocio: Mapped[str] = mapped_column(String(150), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Costo(Base):
    """Costo registrado del emprendimiento."""
    __tablename__ = "costos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(50), index=True)
    nombre: Mapped[str] = mapped_column(String(200))
    monto: Mapped[float] = mapped_column(Float)
    tipo: Mapped[str] = mapped_column(String(20))       # "fijo" o "variable"
    categoria: Mapped[str] = mapped_column(String(100), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ConfigPrecio(Base):
    """Configuración de precio de venta y unidades."""
    __tablename__ = "config_precio"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telefono: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    precio_actual: Mapped[float] = mapped_column(Float, default=0)
    unidades_mes: Mapped[float] = mapped_column(Float, default=0)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


async def inicializar_db_negocio():
    """Crea las tablas si no existen."""
    async with engine_negocio.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ── Emprendedor ────────────────────────────────────────────

async def obtener_emprendedor(telefono: str) -> Emprendedor | None:
    async with session_negocio() as s:
        result = await s.execute(select(Emprendedor).where(Emprendedor.telefono == telefono))
        return result.scalar_one_or_none()


async def crear_emprendedor(telefono: str) -> Emprendedor:
    async with session_negocio() as s:
        emp = Emprendedor(telefono=telefono)
        s.add(emp)
        await s.commit()
        await s.refresh(emp)
        return emp


async def actualizar_nombre_agente(telefono: str, nombre_agente: str):
    async with session_negocio() as s:
        result = await s.execute(select(Emprendedor).where(Emprendedor.telefono == telefono))
        emp = result.scalar_one_or_none()
        if emp:
            emp.nombre_agente = nombre_agente
            emp.actualizado_en = datetime.utcnow()
            await s.commit()


async def actualizar_perfil(telefono: str, nombre_emprendedor: str, nombre_negocio: str):
    async with session_negocio() as s:
        result = await s.execute(select(Emprendedor).where(Emprendedor.telefono == telefono))
        emp = result.scalar_one_or_none()
        if not emp:
            emp = Emprendedor(telefono=telefono)
            s.add(emp)
        emp.nombre_emprendedor = nombre_emprendedor
        emp.nombre_negocio = nombre_negocio
        emp.actualizado_en = datetime.utcnow()
        await s.commit()


# ── Costos ─────────────────────────────────────────────────

async def registrar_costo(telefono: str, nombre: str, monto: float, tipo: str, categoria: str = None):
    async with session_negocio() as s:
        costo = Costo(
            telefono=telefono,
            nombre=nombre,
            monto=monto,
            tipo=tipo.lower(),
            categoria=categoria or "general",
            creado_en=datetime.utcnow()
        )
        s.add(costo)
        await s.commit()


async def obtener_costos(telefono: str) -> list[Costo]:
    async with session_negocio() as s:
        result = await s.execute(
            select(Costo)
            .where(Costo.telefono == telefono, Costo.activo == True)
            .order_by(Costo.tipo, Costo.creado_en)
        )
        return list(result.scalars().all())


async def eliminar_costo(costo_id: int, telefono: str):
    async with session_negocio() as s:
        result = await s.execute(
            select(Costo).where(Costo.id == costo_id, Costo.telefono == telefono)
        )
        costo = result.scalar_one_or_none()
        if costo:
            costo.activo = False
            await s.commit()


# ── Precio ─────────────────────────────────────────────────

async def guardar_precio(telefono: str, precio_actual: float, unidades_mes: float):
    async with session_negocio() as s:
        result = await s.execute(select(ConfigPrecio).where(ConfigPrecio.telefono == telefono))
        config = result.scalar_one_or_none()
        if not config:
            config = ConfigPrecio(telefono=telefono)
            s.add(config)
        config.precio_actual = precio_actual
        config.unidades_mes = unidades_mes
        config.actualizado_en = datetime.utcnow()
        await s.commit()


async def obtener_precio(telefono: str) -> ConfigPrecio | None:
    async with session_negocio() as s:
        result = await s.execute(select(ConfigPrecio).where(ConfigPrecio.telefono == telefono))
        return result.scalar_one_or_none()


# ── Contexto completo ──────────────────────────────────────

async def obtener_contexto_completo(telefono: str) -> dict:
    """Retorna todo el contexto del emprendedor para el system prompt."""
    emp = await obtener_emprendedor(telefono)
    costos = await obtener_costos(telefono)
    precio = await obtener_precio(telefono)

    if not emp:
        return {
            "es_nuevo": True,
            "nombre_agente": "Kallpa",
            "nombre_emprendedor": None,
            "nombre_negocio": None,
            "costos": [],
            "precio_actual": 0,
            "unidades_mes": 0,
        }

    return {
        "es_nuevo": False,
        "nombre_agente": emp.nombre_agente or "Kallpa",
        "nombre_emprendedor": emp.nombre_emprendedor,
        "nombre_negocio": emp.nombre_negocio,
        "costos": [
            {"nombre": c.nombre, "monto": c.monto, "tipo": c.tipo, "categoria": c.categoria}
            for c in costos
        ],
        "precio_actual": precio.precio_actual if precio else 0,
        "unidades_mes": precio.unidades_mes if precio else 0,
    }
