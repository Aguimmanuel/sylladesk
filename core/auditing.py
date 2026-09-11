"""The single function every mutation must call (convention #2).

Usage:
    audit(actor=request.user, action="submission.create", obj=submission, detail={"attempt": 2})
"""
from .models import AuditLog


def audit(*, actor, action, obj=None, object_type="", object_id="", detail=None):
    if obj is not None:
        object_type = object_type or type(obj).__name__
        object_id = object_id or str(getattr(obj, "pk", ""))
    return AuditLog.objects.create(
        actor=actor,
        action=action,
        object_type=object_type,
        object_id=object_id,
        detail=detail or {},
    )
