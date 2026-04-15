from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import models, schemas
from database import get_db
from auth import require_role

router = APIRouter(prefix="/jefe", tags=["Jefe de Mesa"])
jefe_dependency = Depends(require_role(["admin", "jefe"]))

@router.get("/votante/{ci}", response_model=schemas.VotanteResponse, dependencies=[jefe_dependency])
def consultar_votante(ci: str, db: Session = Depends(get_db)):
    votante = db.query(models.Votante).filter(models.Votante.ci == ci).first()
    if not votante:
        raise HTTPException(status_code=404, detail="Votante no encontrado")
    return votante

@router.post("/validar-votante", dependencies=[jefe_dependency])
def validar_votante(ci: str, db: Session = Depends(get_db)):
    votante = db.query(models.Votante).filter(models.Votante.ci == ci).first()
    if not votante:
        raise HTTPException(status_code=404, detail="Votante no encontrado")
    
    if votante.habilitado:
        raise HTTPException(status_code=400, detail="Votante ya habilitado")
        
    votante.habilitado = True
    db.commit()
    return {"msg": "Votante habilitado para emitir su voto", "correo_login": votante.correo}
