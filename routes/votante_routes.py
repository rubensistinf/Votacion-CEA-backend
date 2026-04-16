from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
import models, schemas
from database import get_db
from auth import require_role, get_current_user
import random
from utils import log_audit

router = APIRouter(prefix="/votante", tags=["Votante"])
votante_dependency = Depends(require_role(["votante", "jefe"]))

@router.get("/mi-info")
def mi_info(current_user: models.Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.rol not in ["votante", "jefe"]:
        raise HTTPException(status_code=403, detail="Acceso denegado")
    votante = db.query(models.Votante).filter(models.Votante.correo == current_user.correo).first()
    if not votante:
        raise HTTPException(status_code=404, detail="Votante no encontrado")

    # Buscar su asignación de mesa
    asig = db.query(models.AsignacionMesa).filter(models.AsignacionMesa.votante_ci == votante.ci).first()
    mesa_numero = asig.mesa_numero if asig else None
    nombre_jefe = None

    if asig:
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

@router.get("/candidatos")
def listar_candidatos(current_user: models.Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.rol not in ["votante", "jefe", "secretaria", "admin"]:
        raise HTTPException(status_code=403, detail="Acceso denegado")
    return db.query(models.Candidato).all()

@router.post("/votar")
def emitir_voto(voto: schemas.VotoCreate, request: Request, current_user: models.Usuario = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.rol not in ["votante", "jefe"]:
        raise HTTPException(status_code=403, detail="Acceso denegado")

    # Verificar que la elección esté activa (votación abierta)
    eleccion = db.query(models.Eleccion).filter(models.Eleccion.id == voto.eleccion_id).first()
    if not eleccion:
        raise HTTPException(status_code=404, detail="Elección no encontrada.")
    if not eleccion.activa:
        raise HTTPException(status_code=403, detail="La votación está cerrada. El administrador aún no ha habilitado el proceso electoral.")

    votante = db.query(models.Votante).filter(models.Votante.correo == current_user.correo).first()
    if not votante:
        raise HTTPException(status_code=403, detail="Votante no encontrado en padrón")
    if not votante.habilitado:
        raise HTTPException(status_code=403, detail="Aún no ha sido validado por el Jefe de Mesa. Diríjase a su mesa asignada.")
    if votante.ha_votado:
        raise HTTPException(status_code=403, detail="Ya ha emitido su voto anteriormente.")

    db_voto = models.Voto(candidato_id=voto.candidato_id, eleccion_id=voto.eleccion_id)
    db.add(db_voto)
    votante.ha_votado = True
    db.commit()
    log_audit(db, current_user.id, "VOTO_EMITIDO", f"Elección ID: {voto.eleccion_id}", request)
    db.commit()
    return {"msg": "Voto registrado exitosamente.", "eleccion": eleccion.nombre}

@router.get("/estado-eleccion")
def estado_eleccion(db: Session = Depends(get_db)):
    """Endpoint público: devuelve si hay una elección activa y su info."""
    eleccion = db.query(models.Eleccion).filter(models.Eleccion.activa == True).first()
    if eleccion:
        return {"activa": True, "id": eleccion.id, "nombre": eleccion.nombre, "resultados_publicados": eleccion.resultados_publicados}
    # Si no hay activa, retornar la última
    ultima = db.query(models.Eleccion).order_by(models.Eleccion.id.desc()).first()
    if ultima:
        return {"activa": False, "id": ultima.id, "nombre": ultima.nombre, "resultados_publicados": ultima.resultados_publicados}
    return {"activa": False, "id": None, "nombre": None, "resultados_publicados": False}
