"""知识掌握详情接口（阶段 5）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.response import success
from app.models.user import User
from app.services import stats_service

router = APIRouter()


@router.get("/knowledge-base/{quiz_id}", summary="知识掌握详情（知识点清单：掌握 / 薄弱 / 未学）")
def knowledge_detail_route(
    quiz_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict:
    data = stats_service.get_knowledge_detail(session, user.id, quiz_id)
    return success(data)
