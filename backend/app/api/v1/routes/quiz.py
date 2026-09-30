"""生成题库接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.response import success
from app.llm.quiz_chain import build_quiz_chain
from app.models.quiz import QuizGenerateRequest
from app.services.quiz_service import generate_quiz

router = APIRouter()


def get_quiz_chain():
    """依赖注入：出题链（测试中可通过 dependency_overrides 替换为 Mock）。"""
    return build_quiz_chain()


@router.post("/quiz/generate", summary="生成闯关题库")
def generate_quiz_route(payload: QuizGenerateRequest, chain=Depends(get_quiz_chain)) -> dict:
    data = generate_quiz(payload, chain)
    return success(data)
