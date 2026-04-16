from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from sqlalchemy.orm import Session
import models, schemas
from database import get_db
from auth import require_role, get_password_hash
from utils import log_audit
import openpyxl
from io import BytesIO

router = APIRouter(prefix="/secretaria", tags=["Secretaria"])
secretaria_dependency = Depends(require_role(["admin", "secretaria"]))

@router.post("/usuarios", response_model=schemas.VotanteResponse)
def inscribir_votante(votante: schemas.VotanteCreate, request: Request, db: Session = Depends(get_db), user: models.Usuario = Depends(require_role(["admin", "secretaria"]))):
    # Validar si ya existe
    existe = db.query(models.Votante).filter(models.Votante.ci == votante.ci).first()
    if existe:
        raise HTTPException(status_code=400, detail="El votante ya está registrado.")
    
    # Generar correo base: nombre.apellidopaterno@cea.com
    partes = votante.nombre.strip().lower().split()
    if len(partes) >= 2:
        correo = f"{partes[0]}.{partes[1]}@cea.com"
    else:
        correo = f"{partes[0]}@cea.com"
    
    # Manejar correos duplicados adjuntando C.I. si es necesario
    if db.query(models.Votante).filter(models.Votante.correo == correo).first():
        correo = f"{correo.split('@')[0]}{votante.ci}@cea.com"

    db_votante = models.Votante(ci=votante.ci, nombre=votante.nombre, correo=correo)
    db.add(db_votante)
    
    # Crear su cuenta de usuario para login
    pwd_hash = get_password_hash(votante.ci)
    db_usuario = models.Usuario(correo=correo, password_hash=pwd_hash, rol="votante")
    db.add(db_usuario)
    
    db.refresh(db_votante)
    log_audit(db, user.id, "INSCRIBIR_VOTANTE", f"Inscribió individual: {db_votante.nombre} (CI: {db_votante.ci})", request)
    return db_votante

@router.get("/votantes", dependencies=[secretaria_dependency])
def listar_votantes(db: Session = Depends(get_db)):
    votantes = db.query(models.Votante).all()
    return [{"ci": v.ci, "nombre": v.nombre, "correo": v.correo, "habilitado": v.habilitado, "ha_votado": v.ha_votado} for v in votantes]

@router.post("/candidatos", response_model=schemas.CandidatoResponse)
def registrar_candidato(candidato: schemas.CandidatoCreate, request: Request, db: Session = Depends(get_db), user: models.Usuario = Depends(require_role(["admin", "secretaria"]))):
    db_candidato = models.Candidato(**candidato.model_dump(exclude={'ci_representante'}))
    db.add(db_candidato)
    db.flush()  # Para obtener el id del candidato
    
    # Asignar imagen_base64 por defecto (1.png, 2.png, etc) según el orden de inscripción si no se subió una
    if not db_candidato.imagen_base64:
        orden = db.query(models.Candidato).filter(models.Candidato.eleccion_id == candidato.eleccion_id, models.Candidato.id <= db_candidato.id).count()
        db_candidato.imagen_base64 = f"../candidatos/{orden}.png"
    
    # Si el candidato tiene CI, also inscribirlo como votante
    if candidato.ci_representante:
        ci = candidato.ci_representante.strip()
        existe_votante = db.query(models.Votante).filter(models.Votante.ci == ci).first()
        if not existe_votante:
            partes = candidato.nombre.strip().lower().split()
            p1 = partes[0] if len(partes) > 0 else 'candidato'
            p2 = partes[1] if len(partes) > 1 else ci
            correo = f"{p1}.{p2}@cea.com"
            if db.query(models.Votante).filter(models.Votante.correo == correo).first():
                correo = f"{p1}.{p2}{ci}@cea.com"
            db_votante = models.Votante(ci=ci, nombre=candidato.nombre, correo=correo)
            db.add(db_votante)
            pwd_hash = get_password_hash(ci)
            db_usuario = models.Usuario(correo=correo, password_hash=pwd_hash, rol="votante")
            db.add(db_usuario)
    
    db.refresh(db_candidato)
    log_audit(db, user.id, "REGISTRAR_CANDIDATO", f"Candidato: {db_candidato.nombre} para elección {db_candidato.eleccion_id}", request)
    return db_candidato

@router.get("/votantes/buscar/{ci}", dependencies=[secretaria_dependency])
def buscar_votante(ci: str, db: Session = Depends(get_db)):
    votante = db.query(models.Votante).filter(models.Votante.ci == ci).first()
    if not votante:
        raise HTTPException(status_code=404, detail="No registrado")
    return {"ci": votante.ci, "nombre": votante.nombre, "correo": votante.correo}

