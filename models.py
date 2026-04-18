from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    correo = Column(String, unique=True, index=True)
    password_hash = Column(String)
    rol = Column(String)  # admin, secretaria, jefe, votante

class Eleccion(Base):
    __tablename__ = "elecciones"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, index=True)
    activa = Column(Boolean, default=False)
    resultados_publicados = Column(Boolean, default=False)

class Mesa(Base):
    __tablename__ = "mesas"

    id = Column(Integer, primary_key=True, index=True)
    eleccion_id = Column(Integer, ForeignKey("elecciones.id"))
    numero = Column(Integer)

class JefeMesa(Base):
    __tablename__ = "jefes_mesa"

    id = Column(Integer, primary_key=True, index=True)
    mesa_id = Column(Integer, ForeignKey("mesas.id"))
    usuario_id = Column(Integer, ForeignKey("usuarios.id"))
    nombre_jefe = Column(String, nullable=True)  # Nombre del jefe para carnet

class Candidato(Base):
    __tablename__ = "candidatos"

    id = Column(Integer, primary_key=True, index=True)
    eleccion_id = Column(Integer, ForeignKey("elecciones.id"))
    nombre = Column(String)
    sigla = Column(String, nullable=True)
    cargo = Column(String)
    frente = Column(String, nullable=True)
    descripcion = Column(String, nullable=True)
    imagen_base64 = Column(String, nullable=True)

class Votante(Base):
    __tablename__ = "votantes"

    id = Column(Integer, primary_key=True, index=True)
    ci = Column(String, unique=True, index=True)
    nombre = Column(String)
    correo = Column(String, unique=True)
    habilitado = Column(Boolean, default=False)
    ha_votado = Column(Boolean, default=False)

class AsignacionMesa(Base):
    """Relaciona cada votante con su mesa asignada."""
    __tablename__ = "asignaciones_mesa"

    id = Column(Integer, primary_key=True, index=True)
    votante_ci = Column(String, ForeignKey("votantes.ci"), unique=True, index=True)
    mesa_id = Column(Integer, ForeignKey("mesas.id"))
    mesa_numero = Column(Integer)  # Desnormalizado para acceso rápido

class Voto(Base):
    __tablename__ = "votos"

    id = Column(Integer, primary_key=True, index=True)
    candidato_id = Column(Integer, ForeignKey("candidatos.id"))
    eleccion_id = Column(Integer, ForeignKey("elecciones.id"))
    timestamp = Column(DateTime, default=datetime.utcnow)

class AuditLog(Base):
    """Registro de auditoría para acciones críticas administrativos."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    accion = Column(String)  # ej: "CREAR_ELECCION", "HABILITAR_VOTANTE", "BORRAR_MESAS"
    detalle = Column(String) # Información adicional
    ip_address = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

