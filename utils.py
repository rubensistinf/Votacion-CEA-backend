from fastapi import Request
from sqlalchemy.orm import Session
import models

def log_audit(db: Session, user_id: int, action: str, detail: str, request: Request = None):
    """
    Registra una acción en la tabla de auditoría.
    """
    ip = request.client.host if request and request.client else "Interno"
    db_log = models.AuditLog(
        usuario_id=user_id,
        accion=action,
        detalle=detail,
        ip_address=ip
    )
    db.add(db_log)
    db.commit()
