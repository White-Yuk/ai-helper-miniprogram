"""健康检查接口测试。"""
from __future__ import annotations


def test_health_ok(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200

    body = resp.json()
    assert body["code"] == 0
    assert body["message"] == "ok"
    assert body["data"]["status"] == "healthy"
    assert "app_name" in body["data"]
    assert "version" in body["data"]


def test_cors_headers_for_options(client):
    """OPTIONS 预检请求应带 CORS 头（开发期允许跨域）。"""
    resp = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:10086",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") is not None
