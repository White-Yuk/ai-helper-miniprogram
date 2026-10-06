"""文档资料库接口：上传（multipart） / 列表 / 删除。

- 全部接口要求登录（文档归属用户，严格隔离）；
- 上传 = 受理 + 后台处理（客户端轮询列表获取状态与步骤）；
- 格式 / 大小 / 启用状态校验在服务层（错误码 4000 / 422）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.response import success
from app.models.document import Document
from app.models.user import User
from app.services import doc_service

router = APIRouter()


def _document_to_dict(document: Document) -> dict:
    """文档记录 → 响应数据（前端列表 / 轮询用）。"""
    return {
        "doc_id": document.doc_id,
        "filename": document.filename,
        "file_type": document.file_type,
        "file_size": document.file_size,
        "status": document.status,
        "steps": document.steps or [],
        "error_message": document.error_message,
        "chunk_count": document.chunk_count,
        "char_count": document.char_count,
        "created_at": document.created_at.isoformat(timespec="seconds") if document.created_at else None,
        "finished_at": document.finished_at.isoformat(timespec="seconds") if document.finished_at else None,
    }


@router.post("/documents", summary="上传文档（受理后进入后台处理）")
async def upload_document_route(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict:
    content = await file.read()
    document = doc_service.save_upload(session, user.id, file.filename or "未命名文件", content)
    doc_service.submit_document(document.doc_id)
    return success({"doc_id": document.doc_id, "status": document.status})


@router.get("/documents", summary="我的文档列表（含处理状态与步骤，供轮询）")
def list_documents_route(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict:
    documents = doc_service.list_documents(session, user.id)
    return success({"documents": [_document_to_dict(item) for item in documents]})


@router.delete("/documents/{doc_id}", summary="删除文档（记录 + 向量 + 原文件）")
def delete_document_route(
    doc_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict:
    return success(doc_service.delete_document(session, user.id, doc_id))
