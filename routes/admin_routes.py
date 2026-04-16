from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import models, schemas
from database import get_db
from auth import require_role
from sqlalchemy import func

router = APIRouter(prefix="/admin", tags=["Admin"])
admin_dependency = Depends(require_role(["admin"]))

# ─── ELECCIONES ───
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
    eleccion = db.query(models.Eleccion).filter(models.Eleccion.id == eleccion_id).first()
    if not eleccion:
        raise HTTPException(status_code=404, detail="Elección no encontrada")
    eleccion.activa = not eleccion.activa
    db.commit()
    return {"msg": f"Elección {'abierta' if eleccion.activa else 'cerrada'}.", "activa": eleccion.activa}

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
        jefe_rec = db.query(models.JefeMesa).filter(models.JefeMesa.mesa_id == m.id).first()
        jefe_nombre = None
        if jefe_rec:
            jefe_nombre = jefe_rec.nombre_jefe or "—"
        # Contar votantes asignados a esta mesa
        total_asignados = db.query(func.count(models.AsignacionMesa.id)).filter(
            models.AsignacionMesa.mesa_id == m.id
        ).scalar()
        resultado.append({
            "id": m.id,
            "numero": m.numero,
            "jefe": jefe_nombre,
            "total_votantes": total_asignados
        })
    return resultado

@router.post("/asignar-jefe-ci", dependencies=[admin_dependency])
def asignar_jefe_por_ci(datos: schemas.AsignarJefeCI, db: Session = Depends(get_db)):
    """Busca un votante inscrito por su CI y lo designa como Jefe de Mesa."""
    # Buscar al votante
    votante = db.query(models.Votante).filter(models.Votante.ci == datos.ci).first()
    if not votante:
        raise HTTPException(status_code=404, detail=f"Votante con CI {datos.ci} no encontrado en el padrón.")

    # Buscar la mesa
    mesa = db.query(models.Mesa).filter(models.Mesa.id == datos.mesa_id).first()
    if not mesa:
        raise HTTPException(status_code=404, detail="Mesa no encontrada.")

    # Actualizar o crear su cuenta de usuario con rol 'jefe'
    usuario = db.query(models.Usuario).filter(models.Usuario.correo == votante.correo).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario del votante no encontrado. Debe estar inscrito primero.")
    usuario.rol = "jefe"

    # Crear o actualizar el registro JefeMesa
    jefe_existente = db.query(models.JefeMesa).filter(models.JefeMesa.mesa_id == datos.mesa_id).first()
    if jefe_existente:
        jefe_existente.usuario_id = usuario.id
        jefe_existente.nombre_jefe = votante.nombre
    else:
        db_jefe = models.JefeMesa(mesa_id=datos.mesa_id, usuario_id=usuario.id, nombre_jefe=votante.nombre)
        db.add(db_jefe)

    db.commit()
    return {
        "msg": f"✅ {votante.nombre} (CI: {datos.ci}) asignado como Jefe de Mesa {mesa.numero}.",
        "jefe": votante.nombre,
        "mesa": mesa.numero
    }

@router.post("/distribuir-mesas/{eleccion_id}", dependencies=[admin_dependency])
def distribuir_mesas(eleccion_id: int, db: Session = Depends(get_db)):
    """Distribuye todos los votantes sin mesa asignada entre las mesas disponibles (round-robin)."""
    mesas = db.query(models.Mesa).filter(models.Mesa.eleccion_id == eleccion_id).all()
    if not mesas:
        raise HTTPException(status_code=400, detail="No hay mesas creadas para esta elección.")

    # Votantes sin asignación de mesa
    asignados_ci = [a.votante_ci for a in db.query(models.AsignacionMesa).all()]
    pendientes = db.query(models.Votante).filter(~models.Votante.ci.in_(asignados_ci)).all()

    if not pendientes:
        return {"msg": "Todos los votantes ya tienen mesa asignada.", "distribuidos": 0}

    asignados = 0
    for i, votante in enumerate(pendientes):
        mesa = mesas[i % len(mesas)]  # Round-robin
        asig = models.AsignacionMesa(
            votante_ci=votante.ci,
            mesa_id=mesa.id,
            mesa_numero=mesa.numero
        )
        db.add(asig)
        asignados += 1

    db.commit()
    return {
        "msg": f"✅ {asignados} votantes distribuidos en {len(mesas)} mesa(s).",
        "distribuidos": asignados,
        "mesas": len(mesas)
    }

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
    total_votantes = db.query(func.count(models.Votante.id)).scalar()
    total_habilitados = db.query(func.count(models.Votante.id)).filter(models.Votante.habilitado == True).scalar()
    total_votos = db.query(func.count(models.Voto.id)).scalar()
    total_candidatos = db.query(func.count(models.Candidato.id)).scalar()
    total_mesas = db.query(func.count(models.Mesa.id)).scalar()
    return {
        "total_votantes": total_votantes,
        "total_habilitados": total_habilitados,
        "total_votos": total_votos,
        "total_candidatos": total_candidatos,
        "total_mesas": total_mesas,
        "participacion": round((total_votos / total_habilitados * 100), 1) if total_habilitados else 0
    }
