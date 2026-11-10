"""
web/app.py
==========
ShadowSnipe Telegram Mini App HTTP server (same process as the bot).

Routes:
  GET  /  /app /health
  GET  /api/me
  GET  /api/portfolio
  POST /api/wallets/import-fund
  POST /api/wallets/generate-buy
  POST /api/wallets/distribute
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from aiohttp import web

from web.auth import resolve_webapp_user, WebAppUser
from services.multi_wallet_service import (
    import_fund_wallet,
    get_fund_wallet,
    get_buy_wallets,
    generate_buy_wallets,
    list_all_wallets,
    distribute_sol,
)
from services.bot_wallet_service import get_sol_balance
from services.pnl_card_service import fetch_sol_price_usd

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _cors_headers() -> dict:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type, X-Telegram-Init-Data",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    }


def _json(data: dict, status: int = 200) -> web.Response:
    return web.json_response(data, status=status, headers=_cors_headers())


async def handle_options(request: web.Request) -> web.Response:
    return web.Response(status=204, headers=_cors_headers())


async def health(request: web.Request) -> web.Response:
    return _json({"ok": True, "service": "shadowsnipe-miniapp", "phase": 1})


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


async def _require_user(request: web.Request, need_access: bool = True) -> tuple[Optional[WebAppUser], Optional[web.Response]]:
    user = await resolve_webapp_user(_init_data_from_request(request))
    if not user:
        return None, _json({"ok": False, "error": "unauthorized"}, 401)
    if need_access and not user.can_access:
        return None, _json({"ok": False, "error": "license_required", "can_access": False}, 403)
    return user, None


async def _portfolio_payload(user_id: int) -> dict:
    wallets_raw = await list_all_wallets(user_id)
    wallets = []
    total = 0.0
    fund_address = None

    for w in wallets_raw:
        addr = w["wallet_address"]
        bal = await get_sol_balance(addr)
        bal_f = float(bal) if bal is not None else None
        if bal_f is not None:
            total += bal_f
        if w["wallet_type"] == "fund":
            fund_address = addr
        wallets.append({
            "id": w.get("id"),
            "address": addr,
            "type": w["wallet_type"],
            "label": w.get("label") or w["wallet_type"],
            "balance_sol": bal_f,
        })

    sol_px = await fetch_sol_price_usd()
    return {
        "ok": True,
        "can_access": True,
        "phase": 1,
        "total_sol": total,
        "total_usd": total * sol_px if sol_px > 0 else None,
        "sol_price_usd": sol_px or None,
        "fund_address": fund_address,
        "buy_count": sum(1 for x in wallets if x["type"] == "buy"),
        "wallets": wallets,
    }


async def api_me(request: web.Request) -> web.Response:
    user, err = await _require_user(request, need_access=False)
    if err:
        return err
    assert user is not None
    return _json({
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
    })


async def api_portfolio(request: web.Request) -> web.Response:
    user, err = await _require_user(request, need_access=True)
    if err:
        return err
    assert user is not None
    try:
        payload = await _portfolio_payload(user.user_id)
        return _json(payload)
    except Exception as e:
        logger.exception("portfolio failed")
        return _json({"ok": False, "error": str(e)}, 500)


async def api_import_fund(request: web.Request) -> web.Response:
    user, err = await _require_user(request, need_access=True)
    if err:
        return err
    assert user is not None

    try:
        body = await request.json()
    except Exception:
        return _json({"ok": False, "error": "invalid_json"}, 400)

    private_key = (body.get("private_key") or "").strip()
    if not private_key:
        return _json({"ok": False, "error": "private_key required"}, 400)

    result = await import_fund_wallet(user.user_id, private_key)
    if not result.get("success"):
        return _json({"ok": False, "error": result.get("error") or "import_failed"}, 400)

    payload = await _portfolio_payload(user.user_id)
    payload["imported_address"] = result.get("address")
    return _json(payload)


async def api_generate_buy(request: web.Request) -> web.Response:
    user, err = await _require_user(request, need_access=True)
    if err:
        return err
    assert user is not None

    if not await get_fund_wallet(user.user_id):
        return _json({"ok": False, "error": "Import a Fund Wallet first."}, 400)

    try:
        body = await request.json()
    except Exception:
        body = {}

    try:
        count = int(body.get("count") or 2)
    except Exception:
        count = 2
    count = max(1, min(10, count))

    try:
        created = await generate_buy_wallets(user.user_id, count)
    except Exception as e:
        return _json({"ok": False, "error": str(e)}, 400)

    payload = await _portfolio_payload(user.user_id)
    payload["created"] = created
    return _json(payload)


async def api_distribute(request: web.Request) -> web.Response:
    user, err = await _require_user(request, need_access=True)
    if err:
        return err
    assert user is not None

    try:
        body = await request.json()
    except Exception:
        return _json({"ok": False, "error": "invalid_json"}, 400)

    try:
        amount = float(body.get("amount_each") or 0)
    except Exception:
        return _json({"ok": False, "error": "amount_each must be a number"}, 400)

    if amount <= 0:
        return _json({"ok": False, "error": "amount_each must be > 0"}, 400)

    result = await distribute_sol(user.user_id, amount)
    if not result.get("success"):
        return _json({"ok": False, "error": result.get("error") or "distribute_failed"}, 400)

    payload = await _portfolio_payload(user.user_id)
    payload["distribute"] = {
        "signature": result.get("signature"),
        "total_sent": result.get("total_sent"),
        "count": result.get("count"),
        "amount_each": result.get("amount_each"),
    }
    return _json(payload)


def create_web_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_get("/", index)
    app.router.add_get("/app", index)
    app.router.add_get("/api/me", api_me)
    app.router.add_get("/api/portfolio", api_portfolio)
    app.router.add_post("/api/wallets/import-fund", api_import_fund)
    app.router.add_post("/api/wallets/generate-buy", api_generate_buy)
    app.router.add_post("/api/wallets/distribute", api_distribute)

    for path in (
        "/api/me",
        "/api/portfolio",
        "/api/wallets/import-fund",
        "/api/wallets/generate-buy",
        "/api/wallets/distribute",
    ):
        app.router.add_route("OPTIONS", path, handle_options)

    if STATIC_DIR.is_dir():
        app.router.add_static("/static/", STATIC_DIR, name="static")

    logger.info("Mini App static dir: %s", STATIC_DIR)
    return app


async def start_web_server() -> web.AppRunner:
    port = int(os.getenv("PORT", "8080"))
    app = create_web_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Mini App HTTP listening on 0.0.0.0:%s", port)
    return runner
