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
    sigla: Optional[str] = None
    cargo: str
    frente: Optional[str] = None
    descripcion: Optional[str] = None
    eleccion_id: int
    imagen_base64: Optional[str] = None
    ci_representante: Optional[str] = None  # CI del lider para auto-inscribirlo como votante

class CandidatoResponse(BaseModel):
    id: int
    eleccion_id: int
    nombre: str
    sigla: Optional[str] = None
    cargo: str
    frente: Optional[str] = None
    descripcion: Optional[str] = None
    imagen_base64: Optional[str] = None
    class Config:
        from_attributes = True

class CandidatoPublico(BaseModel):
    id: int
    nombre: str
    sigla: Optional[str] = None
    cargo: str
    frente: Optional[str] = None
    imagen_base64: Optional[str] = None
    class Config:
        from_attributes = True

class LoginCI(BaseModel):
    ci: str

class MesaCreate(BaseModel):
    eleccion_id: int
    numero: int

class AsignarJefe(BaseModel):
    mesa_id: int
    usuario_id: int

class VotoCreate(BaseModel):
    candidato_id: int
    eleccion_id: int
