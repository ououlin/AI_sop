"""社区模型提交与审核。

租户提交检测模型信息（v1 只登记元数据，不上传权重文件），
平台管理员审核通过后进入公共模型目录，所有租户可见。
"""

import json
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from db_models import ModelSubmissionDB

STATUSES = ("pending", "approved", "rejected")
_REQUIRED = ("model_id", "name", "task")


class SubmissionError(ValueError):
    """提交内容非法。"""


def submit(db: Session, tenant_id: int, payload: dict) -> ModelSubmissionDB:
    missing = [key for key in _REQUIRED if not (payload.get(key) or "").strip()]
    if missing:
        raise SubmissionError("缺少必填字段: {}".format(", ".join(missing)))

    model_id = payload["model_id"].strip()
    duplicate = (
        db.query(ModelSubmissionDB)
        .filter(
            ModelSubmissionDB.tenant_id == tenant_id,
            ModelSubmissionDB.model_id == model_id,
            ModelSubmissionDB.status.in_(("pending", "approved")),
        )
        .first()
    )
    if duplicate is not None:
        raise SubmissionError("该模型已提交或已通过审核: {}".format(model_id))

    row = ModelSubmissionDB(
        tenant_id=tenant_id,
        model_id=model_id,
        name=payload["name"].strip(),
        task=payload["task"].strip(),
        version=(payload.get("version") or "").strip(),
        source=(payload.get("source") or "community").strip(),
        license=(payload.get("license") or "未声明").strip(),
        size_mb=float(payload.get("size_mb") or 0.0),
        note=(payload.get("note") or "").strip()[:200],
        status="pending",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_submissions(
    db: Session, tenant_id: Optional[int] = None
) -> List[ModelSubmissionDB]:
    query = db.query(ModelSubmissionDB)
    if tenant_id is not None:
        query = query.filter(ModelSubmissionDB.tenant_id == tenant_id)
    return query.order_by(ModelSubmissionDB.id.desc()).all()


def get(db: Session, submission_id: int) -> Optional[ModelSubmissionDB]:
    return (
        db.query(ModelSubmissionDB)
        .filter(ModelSubmissionDB.id == submission_id)
        .first()
    )


def review(
    db: Session, submission_id: int, approve: bool, note: str = ""
) -> Optional[ModelSubmissionDB]:
    row = get(db, submission_id)
    if row is None:
        return None
    row.status = "approved" if approve else "rejected"
    row.review_note = (note or "")[:200]
    row.reviewed_at = datetime.now()
    db.commit()
    db.refresh(row)
    return row


def approved_models(db: Session) -> List[dict]:
    """已通过审核、进入公共目录的模型。"""
    rows = (
        db.query(ModelSubmissionDB)
        .filter(ModelSubmissionDB.status == "approved")
        .all()
    )
    return [
        {
            "model_id": row.model_id,
            "name": row.name,
            "task": row.task,
            "source": row.source,
            "license": row.license,
            "size_mb": row.size_mb,
            "bundled": False,
            "note": row.note or "社区提交",
        }
        for row in rows
    ]


def serialize(row: ModelSubmissionDB) -> dict:
    return {
        "id": row.id,
        "model_id": row.model_id,
        "name": row.name,
        "task": row.task,
        "version": row.version,
        "source": row.source,
        "license": row.license,
        "size_mb": row.size_mb,
        "note": row.note,
        "status": row.status,
        "review_note": row.review_note,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
    }
