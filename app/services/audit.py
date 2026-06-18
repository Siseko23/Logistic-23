from app.models import db, AuditLog
from flask import request as flask_request


def log_action(user_id, action: str, entity_type: str = None,
               entity_id: str = None, detail: str = None):
    try:
        ip = flask_request.remote_addr
    except RuntimeError:
        ip = None
    entry = AuditLog(
        user_id=user_id, action=action,
        entity_type=entity_type, entity_id=entity_id,
        detail=detail, ip_address=ip
    )
    db.session.add(entry)
