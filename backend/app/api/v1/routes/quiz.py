"""题库与答题记录接口：生成 / 进度保存 / 提交 / 未完成查询。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_optional_current_user
from app.core.db import get_db
from app.core.response import success
from app.llm.quiz_chain import build_quiz_chain
from app.models.progress import QuizProgressRequest, QuizSubmitRequest
from app.models.quiz import QuizGenerateRequest
from app.models.user import User
from app.services import record_service
from app.services.quiz_service import generate_quiz

router = APIRouter()


def get_quiz_chain():
    """依赖注入：出题链（测试中可通过 dependency_overrides 替换为 Mock）。"""
    return build_quiz_chain()


@router.post("/quiz/generate", summary="生成闯关题库（可选登录：登录后自动保存并可续答）")
def generate_quiz_route(
    payload: QuizGenerateRequest,
    chain=Depends(get_quiz_chain),
    user: User | None = Depends(get_optional_current_user),
    session: Session = Depends(get_db),
) -> dict:
    data = generate_quiz(payload, chain)
    if user is not None:
        record_service.save_generated_quiz(session, user.id, data)
    return success(data)


@router.get("/quiz/unfinished", summary="最近未完成闯关（含完整题库与已答记录，供续答恢复）")
def unfinished_quiz_route(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict:
    data = record_service.get_unfinished_quiz(session, user.id)
    return success(data)


@router.put("/quiz/{quiz_id}/progress", summary="保存中途进度（幂等：全量覆盖）")
def save_progress_route(
    quiz_id: str,
    payload: QuizProgressRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict:
    data = record_service.save_progress(session, user.id, quiz_id, payload.current_index, payload.records)
    return success(data)


@router.post("/quiz/{quiz_id}/submit", summary="提交完整作答（quiz 置完成）")
def submit_quiz_route(
    quiz_id: str,
    payload: QuizSubmitRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict:
    data = record_service.submit_quiz(session, user.id, quiz_id, payload.records)
    return success(data)
