"""生成复盘报告接口（登录后报告自动落库）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_optional_current_user
from app.core.db import get_db
from app.core.response import success
from app.llm.report_chain import build_report_chain
from app.models.report import ReportGenerateRequest
from app.models.user import User
from app.services import record_service
from app.services.report_service import generate_report

router = APIRouter()


def get_report_chain():
    """依赖注入：报告链（测试中可通过 dependency_overrides 替换为 Mock）。"""
    return build_report_chain()


@router.post("/report/generate", summary="生成复盘报告（可选登录：登录后落库）")
def generate_report_route(
    payload: ReportGenerateRequest,
    chain=Depends(get_report_chain),
    user: User | None = Depends(get_optional_current_user),
    session: Session = Depends(get_db),
) -> dict:
    data = generate_report(payload, chain)
    if user is not None:
        record_service.save_report(session, user.id, payload.quiz_id, data)
    return success(data)
