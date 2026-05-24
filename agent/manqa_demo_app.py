# agent/manqa_demo_app.py — Aplicación independiente FastAPI para la demo de Manq'a
# Proyecto Kallpa — Demo Manq'a / Wayna Hub

from fastapi import FastAPI
from agent.manqa_demo_routes import router as manqa_demo_router
from agent.manqa_demo_db import init_manqa_db

app = FastAPI(
    title="Demo Manq'a Wayna Hub",
    description="Demo independiente para seguimiento de emprendedores por WhatsApp",
    version="1.0.0"
)


@app.on_event("startup")
def startup():
    """Evento que se ejecuta al iniciar el servidor para inicializar la base de datos."""
    init_manqa_db()


app.include_router(manqa_demo_router)


@app.get("/")
def home():
    """Ruta raíz que redirige o informa que la demo de Manq'a está lista."""
    return {
        "mensaje": "Demo Manq'a funcionando",
        "panel": "/manqa/panel"
    }
