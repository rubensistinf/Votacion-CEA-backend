from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
import models, schemas
from database import get_db
from auth import require_role
from sqlalchemy import func
import random
from utils import log_audit

router = APIRouter(prefix="/admin", tags=["Admin"])
admin_dependency = Depends(require_role(["admin"]))

# ─── ELECCIONES ───
@router.post("/elecciones", response_model=schemas.EleccionResponse)
def crear_eleccion(eleccion: schemas.EleccionCreate, request: Request, db: Session = Depends(get_db), admin: models.Usuario = Depends(require_role(["admin"]))):
    db_eleccion = models.Eleccion(nombre=eleccion.nombre)
    db.add(db_eleccion)
    db.commit()
    db.refresh(db_eleccion)
    log_audit(db, admin.id, "CREAR_ELECCION", f"Nombre: {db_eleccion.nombre} (ID: {db_eleccion.id})", request)
    db.commit() # Asegurar que el log se guarde
    return db_eleccion

@router.get("/elecciones", response_model=list[schemas.EleccionResponse], dependencies=[Depends(require_role(["admin", "secretaria"]))])
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

@router.delete("/elecciones/{eleccion_id}")
def eliminar_eleccion(eleccion_id: int, request: Request, db: Session = Depends(get_db), admin: models.Usuario = Depends(require_role(["admin"]))):
    eleccion = db.query(models.Eleccion).filter(models.Eleccion.id == eleccion_id).first()
    if not eleccion:
        raise HTTPException(status_code=404, detail="Elección no encontrada")

    # 1. Eliminar votos y candidatos
    db.query(models.Voto).filter(models.Voto.eleccion_id == eleccion_id).delete()
    db.query(models.Candidato).filter(models.Candidato.eleccion_id == eleccion_id).delete()
    
    # 2. Buscar mesas de esta elección y eliminar Jefes y Asignaciones
    mesas_ids = [m.id for m in db.query(models.Mesa).filter(models.Mesa.eleccion_id == eleccion_id).all()]
    if mesas_ids:
        db.query(models.AsignacionMesa).filter(models.AsignacionMesa.mesa_id.in_(mesas_ids)).delete(synchronize_session=False)
        db.query(models.JefeMesa).filter(models.JefeMesa.mesa_id.in_(mesas_ids)).delete(synchronize_session=False)
    
    # 3. Eliminar Mesas
    db.query(models.Mesa).filter(models.Mesa.eleccion_id == eleccion_id).delete()
    
    # 4. Restablecer el Padrón (Mantiene a la gente, pero borra su estado de "ha_votado" y "habilitado")
    db.query(models.Votante).update({"ha_votado": False, "habilitado": False})
    
    # 5. Restituir cualquier usuario que era Jefe a Votante normal
    db.query(models.Usuario).filter(models.Usuario.rol == "jefe").update({"rol": "votante"})
    
    # 6. Finalmente borrar la elección
    nombre_old = eleccion.nombre
    db.delete(eleccion)
    db.commit()
    
    log_audit(db, admin.id, "BORRAR_ELECCION", f"Eliminó elección '{nombre_old}' (ID: {eleccion_id}) y reinició padrón.", request)
    
    return {"msg": "🗑️ Elección eliminada drásticamente. Todo reiniciado al estado inicial."}

# ─── MESAS ───
@router.post("/mesas", dependencies=[admin_dependency])
def crear_mesa(mesa_req: schemas.MesaCreate, db: Session = Depends(get_db)):
    """Genera mesas automáticamente para que el total coincida exactamente con la cantidad solicitada."""
    mesas_actuales = db.query(models.Mesa).filter(models.Mesa.eleccion_id == mesa_req.eleccion_id).order_by(models.Mesa.numero).all()
    total_actual = len(mesas_actuales)
    
    if mesa_req.cantidad == total_actual:
        return {"msg": f"Ya existen exactamente {mesa_req.cantidad} mesas.", "desde": None, "hasta": None}
        
    elif mesa_req.cantidad > total_actual:
        # Faltan mesas, creamos las necesarias
        start_num = total_actual + 1
        diferencia = mesa_req.cantidad - total_actual
        for i in range(diferencia):
            db_mesa = models.Mesa(eleccion_id=mesa_req.eleccion_id, numero=start_num + i)
            db.add(db_mesa)
        db.commit()
        return {"msg": f"Se añadieron {diferencia} nuevas mesas (Total: {mesa_req.cantidad}).", "desde": start_num, "hasta": mesa_req.cantidad}
        
    else:
        # Hay más mesas de las requeridas, eliminamos las sobrantes (desde el final)
        mesas_sobrantes = db.query(models.Mesa).filter(
            models.Mesa.eleccion_id == mesa_req.eleccion_id, 
            models.Mesa.numero > mesa_req.cantidad
        ).all()
        
        cant_eliminadas = 0
        for mesa in mesas_sobrantes:
            # Eliminar dependencias
            db.query(models.JefeMesa).filter(models.JefeMesa.mesa_id == mesa.id).delete()
            db.query(models.AsignacionMesa).filter(models.AsignacionMesa.mesa_id == mesa.id).delete()
            db.delete(mesa)
            cant_eliminadas += 1
            
        db.commit()
        return {"msg": f"Se ajustó la capacidad. Se eliminaron {cant_eliminadas} mesas sobrantes (Total exacto: {mesa_req.cantidad}).", "desde": None, "hasta": None}

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

