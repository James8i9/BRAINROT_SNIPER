"""
web/app.py
==========
ShadowSnipe Telegram Mini App HTTP server (same process as the bot).

Routes:
  GET  /              → Mini App shell
  GET  /health        → Railway health
  GET  /api/me        → auth + access (header X-Telegram-Init-Data)
  GET  /api/portfolio → stub for Phase 1
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from aiohttp import web

from web.auth import resolve_webapp_user

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _cors_headers() -> dict:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type, X-Telegram-Init-Data",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    }


async def handle_options(request: web.Request) -> web.Response:
    return web.Response(status=204, headers=_cors_headers())


async def health(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "shadowsnipe-miniapp"}, headers=_cors_headers())


async def index(request: web.Request) -> web.Response:
    index_path = STATIC_DIR / "index.html"
    if not index_path.is_file():
        return web.Response(text="Mini App UI missing", status=500)
    return web.FileResponse(index_path, headers={
        "Cache-Control": "no-cache",
        **_cors_headers(),
    })


def _init_data_from_request(request: web.Request) -> str:
    return (
        request.headers.get("X-Telegram-Init-Data")
        or request.rel_url.query.get("initData")
        or ""
    )


async def api_me(request: web.Request) -> web.Response:
    init_data = _init_data_from_request(request)
    user = await resolve_webapp_user(init_data)
    if not user:
        return web.json_response(
            {"ok": False, "error": "unauthorized"},
            status=401,
            headers=_cors_headers(),
        )

    return web.json_response(
        {
            "ok": True,
            "user": {
                "id": user.user_id,
                "username": user.username,
                "first_name": user.first_name,
                "activated": user.activated,
                "referral": user.referral,
                "is_admin": user.is_admin,
                "can_access": user.can_access,
            },
        },
        headers=_cors_headers(),
    )


async def api_portfolio(request: web.Request) -> web.Response:
    """Phase 1 will fill real balances; Phase 3 returns a gated stub."""
    init_data = _init_data_from_request(request)
    user = await resolve_webapp_user(init_data)
    if not user:
        return web.json_response({"ok": False, "error": "unauthorized"}, status=401, headers=_cors_headers())
    if not user.can_access:
        return web.json_response(
            {"ok": False, "error": "license_required", "can_access": False},
            status=403,
            headers=_cors_headers(),
        )

    return web.json_response(
        {
            "ok": True,
            "can_access": True,
            "phase": 3,
            "message": "Portfolio API ready — Phase 1 will stream live balances",
            "total_sol": None,
            "wallets": [],
        },
        headers=_cors_headers(),
    )


def create_web_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_get("/", index)
    app.router.add_get("/app", index)
    app.router.add_get("/api/me", api_me)
    app.router.add_get("/api/portfolio", api_portfolio)
    app.router.add_route("OPTIONS", "/api/me", handle_options)
    app.router.add_route("OPTIONS", "/api/portfolio", handle_options)

    if STATIC_DIR.is_dir():
        app.router.add_static("/static/", STATIC_DIR, name="static")

    logger.info("Mini App static dir: %s", STATIC_DIR)
    return app


async def start_web_server() -> web.AppRunner:
    """Bind 0.0.0.0:$PORT for Railway. Returns runner (keep reference)."""
    port = int(os.getenv("PORT", "8080"))
    app = create_web_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Mini App HTTP listening on 0.0.0.0:%s", port)
    return runner
