"""文档服务：上传落盘 / 异步处理流水线 / 查询 / 删除 / 启动兜底。

对齐 design.md D1-D3：
- 上传即受理（pending）→ 独立线程池处理【解析 → 分块 → 向量化 → 入库】→ ready / failed；
- 步骤流（steps JSON）与生成任务同格式，前端可复用展示逻辑；
- 删除清理（记录 + 向量 + 原文件）；处理中删除由「写前复查 + 写后补偿清理」防竞态残留；
- `mark_stale_documents_failed`：服务启动兜底残留 pending / processing
  （对齐 `mark_stale_tasks_failed`）。
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.core.exceptions import BizException
from app.models.document import Document
from app.utils.doc_parser import DocParseError, normalize_file_type, parse_document
from app.utils.id_generator import new_doc_id
from app.utils.text_splitter import build_text_splitter

logger = logging.getLogger(__name__)

_executor: ThreadPoolExecutor | None = None


def _get_executor() -> ThreadPoolExecutor:
    """文档处理线程池（独立于生成任务线程池；默认并发 1，测试可 patch）。"""
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=get_settings().doc_worker_concurrency,
            thread_name_prefix="doc-worker",
        )
    return _executor


def is_kb_enabled() -> bool:
    """资料库是否启用（百炼凭据已配置）。"""
    return bool(get_settings().dashscope_api_key)


def upload_root() -> Path:
    """上传文件存储根目录（配置为空 = backend/data/uploads）。"""
    settings = get_settings()
    if settings.upload_dir:
        return Path(settings.upload_dir)
    backend_dir = Path(__file__).resolve().parents[2]
    return backend_dir / "data" / "uploads"


def get_vector_store():
    """向量库实例（测试可 patch 本函数注入 Fake 嵌入 / 临时目录）。"""
    from app.services.vector_store import VectorStore

    return VectorStore()


def document_file_path(document: Document) -> Path:
    """文档原文件路径（存储名用 doc_id，不信任原始文件名）。"""
    return upload_root() / str(document.user_id) / f"{document.doc_id}.{document.file_type}"


# ---- 上传 ----


def validate_upload(filename: str, content: bytes) -> str:
    """上传校验（启用状态 / 类型 / 空文件 / 大小）；返回文件类型，失败抛 BizException(4000)。"""
    settings = get_settings()
    if not is_kb_enabled():
        raise BizException(code=4000, message="资料库功能未启用（未配置 DASHSCOPE_API_KEY）", http_status=422)
    file_type = normalize_file_type(filename)
    if not file_type:
        raise BizException(code=4000, message="仅支持 PDF / Word(.docx) / Markdown(.md) 文件", http_status=422)
    if not content:
        raise BizException(code=4000, message="文件内容为空", http_status=422)
    max_bytes = settings.upload_max_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise BizException(code=4000, message=f"文件不能超过 {settings.upload_max_size_mb}MB", http_status=422)
    return file_type


def save_upload(session: Session, user_id: int, filename: str, content: bytes) -> Document:
    """保存上传：校验 → 落盘 → 创建记录（pending）。调用方随后 submit_document。"""
    file_type = validate_upload(filename, content)
    doc_id = new_doc_id()
    directory = upload_root() / str(user_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{doc_id}.{file_type}"
    try:
        path.write_bytes(content)
    except OSError as exc:
        raise BizException(code=4000, message="文件保存失败，请重试", http_status=500) from exc

    document = Document(
        doc_id=doc_id,
        user_id=user_id,
        filename=filename[:255],
        file_type=file_type,
        file_size=len(content),
        status="pending",
        steps=[],
    )
    session.add(document)
    session.commit()
    session.refresh(document)
    logger.info("创建文档记录：%s（user_id=%s, %s, %s bytes）", doc_id, user_id, file_type, len(content))
    return document


def submit_document(doc_id: str) -> None:
    """提交文档处理到线程池（接口测试 patch 本函数防止真实执行）。"""
    try:
        _get_executor().submit(_process_document, doc_id)
    except Exception:  # noqa: BLE001 - 提交失败不向外抛（记录已持久化，客户端可见 pending 状态）
        logger.exception("文档处理提交失败：%s", doc_id)


# ---- 处理流水线 ----


def _update_step(document: Document, key: str, label: str, detail: str, state: str) -> None:
    """更新步骤（upsert 语义；调用方负责 commit）。"""
    steps = [dict(step) for step in (document.steps or [])]
    now = datetime.now().isoformat(timespec="seconds")
    for step in steps:
        if step.get("key") == key:
            step.update({"label": label, "detail": detail, "state": state, "ts": now})
            break
    else:
        steps.append({"key": key, "label": label, "detail": detail, "state": state, "ts": now})
    document.steps = steps


def _fresh_document(session: Session, doc_id: str) -> Document | None:
    """强制刷新后查询记录（每步 commit 后调用；不存在视为已被删除）。"""
    session.expire_all()
    return session.scalars(select(Document).where(Document.doc_id == doc_id)).one_or_none()


def _finish_failed(session: Session, document: Document, message: str) -> None:
    document.status = "failed"
    document.error_message = message[:500]
    document.finished_at = datetime.now()
    _update_step(document, "finish", "失败", message[:200], "done")
    session.commit()


def _process_document(doc_id: str) -> None:
    """处理主流程：pending → processing → ready / failed（未知异常兜底 failed）。"""
    session = get_session_factory()()
    try:
        document = _fresh_document(session, doc_id)
        if document is None:
            logger.info("文档不存在（可能已删除），跳过处理：%s", doc_id)
            return

        # 提前取出处理上下文（后续 expire_all 后不再依赖 ORM 实例属性——行可能已被删除）
        owner_id = document.user_id
        stored_doc_id = document.doc_id
        doc_filename = document.filename

        document.status = "processing"
        _update_step(document, "parse", "解析文档", "正在解析文本", "doing")
        session.commit()

        try:
            text = parse_document(document_file_path(document), document.file_type)
        except DocParseError as exc:
            _finish_failed(session, document, str(exc))
            return

        _update_step(document, "parse", "解析文档", f"已提取 {len(text)} 字", "done")
        _update_step(document, "split", "文本分块", "正在分块", "doing")
        session.commit()

        chunks = build_text_splitter().split_text(text)
        if not chunks:
            _finish_failed(session, document, "未提取到有效文本（暂不支持扫描版 PDF）")
            return
        _update_step(document, "split", "文本分块", f"共 {len(chunks)} 块", "done")
        _update_step(document, "embed", "向量化入库", f"正在处理 {len(chunks)} 块", "doing")
        session.commit()

        # 写前复查（防处理中删除）
        if _fresh_document(session, doc_id) is None:
            logger.info("文档在处理中被删除，丢弃结果：%s", doc_id)
            return

        store = get_vector_store()
        try:
            store.add_chunks(owner_id, stored_doc_id, doc_filename, chunks)
        except Exception as exc:  # noqa: BLE001 - 向量化 / 入库失败
            logger.warning("文档向量化失败：%s（%s）", doc_id, type(exc).__name__)
            fresh = _fresh_document(session, doc_id)
            if fresh is not None:
                _finish_failed(session, fresh, f"向量化失败（{type(exc).__name__}），请稍后重试")
            return

        # 写后复查（写入期间被删除 → 补偿清理刚写入的向量）
        fresh = _fresh_document(session, doc_id)
        if fresh is None:
            logger.info("文档在处理中被删除，补偿清理已写入向量：%s", doc_id)
            try:
                store.delete_by_doc(owner_id, stored_doc_id)
            except Exception:  # noqa: BLE001 - 补偿清理失败仅告警
                logger.warning("补偿清理向量失败：%s", doc_id, exc_info=True)
            return

        fresh.status = "ready"
        fresh.chunk_count = len(chunks)
        fresh.char_count = len(text)
        fresh.finished_at = datetime.now()
        _update_step(fresh, "embed", "向量化入库", f"已入库 {len(chunks)} 块", "done")
        _update_step(fresh, "finish", "完成", "文档已就绪，可用于出题检索", "done")
        session.commit()
        logger.info("文档处理完成：%s（%s 块）", doc_id, len(chunks))
    except Exception:  # noqa: BLE001 - 未知异常兜底 failed
        logger.exception("文档处理异常：%s", doc_id)
        try:
            session.rollback()
            document = _fresh_document(session, doc_id)
            if document is not None:
                _finish_failed(session, document, "处理中断，请重新上传")
        except Exception:  # noqa: BLE001 - 失败状态写入失败仅告警
            logger.exception("文档失败状态写入异常：%s", doc_id)
    finally:
        session.close()


# ---- 查询与删除 ----


def has_ready_documents(user_id: int) -> bool:
    """用户是否有处理就绪的文档（出题链路「资料库工具注入」的轻查询）。"""
    session = get_session_factory()()
    try:
        row = session.scalars(
            select(Document.id)
            .where(Document.user_id == user_id, Document.status == "ready")
            .limit(1)
        ).first()
        return row is not None
    finally:
        session.close()


def list_documents(session: Session, user_id: int) -> list[Document]:
    """用户文档列表（新 → 旧）。"""
    return list(
        session.scalars(
            select(Document)
            .where(Document.user_id == user_id)
            .order_by(Document.created_at.desc(), Document.id.desc())
        ).all()
    )


def get_user_document(session: Session, user_id: int, doc_id: str) -> Document:
    """归属校验查询：不存在 / 他人 → 4005（HTTP 404）。"""
    document = session.scalars(select(Document).where(Document.doc_id == doc_id)).one_or_none()
    if document is None or document.user_id != user_id:
        raise BizException(code=4005, message="文档不存在或已删除", http_status=404)
    return document


def delete_document(session: Session, user_id: int, doc_id: str) -> dict:
    """删除文档：记录 → 向量（失败重试 1 次）→ 原文件。

    处理中删除的竞态由处理线程的复查机制兜底（见 `_process_document`）。
    """
    document = get_user_document(session, user_id, doc_id)
    file_path = document_file_path(document)
    session.delete(document)
    session.commit()

    store = get_vector_store()
    for attempt in (1, 2):  # 轻试重试 1 次（本地删除极少失败，尽力保证检索侧干净）
        try:
            store.delete_by_doc(user_id, doc_id)
            break
        except Exception:  # noqa: BLE001
            log = logger.warning if attempt == 1 else logger.error
            log("删除文档向量失败（第 %s 次）：%s", attempt, doc_id, exc_info=attempt == 2)

    try:
        file_path.unlink(missing_ok=True)
    except OSError:
        logger.warning("删除文档文件失败：%s", file_path, exc_info=True)

    logger.info("删除文档：%s（user_id=%s）", doc_id, user_id)
    return {"doc_id": doc_id, "deleted": True}


# ---- 启动兜底 ----


def mark_stale_documents_failed() -> int:
    """服务启动兜底：残留 pending / processing → failed（避免客户端看到永远处理中）。

    返回处理条数；任何异常只记日志（不影响服务启动）。
    """
    session = get_session_factory()()
    try:
        documents = session.scalars(
            select(Document).where(Document.status.in_(["pending", "processing"]))
        ).all()
        if not documents:
            return 0
        now = datetime.now()
        for document in documents:
            document.status = "failed"
            document.error_message = "处理中断，请重新上传"
            document.finished_at = now
        session.commit()
        logger.warning("启动清理：%s 个残留文档标记为失败", len(documents))
        return len(documents)
    except Exception:  # noqa: BLE001 - 清理失败不影响服务启动
        logger.warning("启动清理文档失败（不影响服务启动）", exc_info=True)
        session.rollback()
        return 0
    finally:
        session.close()
