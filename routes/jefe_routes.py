from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import models, schemas
from database import get_db
from auth import require_role

router = APIRouter(prefix="/jefe", tags=["Jefe de Mesa"])
jefe_dependency = Depends(require_role(["admin", "jefe"]))

@router.get("/votante/{ci}")
def consultar_votante(ci: str, db: Session = Depends(get_db), current_user: models.Usuario = Depends(require_role(["admin", "jefe"]))):
    votante = db.query(models.Votante).filter(models.Votante.ci == ci).first()
    if not votante:
        raise HTTPException(status_code=404, detail="Votante no encontrado")
        
    asignacion = db.query(models.AsignacionMesa).filter(models.AsignacionMesa.votante_ci == ci).first()
    mesa_numero = asignacion.mesa_numero if asignacion else "Sin mesa"
    
    return {
        "ci": votante.ci,
        "nombre": votante.nombre,
        "correo": votante.correo,
        "habilitado": votante.habilitado,
        "ha_votado": votante.ha_votado,
        "mesa": mesa_numero
    }

@router.post("/validar-votante")
def validar_votante(ci: str, db: Session = Depends(get_db), current_user: models.Usuario = Depends(require_role(["admin", "jefe"]))):
    votante = db.query(models.Votante).filter(models.Votante.ci == ci).first()
    if not votante:
        raise HTTPException(status_code=404, detail="Votante no encontrado")
    
    # ─── VERIFICACIÓN DE MESA ───
    if current_user.rol == "jefe":
        jefe_record = db.query(models.JefeMesa).filter(models.JefeMesa.usuario_id == current_user.id).first()
        if not jefe_record:
            raise HTTPException(status_code=400, detail="Tú (Jefe) no tienes mesa asignada.")
        asignacion = db.query(models.AsignacionMesa).filter(models.AsignacionMesa.votante_ci == ci).first()
        if not asignacion:
            raise HTTPException(status_code=400, detail="⚠️ Este estudiante no tiene mesa asignada. Asegúrate de que el Administrador haya realizado el SORTEO DE MESAS (Paso 3).")
            
        if asignacion.mesa_id != jefe_record.mesa_id:
            mesa_jefe = db.query(models.Mesa).filter(models.Mesa.id == jefe_record.mesa_id).first()
            num_jefe = mesa_jefe.numero if mesa_jefe else '?'
            raise HTTPException(status_code=403, detail=f"❌ No puedes habilitar a este votante. Tú controlas la Mesa {num_jefe}, pero el estudiante pertenece a la Mesa {asignacion.mesa_numero}.")

    if votante.habilitado:
        raise HTTPException(status_code=400, detail="Votante ya habilitado")
        
    votante.habilitado = True
    db.commit()
    return {"msg": "✅ Votante habilitado exitosamente", "correo_login": votante.correo}
