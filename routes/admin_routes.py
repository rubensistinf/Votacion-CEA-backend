from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import models, schemas
from database import get_db
from auth import require_role
from sqlalchemy import func

router = APIRouter(prefix="/admin", tags=["Admin"])
# Este Depends asegura que todos los endpoints aqui requieren rol admin
admin_dependency = Depends(require_role(["admin"]))

@router.post("/elecciones", response_model=schemas.EleccionResponse, dependencies=[admin_dependency])
def crear_eleccion(eleccion: schemas.EleccionCreate, db: Session = Depends(get_db)):
    db_eleccion = models.Eleccion(nombre=eleccion.nombre, activa=True)
    db.add(db_eleccion)
    db.commit()
    db.refresh(db_eleccion)
    return db_eleccion

@router.get("/elecciones", response_model=list[schemas.EleccionResponse], dependencies=[admin_dependency])
def listar_elecciones(db: Session = Depends(get_db)):
    return db.query(models.Eleccion).all()

@router.post("/mesas", dependencies=[admin_dependency])
def crear_mesa(mesa: schemas.MesaCreate, db: Session = Depends(get_db)):
    db_mesa = models.Mesa(eleccion_id=mesa.eleccion_id, numero=mesa.numero)
    db.add(db_mesa)
    db.commit()
    db.refresh(db_mesa)
    return db_mesa

@router.post("/asignar-jefe", dependencies=[admin_dependency])
def asignar_jefe(asignacion: schemas.AsignarJefe, db: Session = Depends(get_db)):
    db_jefe = models.JefeMesa(mesa_id=asignacion.mesa_id, usuario_id=asignacion.usuario_id)
    db.add(db_jefe)
    db.commit()
    return {"msg": "Jefe asignado a mesa exitosamente"}

@router.get("/resultados")
def obtener_resultados(db: Session = Depends(get_db)):
    votos_agrupados = db.query(
        models.Candidato.id,
        models.Candidato.nombre,
        models.Candidato.sigla,
        models.Candidato.cargo,
        func.count(models.Voto.id).label("total_votos")
    ).outerjoin(models.Voto, models.Voto.candidato_id == models.Candidato.id
    ).group_by(models.Candidato.id).order_by(func.count(models.Voto.id).desc()).all()
    
    return [{"candidato": v.nombre, "sigla": v.sigla, "cargo": v.cargo, "votos": v.total_votos} for v in votos_agrupados]


@router.post("/publicar-resultados", dependencies=[admin_dependency])
def publicar_resultados(eleccion_id: int, db: Session = Depends(get_db)):
    eleccion = db.query(models.Eleccion).filter(models.Eleccion.id == eleccion_id).first()
    if not eleccion:
        raise HTTPException(status_code=404, detail="Eleccion no encontrada")
    eleccion.activa = False
    db.commit()
    return {"msg": "Resultados publicados, elección cerrada."}
