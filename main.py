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
    # Ya no ejecutamos migración aquí para que Render arranque al instante
    # El admin puede ejecutarla manualmente con el botón "Reparar"
    init_db()
    yield
    # Shutdown actions

app = FastAPI(title="API Elecciones CEA", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://eleccione-cea.onrender.com",
        "https://elecciones-cea.onrender.com",
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
