from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import models, schemas
from database import get_db
from auth import require_role, get_password_hash

router = APIRouter(prefix="/secretaria", tags=["Secretaria"])
secretaria_dependency = Depends(require_role(["admin", "secretaria"]))

@router.post("/usuarios", response_model=schemas.VotanteResponse, dependencies=[secretaria_dependency])
def inscribir_votante(votante: schemas.VotanteCreate, db: Session = Depends(get_db)):
    # Validar si ya existe
    existe = db.query(models.Votante).filter(models.Votante.ci == votante.ci).first()
    if existe:
        raise HTTPException(status_code=400, detail="El votante ya está registrado.")
    
    # Generar correo base: nombre.apellido@ceapailon.com
    nombre_limpio = votante.nombre.strip().lower().replace(" ", ".")
    correo = f"{nombre_limpio}@ceapailon.com"
    
    db_votante = models.Votante(ci=votante.ci, nombre=votante.nombre, correo=correo)
    db.add(db_votante)
    
    # Crear su cuenta de usuario para login
    pwd_hash = get_password_hash(votante.ci)
    db_usuario = models.Usuario(correo=correo, password_hash=pwd_hash, rol="votante")
    db.add(db_usuario)
    
    db.commit()
    db.refresh(db_votante)
    return db_votante

@router.post("/candidatos", response_model=schemas.CandidatoResponse, dependencies=[secretaria_dependency])
def registrar_candidato(candidato: schemas.CandidatoCreate, db: Session = Depends(get_db)):
    db_candidato = models.Candidato(**candidato.model_dump())
    db.add(db_candidato)
    db.commit()
    db.refresh(db_candidato)
    return db_candidato
