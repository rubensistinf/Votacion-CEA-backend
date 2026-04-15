from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    correo = Column(String, unique=True, index=True) # sirvi para login
    password_hash = Column(String)
    rol = Column(String) # admin, secretaria, jefe, votante

class Eleccion(Base):
    __tablename__ = "elecciones"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, index=True)
    activa = Column(Boolean, default=True)

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

class Candidato(Base):
    __tablename__ = "candidatos"

    id = Column(Integer, primary_key=True, index=True)
    eleccion_id = Column(Integer, ForeignKey("elecciones.id"))
    nombre = Column(String)
    cargo = Column(String)
    descripcion = Column(String, nullable=True)

class Votante(Base):
    __tablename__ = "votantes"

    id = Column(Integer, primary_key=True, index=True)
    ci = Column(String, unique=True, index=True)
    nombre = Column(String)
    correo = Column(String, unique=True) # Para crear su usuario o login
    habilitado = Column(Boolean, default=False)
    ha_votado = Column(Boolean, default=False)

class Voto(Base):
    __tablename__ = "votos"

    id = Column(Integer, primary_key=True, index=True)
    candidato_id = Column(Integer, ForeignKey("candidatos.id"))
    eleccion_id = Column(Integer, ForeignKey("elecciones.id"))
    timestamp = Column(DateTime, default=datetime.utcnow)
