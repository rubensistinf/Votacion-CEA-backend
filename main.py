import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

import models
from database import engine, SessionLocal
from routes import auth_routes, admin_routes, secretaria_routes, jefe_routes, votante_routes
from auth import get_password_hash

# Crear tablas
models.Base.metadata.create_all(bind=engine)

def init_db():
    db = SessionLocal()
    # List of default users expected
    default_users = [
        {"correo": "admin@cea.com", "rol": "admin"},
        {"correo": "secretaria@cea.com", "rol": "secretaria"},
        {"correo": "jefe@cea.com", "rol": "jefe"},
        {"correo": "votante@cea.com", "rol": "votante"}
    ]
    
    for u in default_users:
        user = db.query(models.Usuario).filter(models.Usuario.correo == u["correo"]).first()
        if not user:
            new_user = models.Usuario(
                correo=u["correo"],
                password_hash=get_password_hash("12345"), # Password by default as requested
                rol=u["rol"]
            )
            db.add(new_user)
    
    db.commit()
    db.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    from migrate_db import migrate
    try:
        migrate()
    except Exception as e:
        print(f"⚠️ Error en la migración inicial: {e}")
    init_db()
    yield
    # Shutdown actions

app = FastAPI(title="API Elecciones CEA", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Permitir todos temporalmente para asegurar conectividad total
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(admin_routes.router)
app.include_router(secretaria_routes.router)
app.include_router(jefe_routes.router)
app.include_router(votante_routes.router)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