@router.post("/inscribir-texto-lote")
def inscribir_texto_lote(datos: schemas.VotanteLoteRequest, request: Request, db: Session = Depends(get_db), user: models.Usuario = Depends(require_role(["admin", "secretaria"]))):
    registrados = 0
    errores = 0
    for v in datos.votantes:
        ci = str(v.ci).strip()
        nombres = str(v.nombres).strip()
        apellidos = str(v.apellidos).strip()
        nombre_completo = f"{nombres} {apellidos}".strip()
        
        # Validar si existe
        if db.query(models.Votante).filter(models.Votante.ci == ci).first():
            errores += 1
            continue
            
        partes = nombres.lower().split()
        ape_partes = apellidos.lower().split()
        p1 = partes[0] if partes else "estudiante"
        p2 = ape_partes[0] if ape_partes else ci
        
        correo = f"{p1}.{p2}@cea.com"
        if db.query(models.Votante).filter(models.Votante.correo == correo).first():
            correo = f"{p1}.{p2}{ci}@cea.com"
            
        db_votante = models.Votante(ci=ci, nombre=nombre_completo, correo=correo)
        db.add(db_votante)
        
        pwd_hash = get_password_hash(ci)
        db_usuario = models.Usuario(correo=correo, password_hash=pwd_hash, rol="votante")
        db.add(db_usuario)
        
    db.commit()
    log_audit(db, user.id, "INSCRIBIR_LOTE_TEXTO", f"Registró {registrados} votantes (omitió {errores} duplicados).", request)
    return {"registrados": registrados, "omitidos": errores}

@router.post("/inscribir-lote")
async def inscribir_lote(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db), user: models.Usuario = Depends(require_role(["admin", "secretaria"]))):
    if not file.filename.endswith(('.xlsx')):
        raise HTTPException(status_code=400, detail="El archivo debe ser un Excel .xlsx")
    
    contents = await file.read()
    wb = openpyxl.load_workbook(filename=BytesIO(contents), data_only=True)
    sheet = wb.active
    
    registrados = 0
    errores = 0
    
    # Suponiendo columnas: "CI", "Nombres", "Apellidos"
    # Tomaremos la primera fila como header
    headers = [str(cell.value).strip().lower() for cell in sheet[1] if cell.value]
    
    ci_idx = -1
    nom_idx = -1
    ape_idx = -1
    
    for i, h in enumerate(headers):
        if 'ci' in h: ci_idx = i
        elif 'nombre' in h: nom_idx = i
        elif 'apellido' in h: ape_idx = i
        
    if ci_idx == -1 or (nom_idx == -1 and ape_idx == -1):
        raise HTTPException(status_code=400, detail="Formato inválido. Debe tener columnas: CI, Nombres, Apellidos")
        
    for row in sheet.iter_rows(min_row=2, values_only=True):
        if not row[ci_idx]:
            continue
            
        ci = str(row[ci_idx]).strip()
        nombres = str(row[nom_idx] or "").strip()
        apellidos = str(row[ape_idx] or "") if ape_idx != -1 else ""
        nombre_completo = f"{nombres} {apellidos}".strip()
        
        # Validar si existe
        if db.query(models.Votante).filter(models.Votante.ci == ci).first():
            errores += 1
            continue
            
        partes = nombres.lower().split()
        ape_partes = apellidos.lower().split()
        
        p1 = partes[0] if partes else ""
        p2 = ape_partes[0] if ape_partes else ""
        
        if p1 and p2:
            correo = f"{p1}.{p2}@cea.com"
        else:
            correo = f"{p1 or p2}@cea.com"
            
        # Manejar correos duplicados
        if db.query(models.Votante).filter(models.Votante.correo == correo).first():
            correo = f"{correo.split('@')[0]}{ci}@cea.com"
            
        db_votante = models.Votante(ci=ci, nombre=nombre_completo, correo=correo)
        db.add(db_votante)
        
        pwd_hash = get_password_hash(ci)
        db_usuario = models.Usuario(correo=correo, password_hash=pwd_hash, rol="votante")
        db.add(db_usuario)
    db.commit()
    log_audit(db, user.id, "INSCRIBIR_LOTE_EXCEL", f"Archivo: {file.filename}. Registró {registrados} votantes (omitió {errores}).", request)
    return {"msg": f"Procesamiento listo", "registrados": registrados, "omitidos": errores}
