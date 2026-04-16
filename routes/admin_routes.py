from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import models, schemas
from database import get_db
from auth import require_role
from sqlalchemy import func

router = APIRouter(prefix="/admin", tags=["Admin"])
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

@router.post("/elecciones/{eleccion_id}/toggle", dependencies=[admin_dependency])
def toggle_eleccion(eleccion_id: int, db: Session = Depends(get_db)):
    """Abrir o cerrar (toggle) el estado activo de una elección."""
    eleccion = db.query(models.Eleccion).filter(models.Eleccion.id == eleccion_id).first()
    if not eleccion:
        raise HTTPException(status_code=404, detail="Elección no encontrada")
    eleccion.activa = not eleccion.activa
    db.commit()
    estado = "abierta" if eleccion.activa else "cerrada"
    return {"msg": f"Elección {estado}.", "activa": eleccion.activa}

# ─── MESAS ───
@router.post("/mesas", dependencies=[admin_dependency])
def crear_mesa(mesa: schemas.MesaCreate, db: Session = Depends(get_db)):
    db_mesa = models.Mesa(eleccion_id=mesa.eleccion_id, numero=mesa.numero)
    db.add(db_mesa)
    db.commit()
    db.refresh(db_mesa)
    return {"id": db_mesa.id, "numero": db_mesa.numero, "eleccion_id": db_mesa.eleccion_id}

@router.get("/mesas/{eleccion_id}", dependencies=[admin_dependency])
def listar_mesas(eleccion_id: int, db: Session = Depends(get_db)):
    mesas = db.query(models.Mesa).filter(models.Mesa.eleccion_id == eleccion_id).all()
    resultado = []
    for m in mesas:
        jefe = db.query(models.JefeMesa).filter(models.JefeMesa.mesa_id == m.id).first()
        jefe_info = None
        if jefe:
            u = db.query(models.Usuario).filter(models.Usuario.id == jefe.usuario_id).first()
            jefe_info = u.correo if u else "—"
        resultado.append({"id": m.id, "numero": m.numero, "jefe": jefe_info})
    return resultado

@router.post("/asignar-jefe", dependencies=[admin_dependency])
def asignar_jefe(asignacion: schemas.AsignarJefe, db: Session = Depends(get_db)):
    # Verificar si ya tiene jefe asignado y actualizar
    existente = db.query(models.JefeMesa).filter(models.JefeMesa.mesa_id == asignacion.mesa_id).first()
    if existente:
        existente.usuario_id = asignacion.usuario_id
    else:
        db_jefe = models.JefeMesa(mesa_id=asignacion.mesa_id, usuario_id=asignacion.usuario_id)
        db.add(db_jefe)
    db.commit()
    return {"msg": "Jefe asignado a mesa exitosamente"}

@router.get("/usuarios-jefe", dependencies=[admin_dependency])
def listar_usuarios_jefe(db: Session = Depends(get_db)):
    """Listar todos los usuarios con rol jefe para asignarlos a mesas."""
    jefes = db.query(models.Usuario).filter(models.Usuario.rol == "jefe").all()
    return [{"id": u.id, "correo": u.correo} for u in jefes]

# ─── RESULTADOS ───
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

@router.get("/stats", dependencies=[admin_dependency])
def obtener_estadisticas(db: Session = Depends(get_db)):
    """Estadísticas generales para el dashboard del admin."""
    total_votantes = db.query(func.count(models.Votante.id)).scalar()
    total_habilitados = db.query(func.count(models.Votante.id)).filter(models.Votante.habilitado == True).scalar()
    total_votos = db.query(func.count(models.Voto.id)).scalar()
    total_candidatos = db.query(func.count(models.Candidato.id)).scalar()
    return {
        "total_votantes": total_votantes,
        "total_habilitados": total_habilitados,
        "total_votos": total_votos,
        "total_candidatos": total_candidatos,
        "participacion": round((total_votos / total_habilitados * 100), 1) if total_habilitados else 0
    }
