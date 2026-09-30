"""生成复盘报告接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.response import success
from app.llm.report_chain import build_report_chain
from app.models.report import ReportGenerateRequest
from app.services.report_service import generate_report

router = APIRouter()


def get_report_chain():
    """依赖注入：报告链（测试中可通过 dependency_overrides 替换为 Mock）。"""
    return build_report_chain()


@router.post("/report/generate", summary="生成复盘报告")
def generate_report_route(payload: ReportGenerateRequest, chain=Depends(get_report_chain)) -> dict:
    data = generate_report(payload, chain)
    return success(data)