@router.post("/asignar-jefe-ci")
def asignar_jefe_por_ci(datos: schemas.AsignarJefeCI, request: Request, db: Session = Depends(get_db), admin: models.Usuario = Depends(require_role(["admin"]))):
    """Busca un votante y lo asigna automáticamente a la siguiente mesa libre de la elección."""
    votante = db.query(models.Votante).filter(models.Votante.ci == datos.ci).first()
    if not votante:
        raise HTTPException(status_code=404, detail=f"Votante con CI {datos.ci} no encontrado en el padrón.")

    # Buscar todas las mesas de la elección
    eleccion = db.query(models.Eleccion).filter(models.Eleccion.id == datos.eleccion_id).first()
    if not eleccion:
        raise HTTPException(status_code=404, detail="La elección especificada no existe.")
    
    if not eleccion.activa and not eleccion.resultados_publicados:
         raise HTTPException(status_code=400, detail="La elección debe estar abierta para asignar Jefes.")

    mesas_eleccion = db.query(models.Mesa).filter(models.Mesa.eleccion_id == datos.eleccion_id).order_by(models.Mesa.numero).all()
    if not mesas_eleccion:
        raise HTTPException(status_code=400, detail="No hay mesas creadas en esta elección. Primero crea mesas en el Paso 2.")

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
    log_audit(db, admin.id, "ASIGNAR_JEFE", f"Asignó a {votante.nombre} (CI: {votante.ci}) a Mesa {mesa_asignar.numero}", request)
    db.commit() # Asegurar que el log se guarde
    return {
        "msg": f"✅ {votante.nombre} asignado automáticamente como Jefe de la Mesa Nº {mesa_asignar.numero}.",
        "jefe": votante.nombre,
        "mesa": mesa_asignar.numero
    }

@router.delete("/mesas/{mesa_id}")
def eliminar_mesa(mesa_id: int, request: Request, db: Session = Depends(get_db), admin: models.Usuario = Depends(require_role(["admin"]))):
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
    log_audit(db, admin.id, "ELIMINAR_MESA", f"Eliminó Mesa {mesa.numero} (ID: {mesa_id})", request)
    db.commit() # Asegurar que el log se guarde
    return {"msg": f"Mesa {mesa.numero} eliminada exitosamente. Los votantes asignados a ella deberán ser redistribuidos."}

@router.post("/distribuir-mesas/{eleccion_id}")
def distribuir_mesas(eleccion_id: int, request: Request, db: Session = Depends(get_db), admin: models.Usuario = Depends(require_role(["admin"]))):
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
    log_audit(db, admin.id, "SORTEO_MESAS", f"Distribuyó {asignados} votantes en {len(mesas)} mesas.", request)
    return {
        "msg": f"✅ Sorteo completado. {asignados} votantes distribuidos aleatoriamente en {len(mesas)} mesa(s).",
        "distribuidos": asignados,
        "mesas": len(mesas),
        "resumen": resumen_str
    }

# ─── RESULTADOS ───
@router.get("/resultados")
def obtener_resultados(eleccion_id: int, db: Session = Depends(get_db)):
    votos_agrupados = db.query(
        models.Candidato.id,
        models.Candidato.nombre,
        models.Candidato.sigla,
        models.Candidato.cargo,
        func.count(models.Voto.id).label("total_votos")
    ).outerjoin(models.Voto, (models.Voto.candidato_id == models.Candidato.id)) \
     .filter(models.Candidato.eleccion_id == eleccion_id) \
     .group_by(models.Candidato.id).order_by(func.count(models.Voto.id).desc()).all()
    return [{"candidato": v.nombre, "sigla": v.sigla, "cargo": v.cargo, "votos": v.total_votos} for v in votos_agrupados]

