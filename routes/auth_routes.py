from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta

from database import get_db
import models
import schemas
from auth import verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, get_password_hash
from utils import log_audit

router = APIRouter(tags=["Auth"])

@router.post("/login", response_model=schemas.Token)
def login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.Usuario).filter(models.Usuario.correo == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.correo, "rol": user.rol}, expires_delta=access_token_expires
    )
    log_audit(db, user.id, "LOGIN", f"Ingreso exitoso ({user.rol})", request)
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/login-ci", response_model=schemas.Token)
def login_con_ci(datos: schemas.LoginCI, request: Request, db: Session = Depends(get_db)):
    """Login especial para votantes usando solo su número de carnet (CI)."""
    # Buscar el votante por CI
    votante = db.query(models.Votante).filter(models.Votante.ci == datos.ci).first()
    if not votante:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Número de carnet no registrado en el padrón.",
        )
    # Buscar el usuario asociado
    usuario = db.query(models.Usuario).filter(models.Usuario.correo == votante.correo).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Cuenta de acceso no encontrada. Contacte a la secretaría.",
        )
    # Verificar que la contraseña (el CI) sea válida
    if not verify_password(datos.ci, usuario.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Error de autenticación. Contacte a la secretaría.",
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": usuario.correo, "rol": usuario.rol}, expires_delta=access_token_expires
    )
    log_audit(db, usuario.id, "LOGIN_CI", f"Ingreso de votante CI: {datos.ci}", request)
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/candidatos/publicos", response_model=list[schemas.CandidatoPublico])
def candidatos_publicos(db: Session = Depends(get_db)):
    """Endpoint público: muestra candidatos sin requerir autenticación."""
    return db.query(models.Candidato).all()
