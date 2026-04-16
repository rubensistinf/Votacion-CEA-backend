from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import models, schemas
from database import get_db
from auth import require_role
from sqlalchemy import func
import random

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
def crear_mesa(mesa_req: schemas.MesaCreate, db: Session = Depends(get_db)):
    """Genera N mesas automáticamente empezando por el número siguiente disponible."""
    # Obtener el número máximo actual
    max_mesa = db.query(func.max(models.Mesa.numero)).filter(models.Mesa.eleccion_id == mesa_req.eleccion_id).scalar()
    start_num = (max_mesa or 0) + 1

    nuevas_mesas = []
    for i in range(mesa_req.cantidad):
        db_mesa = models.Mesa(eleccion_id=mesa_req.eleccion_id, numero=start_num + i)
        db.add(db_mesa)
        nuevas_mesas.append(db_mesa)
        
    db.commit()
    return {"msg": f"Se generaron {mesa_req.cantidad} mesas con éxito.", "desde": start_num, "hasta": start_num + mesa_req.cantidad - 1}

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
    """Busca un votante y lo asigna automáticamente a la siguiente mesa libre de la elección."""
    votante = db.query(models.Votante).filter(models.Votante.ci == datos.ci).first()
    if not votante:
        raise HTTPException(status_code=404, detail=f"Votante con CI {datos.ci} no encontrado en el padrón.")

    # Buscar todas las mesas de la elección
    mesas_eleccion = db.query(models.Mesa).filter(models.Mesa.eleccion_id == datos.eleccion_id).order_by(models.Mesa.numero).all()
    if not mesas_eleccion:
        raise HTTPException(status_code=400, detail="No se han creado mesas para esta elección.")

    # Buscar la primera mesa que no tenga jefe
    mesa_asignar = None
    for m in mesas_eleccion:
        tiene_jefe = db.query(models.JefeMesa).filter(models.JefeMesa.mesa_id == m.id).first()
        if not tiene_jefe:
            mesa_asignar = m
            break
            
    if not mesa_asignar:
        raise HTTPException(status_code=400, detail="Todas las mesas actuales ya tienen un Jefe asignado. Por favor, crea más mesas.")

    # Actualizar cuenta de usuario con rol 'jefe'
    usuario = db.query(models.Usuario).filter(models.Usuario.correo == votante.correo).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado. Debe estar inscrito primero.")
    usuario.rol = "jefe"

    # Asignar a JefeMesa
    db_jefe = models.JefeMesa(mesa_id=mesa_asignar.id, usuario_id=usuario.id, nombre_jefe=votante.nombre)
    db.add(db_jefe)
        
    # Asignarlo como votante a su propia mesa
    asignacion = db.query(models.AsignacionMesa).filter(models.AsignacionMesa.votante_ci == votante.ci).first()
    if asignacion:
        asignacion.mesa_id = mesa_asignar.id
        asignacion.mesa_numero = mesa_asignar.numero
    else:
        db_asignacion = models.AsignacionMesa(votante_ci=votante.ci, mesa_id=mesa_asignar.id, mesa_numero=mesa_asignar.numero)
        db.add(db_asignacion)

    db.commit()
    return {
        "msg": f"✅ {votante.nombre} asignado automáticamente como Jefe de la Mesa Nº {mesa_asignar.numero}.",
        "jefe": votante.nombre,
        "mesa": mesa_asignar.numero
    }

@router.delete("/mesas/{mesa_id}", dependencies=[admin_dependency])
def eliminar_mesa(mesa_id: int, db: Session = Depends(get_db)):
    mesa = db.query(models.Mesa).filter(models.Mesa.id == mesa_id).first()
    if not mesa:
        raise HTTPException(status_code=404, detail="Mesa no encontrada")
        
    # Eliminar relacion JefeMesa
    db.query(models.JefeMesa).filter(models.JefeMesa.mesa_id == mesa_id).delete()
    
    # Eliminar Asignaciones de Votantes a esta mesa (los devuelve al pozo sin mesa)
    db.query(models.AsignacionMesa).filter(models.AsignacionMesa.mesa_id == mesa_id).delete()
    
    # Eliminar la Mesa
    db.delete(mesa)
    db.commit()
    
    return {"msg": f"Mesa {mesa.numero} eliminada exitosamente. Los votantes asignados a ella deberán ser redistribuidos."}

@router.post("/distribuir-mesas/{eleccion_id}", dependencies=[admin_dependency])
def distribuir_mesas(eleccion_id: int, db: Session = Depends(get_db)):
    """Distribuye por sorteo aleatorio todos los votantes sin mesa entre las mesas disponibles."""
    mesas = db.query(models.Mesa).filter(models.Mesa.eleccion_id == eleccion_id).all()
    if not mesas:
        raise HTTPException(status_code=400, detail="No hay mesas creadas para esta elección.")

    # Votantes sin asignación de mesa
    asignados_ci = [a.votante_ci for a in db.query(models.AsignacionMesa).all()]
    pendientes = db.query(models.Votante).filter(~models.Votante.ci.in_(asignados_ci)).all()

    if not pendientes:
        return {"msg": "Todos los votantes ya tienen mesa asignada.", "distribuidos": 0}

    # ¡SORTEO ALEATORIO! Mezclar antes de asignar
    random.shuffle(pendientes)

    asignados = 0
    resumen = {m.numero: 0 for m in mesas}
    for i, votante in enumerate(pendientes):
        mesa = mesas[i % len(mesas)]
        asig = models.AsignacionMesa(
            votante_ci=votante.ci,
            mesa_id=mesa.id,
            mesa_numero=mesa.numero
        )
        db.add(asig)
        resumen[mesa.numero] += 1
        asignados += 1

    db.commit()
    resumen_str = " | ".join([f"Mesa {k}: {v} votantes" for k, v in sorted(resumen.items())])
    return {
        "msg": f"✅ Sorteo completado. {asignados} votantes distribuidos aleatoriamente en {len(mesas)} mesa(s).",
        "distribuidos": asignados,
        "mesas": len(mesas),
        "resumen": resumen_str
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
