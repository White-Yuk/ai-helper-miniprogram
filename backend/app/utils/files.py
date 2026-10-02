"""用户上传文件处理（头像等）。

- 头像仅允许 JPG / PNG / WebP，且不超过 2MB
- 文件名使用 uuid（不信任客户端文件名），保存到 static/avatars/
- 返回相对 URL（如 /static/avatars/xxx.png），由 FastAPI StaticFiles 提供访问
"""
from __future__ import annotations

import uuid
from pathlib import Path

from app.core.exceptions import BizException

MAX_AVATAR_BYTES = 2 * 1024 * 1024
ALLOWED_IMAGE_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

# backend/ 目录（本文件位于 backend/app/utils/）
BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_AVATAR_DIR = BACKEND_DIR / "static" / "avatars"


def default_avatar_dir() -> Path:
    """默认头像存储目录（测试中通过依赖注入替换）。"""
    return DEFAULT_AVATAR_DIR


def save_avatar(content: bytes, content_type: str, target_dir: Path | None = None) -> str:
    """校验并保存头像文件，返回可访问的相对 URL。"""
    normalized = (content_type or "").split(";")[0].strip().lower()
    ext = ALLOWED_IMAGE_TYPES.get(normalized)
    if ext is None:
        raise BizException(code=4000, message="仅支持 JPG / PNG / WebP 格式的图片", http_status=422)
    if not content:
        raise BizException(code=4000, message="文件内容为空", http_status=422)
    if len(content) > MAX_AVATAR_BYTES:
        raise BizException(code=4000, message="图片不能超过 2MB", http_status=422)

    directory = target_dir or default_avatar_dir()
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    (directory / filename).write_bytes(content)
    return f"/static/avatars/{filename}"
