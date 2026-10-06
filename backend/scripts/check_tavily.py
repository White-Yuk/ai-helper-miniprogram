"""Tavily 联网检索可用性检查脚本。

用法（在 backend 目录下执行）：
    .venv/Scripts/python.exe scripts/check_tavily.py

检查内容（依次执行）：
    [0] .env 中 TAVILY_API_KEY 是否已配置（不输出 Key 内容）
    [1] 轻快搜索（摘要，无完整内容）
    [2] 深度搜索（含完整页面内容）
    [3] 网页提取（TavilyExtract）

说明：真实调用外部 API，不属于 tests/ 单元测试套件（项目约定：单测不触网）。
输出自动脱敏：任何异常信息中的 Key 都会被打码。
"""
from __future__ import annotations

import os
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = BACKEND_DIR / ".env"


def load_api_key() -> str:
    """从 backend/.env 读取 TAVILY_API_KEY（不打印内容）。"""
    if not ENV_PATH.exists():
        print(f"[FAIL] 未找到 {ENV_PATH}，请先从 .env.example 复制并填写配置")
        return ""
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH, override=False)
    return os.getenv("TAVILY_API_KEY", "").strip()


def _safe_message(exc: Exception, api_key: str) -> str:
    """异常信息脱敏（防止意外携带 Key），并限制长度。"""
    message = f"{type(exc).__name__}: {exc}"
    if api_key:
        message = message.replace(api_key, "***")
    return message[:200]


def main() -> int:
    print("=" * 46)
    print("Tavily 可用性检查")
    print("=" * 46)

    api_key = load_api_key()
    if not api_key:
        print("[FAIL] .env 中未配置 TAVILY_API_KEY（或为空）")
        print("       获取地址：https://app.tavily.com -> API Keys")
        return 1

    prefix_hint = "是" if api_key.startswith("tvly-") else "否（请确认是否复制完整）"
    print(f"[0] Key 已配置（以 tvly- 开头：{prefix_hint}）")

    from langchain_tavily import TavilyExtract, TavilySearch

    ok = True

    # 1) 轻快搜索（basic 档语义：摘要、不取全文）
    try:
        tool = TavilySearch(max_results=5, include_raw_content=False, tavily_api_key=api_key)
        t0 = time.monotonic()
        result = tool.invoke({"query": "Harness Engineering"})
        elapsed = time.monotonic() - t0
        results = result.get("results", []) if isinstance(result, dict) else []
        print(f"[1] 轻快搜索 OK：{elapsed:.1f}s，返回 {len(results)} 条")
        for item in results[:3]:
            title = str(item.get("title", ""))[:50]
            url = str(item.get("url", ""))[:70]
            print(f"    - {title} | {url}")
        if not results:
            ok = False
            print("    [WARN] 结果为空，请人工确认")
    except Exception as exc:  # noqa: BLE001 - 检查脚本需要打印全部失败原因
        ok = False
        print(f"[1] 轻快搜索 FAIL：{_safe_message(exc, api_key)}")

    # 2) 深度搜索（deep 档语义：含完整页面内容）
    try:
        tool = TavilySearch(max_results=3, include_raw_content=True, tavily_api_key=api_key)
        t0 = time.monotonic()
        result = tool.invoke({"query": "Harness Engineering"})
        elapsed = time.monotonic() - t0
        results = result.get("results", []) if isinstance(result, dict) else []
        raw_count = sum(1 for item in results if item.get("raw_content"))
        print(f"[2] 深度搜索 OK：{elapsed:.1f}s，返回 {len(results)} 条，其中含完整内容 {raw_count} 条")
        if not raw_count:
            ok = False
            print("    [WARN] 未返回 raw_content，请人工确认")
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"[2] 深度搜索 FAIL：{_safe_message(exc, api_key)}")

    # 3) 网页提取
    try:
        tool = TavilyExtract(tavily_api_key=api_key)
        t0 = time.monotonic()
        result = tool.invoke({"urls": ["https://example.com"]})
        elapsed = time.monotonic() - t0
        results = result.get("results", []) if isinstance(result, dict) else []
        content_len = len(str(results[0].get("raw_content", ""))) if results else 0
        print(f"[3] 网页提取 OK：{elapsed:.1f}s，成功 {len(results)} 个 URL（内容 {content_len} 字符）")
        if not results:
            ok = False
            print("    [WARN] 提取结果为空，请人工确认")
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"[3] 网页提取 FAIL：{_safe_message(exc, api_key)}")

    print("-" * 46)
    if ok:
        print("[PASS] Tavily 可用（Key 有效、网络可达、三项功能正常）")
        return 0
    print("[FAIL] 存在失败项，请根据上方输出排查（网络 / Key / 额度）")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
