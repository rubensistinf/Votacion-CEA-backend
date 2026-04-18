import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

import models
from database import engine, SessionLocal
from routes import auth_routes, admin_routes, secretaria_routes, jefe_routes, votante_routes
from auth import get_password_hash

# El motor de base de datos se encarga de las tablas
# Quitamos create_all del flujo principal para evitar bloqueos en el arranque de Render

def init_db():
    try:
        models.Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"⚠️ Error al crear tablas: {e}")
        
    db = SessionLocal()
    # List of default users expected
    default_users = [
        {"correo": "admin@cea.com", "rol": "admin"},
        {"correo": "secretaria@cea.com", "rol": "secretaria"},
        {"correo": "jefe@cea.com", "rol": "jefe"},
        {"correo": "votante@cea.com", "rol": "votante"}
    ]
    
    for u in default_users:
        try:
            user = db.query(models.Usuario).filter(models.Usuario.correo == u["correo"]).first()
            if not user:
                new_user = models.Usuario(
                    correo=u["correo"],
                    password_hash=get_password_hash("12345"),
                    rol=u["rol"]
                )
                db.add(new_user)
        except:
            pass
    
    db.commit()
    db.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions: Crear tablas si no existen
    init_db()
    
    # MIGRACIÓN AUTOMÁTICA DE EMERGENCIA (Añadir columnas faltantes)
    from sqlalchemy import text
    from database import engine
    with engine.connect() as conn:
        print("🔍 Verificando esquema de candidatos...")
        columns_to_check = [
            ("sigla", "VARCHAR(100)"),
            ("frente", "VARCHAR(100)"),
            ("imagen_base64", "TEXT")
        ]
        for col_name, col_type in columns_to_check:
            try:
                # Intentar añadir la columna (fallará si ya existe, lo cual es manejado)
                conn.execute(text(f"ALTER TABLE candidatos ADD COLUMN {col_name} {col_type};"))
                conn.commit()
                print(f"✅ Columna añadida: {col_name}")
            except Exception:
                # Ignorar si la columna ya existe
                conn.rollback()
                pass
        print("🚀 Base de datos sincronizada.")
    
    # INYECCIÓN DE VOTO BLANCO Y NULO EN ELECCIONES (Retrospectiva)
    from database import SessionLocal
    import models
    db_session = SessionLocal()
    try:
        elecciones = db_session.query(models.Eleccion).all()
        for e in elecciones:
            # Voto Blanco
            blanco = db_session.query(models.Candidato).filter(models.Candidato.eleccion_id == e.id, models.Candidato.sigla == "BLANCO").first()
            if not blanco:
                db_session.add(models.Candidato(eleccion_id=e.id, nombre="⬜ VOTO EN BLANCO", sigla="BLANCO", cargo="—", frente="Institucional"))
            
            # Voto Nulo
            nulo = db_session.query(models.Candidato).filter(models.Candidato.eleccion_id == e.id, models.Candidato.sigla == "NULO").first()
            if not nulo:
                db_session.add(models.Candidato(eleccion_id=e.id, nombre="❌ VOTO NULO", sigla="NULO", cargo="—", frente="Institucional"))
        db_session.commit()
        print("✅ Tarjetas de Voto Blanco/Nulo inyectadas.")
    except Exception as exc:
        print("Error inyectando Voto Blanco/Nulo:", exc)
    finally:
        db_session.close()
    
    yield
    # Shutdown actions

app = FastAPI(title="API Elecciones CEA", lifespan=lifespan)

@app.middleware("http")
async def custom_cors_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        from fastapi.responses import Response
        response = Response()
    else:
        response = await call_next(request)
    
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Allow-Credentials"] = "false"
    return response


@app.get("/health")
def health_check():
    return {"status": "ok", "version": "4.3.3", "origin_allowed": True}


app.include_router(auth_routes.router)
app.include_router(admin_routes.router)
app.include_router(secretaria_routes.router)
app.include_router(jefe_routes.router)
app.include_router(votante_routes.router)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Log the full error to the console for tracking in Render logs
    import traceback
    print(f"🚨 ERROR GLOBAL DETECTADO: {exc}")
    traceback.print_exc()
    
    # Return a clean error instead of a 500 crash
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=500,
        content={"detail": f"Error interno del sistema: {str(exc)}. Por favor reporta esto al administrador."}
    )

@app.get("/ping")
def ping():
    return {"status": "ok", "version": "2.0.1"}

@app.get("/")
def home():
    return {"msg": "CEA Votación Backend v2.0 Online"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