@router.get("/publicar-resultados", dependencies=[admin_dependency])
def publicar_resultados(eleccion_id: int, db: Session = Depends(get_db)):
    eleccion = db.query(models.Eleccion).filter(models.Eleccion.id == eleccion_id).first()
    if not eleccion:
        raise HTTPException(status_code=404, detail="Eleccion no encontrada")
    eleccion.activa = False
    eleccion.resultados_publicados = True
    db.commit()
    return {"msg": "Resultados publicados, elección cerrada definitivamente."}

@router.get("/stats", dependencies=[admin_dependency])
def obtener_estadisticas(eleccion_id: int = None, db: Session = Depends(get_db)):
    # Totales generales del sistema
    total_votantes = db.query(func.count(models.Votante.id)).scalar()
    
    # Filtro opcional por elección
    f_votos = db.query(func.count(models.Voto.id))
    f_cand = db.query(func.count(models.Candidato.id))
    f_mesa = db.query(func.count(models.Mesa.id))
    
    if eleccion_id:
        total_votos = f_votos.filter(models.Voto.eleccion_id == eleccion_id).scalar()
        total_candidatos = f_cand.filter(models.Candidato.eleccion_id == eleccion_id).scalar()
        total_mesas = f_mesa.filter(models.Mesa.eleccion_id == eleccion_id).scalar()
        total_habilitados = db.query(func.count(models.AsignacionMesa.id)).filter(models.AsignacionMesa.mesa_id.in_(
            db.query(models.Mesa.id).filter(models.Mesa.eleccion_id == eleccion_id)
        )).scalar()
    else:
        total_votos = f_votos.scalar()
        total_candidatos = f_cand.scalar()
        total_mesas = f_mesa.scalar()
        total_habilitados = db.query(func.count(models.Votante.id)).filter(models.Votante.habilitado == True).scalar()

    return {
        "total_votantes": total_votantes,
        "total_habilitados": total_habilitados,
        "total_votos": total_votos,
        "total_candidatos": total_candidatos,
        "total_mesas": total_mesas,
        "participacion": round((total_votos / total_habilitados * 100), 1) if total_habilitados else 0
    }

@router.post("/reset-sistema", dependencies=[admin_dependency])
def reset_sistema(request: Request, db: Session = Depends(get_db), admin: models.Usuario = Depends(require_role(["admin"]))):
    """Limpia todo el sistema dejando solo los 4 usuarios base (Cero Datos Nivel Pro)."""
    try:
        # 1. Borrar datos transaccionales
        db.query(models.Voto).delete()
        db.query(models.Candidato).delete()
        db.query(models.AuditLog).delete()
        db.query(models.AsignacionMesa).delete()
        db.query(models.JefeMesa).delete()
        db.query(models.Mesa).delete()
        db.query(models.Votante).delete()
        db.query(models.Eleccion).delete()
        
        # 2. Borrar usuarios adicionales que no sean los 4 base
        base_emails = ["admin@cea.com", "secretaria@cea.com", "jefe@cea.com", "votante@cea.com"]
        db.query(models.Usuario).filter(~models.Usuario.correo.in_(base_emails)).delete(synchronize_session=False)
        
        db.commit()
        
        # Registrar esta acción de reset como primer log post-limpieza
        nuevo_log = models.AuditLog(
            usuario_id=admin.id,
            accion="REINICIO_TOTAL",
            detalle="El administrador ejecutó un reinicio total del sistema (Cero Datos).",
            ip_address=request.client.host
        )
        db.add(nuevo_log)
        db.commit()
        
        return {"msg": "Sistema reiniciado exitosamente. Todos los datos electorales han sido borrados."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error durante el reinicio: {str(e)}")

@router.get("/forzar-migracion", dependencies=[admin_dependency])
def forzar_migracion(db: Session = Depends(get_db)):
    """Ruta de emergencia para forzar la creación de columnas faltantes en Render."""
    from migrate_db import migrate
    try:
        migrate()
        return {"msg": "Esquema sincronizado. Las columnas faltantes deberían estar activas."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en migración forzada: {str(e)}")


