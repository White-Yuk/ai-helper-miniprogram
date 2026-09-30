"""数据库连接检查脚本：读取 .env 的 DATABASE_URL 并尝试连接。

用法（在 backend 目录下执行）：
    .venv/Scripts/python.exe scripts/check_db.py

输出：连接成功（含 MySQL 版本）或失败原因（自动脱敏，不输出密码）。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 允许从 backend 目录直接导入 app 包
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import get_settings  # noqa: E402


def mask_url(url: str) -> tuple[str, str]:
    """返回（脱敏后的 URL, 明文密码）；无法解析密码时返回空串。"""
    if "://" not in url or "@" not in url:
        return url, ""
    scheme, rest = url.split("://", 1)
    creds, host = rest.split("@", 1)
    if ":" not in creds:
        return url, ""
    user, password = creds.split(":", 1)
    return f"{scheme}://{user}:***@{host}", password


def main() -> int:
    settings = get_settings()
    safe_url, password = mask_url(settings.db_url)
    print(f"目标数据库：{safe_url}")

    try:
        engine = create_engine(settings.db_url, pool_pre_ping=True)
        with engine.connect() as conn:
            version = conn.execute(text("SELECT VERSION()")).scalar()
        print(f"[OK] 连接成功！MySQL 版本：{version}")
        return 0
    except Exception as exc:  # noqa: BLE001 - 检查脚本需要打印全部失败原因
        message = str(exc)
        if password:
            message = message.replace(password, "***")
        print(f"[FAIL] 连接失败：{type(exc).__name__}: {message}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
