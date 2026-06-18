"""
Notification service — push_notification()
"""
from app.models import db, Notification

def push_notification(user_id: int, title: str, body: str = "",
                       type: str = "info", ref_type: str = None, ref_id: str = None):
    """Create a notification record for a user."""
    note = Notification(
        user_id=user_id, title=title, body=body,
        type=type, ref_type=ref_type, ref_id=ref_id
    )
    db.session.add(note)
    # caller must commit
    return note


def notify_all_role(role: str, title: str, body: str = "", type: str = "info"):
    """Push notification to all users of a role."""
    from app.models import User
    users = User.query.filter_by(role=role, is_active=True).all()
    for u in users:
        push_notification(u.id, title, body, type)
