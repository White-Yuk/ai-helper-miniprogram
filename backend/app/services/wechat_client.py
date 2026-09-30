"""微信小程序服务端接口封装：code2Session（code 换 openid）。

官方文档：https://developers.weixin.qq.com/miniprogram/dev/OpenApiDoc/user-login/code2Session.html
"""
from __future__ import annotations

import httpx

from app.core.config import get_settings

CODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"


class WechatCode2SessionError(Exception):
    """code2Session 调用失败（配置缺失 / 微信返回错误 / 网络异常）。"""


def code2session(code: str) -> str:
    """用登录 code 换取 openid。失败抛 WechatCode2SessionError。"""
    settings = get_settings()
    if not settings.wechat_appid or not settings.wechat_secret:
        raise WechatCode2SessionError("尚未配置微信小程序 AppID/AppSecret")

    try:
        resp = httpx.get(
            CODE2SESSION_URL,
            params={
                "appid": settings.wechat_appid,
                "secret": settings.wechat_secret,
                "js_code": code,
                "grant_type": "authorization_code",
            },
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        raise WechatCode2SessionError(f"微信接口网络异常：{type(exc).__name__}") from exc

    try:
        data = resp.json()
    except ValueError as exc:
        raise WechatCode2SessionError("微信接口返回格式异常") from exc

    if data.get("errcode"):
        errcode = data.get("errcode")
        errmsg = data.get("errmsg", "未知错误")
        raise WechatCode2SessionError(f"微信登录失败：{errmsg}（errcode={errcode}）")

    openid = data.get("openid")
    if not openid:
        raise WechatCode2SessionError("微信登录失败：未返回 openid")
    return openid
