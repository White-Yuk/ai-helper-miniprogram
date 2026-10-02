"""错题本接口（阶段 6）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.response import success
from app.models.user import User
from app.models.wrongbook import RedoSubmitRequest
from app.services import record_service

router = APIRouter()


@router.get("/wrongbook", summary="错题本（待清理错题列表）")
def wrongbook_route(user: User = Depends(get_current_user), session: Session = Depends(get_db)) -> dict:
    return success(record_service.get_wrongbook(session, user.id))


@router.post("/wrongbook/redo", summary="提交错题重做结果（答对即清理）")
def redo_route(
    payload: RedoSubmitRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict:
    return success(record_service.submit_redo(session, user.id, payload))
