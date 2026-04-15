from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    correo: Optional[str] = None
    rol: Optional[str] = None

class UsuarioBase(BaseModel):
    correo: str
    rol: str

class UsuarioCreate(UsuarioBase):
    password: str

class UsuarioResponse(UsuarioBase):
    id: int
    class Config:
        from_attributes = True

class EleccionCreate(BaseModel):
    nombre: str

class EleccionResponse(BaseModel):
    id: int
    nombre: str
    activa: bool
    class Config:
        from_attributes = True

class VotanteCreate(BaseModel):
    ci: str
    nombre: str

class VotanteResponse(BaseModel):
    id: int
    ci: str
    nombre: str
    correo: str
    habilitado: bool
    ha_votado: bool
    class Config:
        from_attributes = True

class CandidatoCreate(BaseModel):
    nombre: str
    cargo: str
    descripcion: Optional[str] = None
    eleccion_id: int

class CandidatoResponse(BaseModel):
    id: int
    eleccion_id: int
    nombre: str
    cargo: str
    descripcion: Optional[str] = None
    class Config:
        from_attributes = True

class MesaCreate(BaseModel):
    eleccion_id: int
    numero: int

class AsignarJefe(BaseModel):
    mesa_id: int
    usuario_id: int

class VotoCreate(BaseModel):
    candidato_id: int
    eleccion_id: int
