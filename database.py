import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Leemos la variable de entorno, por defecto usamos SQLite para desarrollo local
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./elecciones.db")

# Si la URL es de postgres (generada por Render a veces viene como postgres:// en vez de postgresql://)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Argumentos del engine solo para SQLite (para evitar errores de multi-hilos)
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependencia para las rutas FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
