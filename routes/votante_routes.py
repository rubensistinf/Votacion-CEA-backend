from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import models, schemas
from database import get_db
from auth import require_role, get_current_user

router = APIRouter(prefix="/votante", tags=["Votante"])
votante_dependency = Depends(require_role(["votante"]))

@router.get("/mi-info", dependencies=[votante_dependency])
def mi_info(current_user: models.Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    votante = db.query(models.Votante).filter(models.Votante.correo == current_user.correo).first()
    if not votante:
        raise HTTPException(status_code=404, detail="Votante no encontrado")

    # Buscar su asignación de mesa
    asig = db.query(models.AsignacionMesa).filter(models.AsignacionMesa.votante_ci == votante.ci).first()
    mesa_numero = asig.mesa_numero if asig else None
    nombre_jefe = None

    if asig:
        # Obtener el jefe de esa mesa
        jefe_rec = db.query(models.JefeMesa).filter(models.JefeMesa.mesa_id == asig.mesa_id).first()
        if jefe_rec and jefe_rec.nombre_jefe:
            nombre_jefe = jefe_rec.nombre_jefe

    return {
        "nombre": votante.nombre,
        "ci": votante.ci,
        "correo": votante.correo,
        "habilitado": votante.habilitado,
        "ha_votado": votante.ha_votado,
        "mesa_numero": mesa_numero,
        "nombre_jefe": nombre_jefe
    }

@router.get("/candidatos", response_model=list[schemas.CandidatoResponse], dependencies=[votante_dependency])
def listar_candidatos(db: Session = Depends(get_db)):
    return db.query(models.Candidato).all()

@router.post("/votar", dependencies=[votante_dependency])
def emitir_voto(voto: schemas.VotoCreate, current_user: models.Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    votante = db.query(models.Votante).filter(models.Votante.correo == current_user.correo).first()

    if not votante:
        raise HTTPException(status_code=403, detail="Votante no encontrado en padrón")

    if not votante.habilitado:
        raise HTTPException(status_code=403, detail="Aún no ha sido validado por el Jefe de Mesa. Pase por su mesa primero.")

    if votante.ha_votado:
        raise HTTPException(status_code=403, detail="Ya ha emitido su voto")

    db_voto = models.Voto(candidato_id=voto.candidato_id, eleccion_id=voto.eleccion_id)
    db.add(db_voto)
    votante.ha_votado = True
    db.commit()
    return {"msg": "Voto registrado exitosamente."}
