"""
bot/handlers/admin_user.py
===========================
Real admin tools for ShadowSnipe.

Requires your Telegram ID in ADMIN_IDS (Railway Variables).

Commands:
  /myid                         — anyone: show Telegram user ID
  /admin                        — admin panel help
  /genkey [user_id]             — create license key (optional lock to user)
  /activate <user_id>           — force-activate without payment
  /deactivate <user_id>         — revoke access
  /adminuser <user_id>          — user + wallet + activation summary
  /walletuser <user_id>         — live SOL balances + Refresh / Export buttons
  /allwallets [page]            — live view of ALL users' wallets + Refresh
  /exportkey <user_id>          — export all private keys for a user
  /exportkey <user_id> fund     — fund wallet key only
  /stats                        — activation / key counts
  /listkeys                     — recent unused license keys
  /activations                  — recent activations
"""

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from database.sqlite_db import get_db
from utils.admin import is_admin
from services.license_service import (
    create_license_key,
    admin_force_activate,
    admin_deactivate,
    get_activation_stats,
    list_recent_activations,
    list_unused_keys,
    is_user_activated,
)
from services.multi_wallet_service import get_keypair_from_wallet
from services.bot_wallet_service import get_sol_balance

logger = logging.getLogger(__name__)
router = Router()

_ALL_WALLETS_PAGE_SIZE = 8


def _deny_msg(message: Message) -> bool:
    return not is_admin(message.from_user.id)


def _deny_cb(callback: CallbackQuery) -> bool:
    return not is_admin(callback.from_user.id)


def _short(addr: str) -> str:
    if not addr:
        return "—"
    return f"{addr[:6]}…{addr[-4:]}" if len(addr) > 12 else addr


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S UTC")


def _keypair_to_base58(kp) -> str:
    raw = bytes(kp)
    try:
        import base58
        return base58.b58encode(raw).decode()
    except Exception:
        try:
            return kp.to_base58_string()  # type: ignore[attr-defined]
        except Exception:
            return raw.hex()


def _kb_walletuser(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄  Refresh Balances", callback_data=f"adm:wu:refresh:{uid}")],
        [InlineKeyboardButton(text="🔓  Export Private Key", callback_data=f"adm:wu:export:{uid}")],
        [InlineKeyboardButton(text="📋  All Wallets", callback_data="adm:aw:page:1")],
    ])


def _kb_allwallets(page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🔄  Refresh Balances", callback_data=f"adm:aw:refresh:{page}")],
    ]
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="◀️ Prev", callback_data=f"adm:aw:page:{page - 1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="Next ▶️", callback_data=f"adm:aw:page:{page + 1}"))
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _fetch_wallets_with_balances(user_id: int) -> tuple[list[dict], float]:
    async with get_db() as db:
        async with db.execute(
            """
            SELECT id, wallet_address, wallet_type, label, is_active, encrypted_private_key
            FROM multi_wallets
            WHERE user_id = ? AND is_active = 1
            ORDER BY CASE wallet_type WHEN 'fund' THEN 0 ELSE 1 END, id ASC
            """,
            (user_id,),
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]

    total = 0.0
    out = []
    for w in rows:
        bal = await get_sol_balance(w["wallet_address"])
        bal_f = float(bal) if bal is not None else None
        if bal_f is not None:
            total += bal_f
        item = dict(w)
        item["balance"] = bal_f
        out.append(item)
    return out, total


async def _build_walletuser_text(uid: int) -> tuple[str, bool]:
    """Returns (html_text, has_wallets)."""
    activated = await is_user_activated(uid)
    wallets, total = await _fetch_wallets_with_balances(uid)

    if not wallets:
        text = (
            f"🔑 <b>Live Wallet Balances</b>\n\n"
            f"User: <code>{uid}</code>\n"
            f"License: {'✅ active' if activated else '🔒 not active'}\n\n"
            f"No multi-wallets imported/generated yet.\n\n"
            f"<i>Updated {_now_stamp()}</i>"
        )
        return text, False

    lines = [
        "🔑 <b>Live Wallet Balances</b>",
        f"User: <code>{uid}</code>",
        f"License: {'✅ active' if activated else '🔒 not active'}",
        "",
    ]
    for w in wallets:
        kind = "Fund Wallet" if w["wallet_type"] == "fund" else (w.get("label") or "Buy Wallet")
        bal = w["balance"]
        bal_str = f"{bal:.4f} SOL" if bal is not None else "?.???? SOL"
        lines.append(f"💰 <b>{kind}</b>")
        lines.append(f"<code>{w['wallet_address']}</code>")
        lines.append(f"Balance: <b>{bal_str}</b>")
        lines.append("")

    lines.append(f"💎 <b>Total visible SOL:</b> {total:.4f} SOL")
    lines.append(f"\n<i>Updated {_now_stamp()}</i>")
    return "\n".join(lines), True


async def _build_allwallets_page(page: int) -> tuple[str, int, int]:
    """Returns (html_text, page, total_pages)."""
    async with get_db() as db:
        async with db.execute(
            """
            SELECT user_id, wallet_address, wallet_type, label
            FROM multi_wallets
            WHERE is_active = 1
            ORDER BY user_id ASC,
                     CASE wallet_type WHEN 'fund' THEN 0 ELSE 1 END,
                     id ASC
            """
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]

        async with db.execute("SELECT user_id, is_active FROM user_activations") as cur:
            act_map = {int(r["user_id"]): bool(r["is_active"]) for r in await cur.fetchall()}

    if not rows:
        return "No multi-wallets in the database yet.", 1, 1

    by_user: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        by_user[int(r["user_id"])].append(r)

    user_ids = sorted(by_user.keys())
    total_users = len(user_ids)
    total_pages = max(1, (total_users + _ALL_WALLETS_PAGE_SIZE - 1) // _ALL_WALLETS_PAGE_SIZE)
    page = max(1, min(page, total_pages))

    start = (page - 1) * _ALL_WALLETS_PAGE_SIZE
    page_ids = user_ids[start : start + _ALL_WALLETS_PAGE_SIZE]

    bal_cache: dict[str, Optional[float]] = {}
    for uid in page_ids:
        for w in by_user[uid]:
            addr = w["wallet_address"]
            if addr not in bal_cache:
                try:
                    bal_cache[addr] = await get_sol_balance(addr)
                except Exception:
                    bal_cache[addr] = None

    grand_total = 0.0
    lines = [
        f"🔑 <b>All User Wallets</b> — page {page}/{total_pages}",
        f"Users with wallets: <b>{total_users}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    for uid in page_ids:
        licensed = act_map.get(uid)
        if licensed is True:
            lic = "✅"
        elif licensed is False:
            lic = "🔒"
        else:
            lic = "—"

        user_total = 0.0
        lines.append(f"👤 <code>{uid}</code> {lic}")

        for w in by_user[uid]:
            bal = bal_cache.get(w["wallet_address"])
            if bal is not None:
                user_total += float(bal)
                grand_total += float(bal)
                bal_str = f"{float(bal):.4f}"
            else:
                bal_str = "?"

            tag = "FUND" if w["wallet_type"] == "fund" else "BUY"
            lines.append(
                f"  [{tag}] <code>{_short(w['wallet_address'])}</code>  ·  <b>{bal_str}</b> SOL"
            )

        lines.append(f"  Σ user: <b>{user_total:.4f}</b> SOL")
        lines.append("")

    lines.append(f"💎 <b>Page total:</b> {grand_total:.4f} SOL")
    lines.append(f"<i>Updated {_now_stamp()}</i>")
    lines.append("Tap a user detail: /walletuser <id>")

    text = "\n".join(lines)
    if len(text) > 3900:
        text = text[:3850] + "\n\n…truncated"
    return text, page, total_pages


async def _do_export_keys(message_or_cb_message, admin_id: int, uid: int, scope: str = "all") -> None:
    async with get_db() as db:
        async with db.execute(
            """
            SELECT id, wallet_address, wallet_type, label, encrypted_private_key, is_active
            FROM multi_wallets
            WHERE user_id = ? AND is_active = 1
            ORDER BY CASE wallet_type WHEN 'fund' THEN 0 ELSE 1 END, id ASC
            """,
            (uid,),
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]

    if scope == "fund":
        rows = [r for r in rows if r["wallet_type"] == "fund"]
    elif scope == "buy":
        rows = [r for r in rows if r["wallet_type"] == "buy"]

    if not rows:
        await message_or_cb_message.answer(
            f"No active wallets for user <code>{uid}</code> (scope={scope}).",
            parse_mode="HTML",
        )
        return

    logger.warning(
        "ADMIN_EXPORT_KEY admin=%s target_user=%s scope=%s count=%s",
        admin_id, uid, scope, len(rows),
    )

    await message_or_cb_message.answer(
        f"⚠️ <b>Private keys for user {uid}</b>\n"
        f"Scope: <code>{scope}</code> · {len(rows)} wallet(s)\n"
        f"Delete these messages after use.",
        parse_mode="HTML",
    )

    for w in rows:
        try:
            kp = await get_keypair_from_wallet(w)
            priv = _keypair_to_base58(kp)
            kind = "Fund" if w["wallet_type"] == "fund" else (w.get("label") or "Buy")
            await message_or_cb_message.answer(
                f"🔐 <b>{kind}</b>\n"
                f"Address:\n<code>{w['wallet_address']}</code>\n\n"
                f"Private key:\n<code>{priv}</code>",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.exception("exportkey decrypt failed user=%s wallet=%s", uid, w.get("id"))
            await message_or_cb_message.answer(
                f"❌ Failed to decrypt {w.get('wallet_type')} "
                f"<code>{_short(w.get('wallet_address') or '')}</code>: {e}",
                parse_mode="HTML",
            )


# ── Commands ──────────────────────────────────────────────────────────────────

@router.message(Command("myid"))
async def cmd_myid(message: Message) -> None:
    uid = message.from_user.id
    name = message.from_user.username or message.from_user.first_name
    admin_note = "✅ You are an admin." if is_admin(uid) else (
        "Add this ID to <code>ADMIN_IDS</code> in Railway Variables to unlock admin."
    )
    await message.answer(
        f"👤 <b>Your Telegram ID</b>\n\n<code>{uid}</code>\n\nName: {name}\n\n{admin_note}",
        parse_mode="HTML",
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if _deny_msg(message):
        return

    await message.answer(
        "🛠 <b>ShadowSnipe Admin</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>Keys</b>\n"
        "/genkey — open license key\n"
        "/genkey <user_id> — key locked to that Telegram ID\n"
        "/listkeys — unused keys\n\n"
        "<b>Access</b>\n"
        "/activate <user_id> — grant access (no payment)\n"
        "/deactivate <user_id> — revoke access\n"
        "/adminuser <user_id> — full user summary\n\n"
        "<b>Wallets</b>\n"
        "/allwallets — live balances for ALL users (+ Refresh)\n"
        "/walletuser <user_id> — one user (+ Refresh / Export)\n"
        "/exportkey <user_id> — export private keys\n\n"
        "<b>Overview</b>\n"
        "/stats · /activations\n\n"
        "⚠️ <i>Export is admin-only. Treat keys like cash.</i>",
        parse_mode="HTML",
    )


@router.message(Command("genkey"))
async def cmd_genkey(message: Message) -> None:
    if _deny_msg(message):
        await message.answer("Unauthorized.")
        return

    parts = (message.text or "").split()
    assigned_to = None
    if len(parts) >= 2 and parts[1].isdigit():
        assigned_to = int(parts[1])

    try:
        key = await create_license_key(message.from_user.id, assigned_to=assigned_to)
        if assigned_to:
            note = f"🔒 Reserved for Telegram ID <code>{assigned_to}</code> only."
        else:
            note = "🔓 Open key — first account that completes payment locks it."
        await message.answer(
            f"🔑 <b>New License Key</b>\n\n<code>{key}</code>\n\n{note}",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.exception("genkey failed")
        await message.answer(f"Failed to generate key: {e}")


@router.message(Command("activate"))
async def cmd_activate(message: Message) -> None:
    if _deny_msg(message):
        return

    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Usage: /activate <telegram_user_id>", parse_mode="HTML")
        return

    uid = int(parts[1])
    await admin_force_activate(uid, note=f"ADMIN:{message.from_user.id}")
    await message.answer(
        f"✅ User <code>{uid}</code> is now <b>activated</b> (admin grant).",
        parse_mode="HTML",
    )


@router.message(Command("deactivate"))
async def cmd_deactivate(message: Message) -> None:
    if _deny_msg(message):
        return

    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Usage: /deactivate <telegram_user_id>", parse_mode="HTML")
        return

    uid = int(parts[1])
    if is_admin(uid):
        await message.answer("Cannot deactivate an admin account.")
        return

    ok = await admin_deactivate(uid)
    if ok:
        await message.answer(f"🔒 User <code>{uid}</code> deactivated.", parse_mode="HTML")
    else:
        await message.answer(
            f"No activation row for <code>{uid}</code>.",
            parse_mode="HTML",
        )


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if _deny_msg(message):
        return

    s = await get_activation_stats()
    await message.answer(
        "📊 <b>ShadowSnipe Stats</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Active licenses: <b>{s['active_users']}</b>\n"
        f"License keys total: <b>{s['keys_total']}</b>\n"
        f"Unused keys: <b>{s['keys_unused']}</b>\n"
        f"Payment sigs claimed: <b>{s['payments_claimed']}</b>",
        parse_mode="HTML",
    )


@router.message(Command("listkeys"))
async def cmd_listkeys(message: Message) -> None:
    if _deny_msg(message):
        return

    keys = await list_unused_keys(20)
    if not keys:
        await message.answer("No unused keys.")
        return

    lines = ["🔑 <b>Unused license keys</b>\n"]
    for k in keys:
        assigned = k.get("assigned_to")
        lock = f" → {assigned}" if assigned else " (open)"
        lines.append(f"<code>{k['key_code']}</code>{lock}")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("activations"))
async def cmd_activations(message: Message) -> None:
    if _deny_msg(message):
        return

    rows = await list_recent_activations(15)
    if not rows:
        await message.answer("No activations yet.")
        return

    lines = ["📋 <b>Recent activations</b>\n"]
    for r in rows:
        status = "✅" if r.get("is_active") else "🔒"
        lines.append(
            f"{status} <code>{r['user_id']}</code> · {r.get('activated_at') or '—'}\n"
            f"   key: <code>{r.get('license_key') or '—'}</code>"
        )
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("adminuser"))
async def cmd_adminuser(message: Message) -> None:
    if _deny_msg(message):
        return

    parts = (message.text or "").strip().split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Usage: /adminuser <user_id>", parse_mode="HTML")
        return

    uid = int(parts[1])
    activated = await is_user_activated(uid)

    async with get_db() as db:
        async with db.execute(
            "SELECT username, first_name, created_at FROM users WHERE telegram_user_id = ?",
            (uid,),
        ) as cur:
            user_row = await cur.fetchone()

        async with db.execute(
            """
            SELECT license_key, payment_signature, activated_at, is_active
            FROM user_activations WHERE user_id = ?
            """,
            (uid,),
        ) as cur:
            act = await cur.fetchone()

        async with db.execute(
            """
            SELECT wallet_address, wallet_type, label, is_active
            FROM multi_wallets WHERE user_id = ?
            ORDER BY wallet_type, id
            """,
            (uid,),
        ) as cur:
            wallets = await cur.fetchall()

    name = "—"
    joined = "—"
    if user_row:
        name = user_row["username"] or user_row["first_name"] or "—"
        joined = user_row["created_at"] or "—"

    act_line = "not in DB"
    if act:
        flag = "active" if act["is_active"] else "revoked"
        act_line = (
            f"{flag}\n"
            f"Key: <code>{act['license_key']}</code>\n"
            f"At: {act['activated_at']}"
        )

    wallet_lines = []
    for w in wallets or []:
        wallet_lines.append(
            f"• [{w['wallet_type']}] <code>{w['wallet_address']}</code> "
            f"{'(on)' if w['is_active'] else '(off)'}"
        )
    wallets_text = "\n".join(wallet_lines) if wallet_lines else "none"

    await message.answer(
        f"👤 <b>User {uid}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Name:</b> {name}\n"
        f"<b>Joined:</b> {joined}\n"
        f"<b>License gate:</b> {'✅ pass' if activated else '🔒 blocked'}\n\n"
        f"<b>Activation:</b>\n{act_line}\n\n"
        f"<b>Multi-wallets:</b>\n{wallets_text}\n\n"
        f"Open live view: /walletuser {uid}",
        parse_mode="HTML",
        reply_markup=_kb_walletuser(uid),
    )


@router.message(Command("walletuser"))
async def cmd_walletuser(message: Message) -> None:
    if _deny_msg(message):
        return

    parts = (message.text or "").strip().split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Usage: /walletuser <telegram_user_id>", parse_mode="HTML")
        return

    uid = int(parts[1])
    status = await message.answer("⏳ Fetching live balances…")
    text, _ = await _build_walletuser_text(uid)
    try:
        await status.edit_text(text, parse_mode="HTML", reply_markup=_kb_walletuser(uid))
    except Exception:
        await message.answer(text, parse_mode="HTML", reply_markup=_kb_walletuser(uid))


@router.message(Command("allwallets"))
async def cmd_allwallets(message: Message) -> None:
    if _deny_msg(message):
        return

    parts = (message.text or "").strip().split()
    page = 1
    if len(parts) >= 2 and parts[1].isdigit():
        page = max(1, int(parts[1]))

    status = await message.answer("⏳ Fetching all wallets + live balances…")
    text, page, total_pages = await _build_allwallets_page(page)
    try:
        await status.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=_kb_allwallets(page, total_pages),
        )
    except Exception:
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=_kb_allwallets(page, total_pages),
        )


@router.message(Command("exportkey"))
async def cmd_exportkey(message: Message) -> None:
    if _deny_msg(message):
        return

    parts = (message.text or "").strip().split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer(
            "Usage:\n"
            "/exportkey <user_id> — all\n"
            "/exportkey <user_id> fund — fund only\n"
            "/exportkey <user_id> buy — buy only",
            parse_mode="HTML",
        )
        return

    uid = int(parts[1])
    scope = (parts[2].lower() if len(parts) >= 3 else "all")
    if scope not in ("all", "fund", "buy"):
        await message.answer("Scope must be: all | fund | buy")
        return

    await _do_export_keys(message, message.from_user.id, uid, scope)


# ── Callbacks: refresh / export / pagination ──────────────────────────────────

@router.callback_query(F.data.startswith("adm:wu:refresh:"))
async def cb_wu_refresh(callback: CallbackQuery) -> None:
    if _deny_cb(callback):
        await callback.answer("Unauthorized", show_alert=True)
        return

    uid = int(callback.data.split(":")[-1])
    await callback.answer("Refreshing…")
    text, _ = await _build_walletuser_text(uid)
    try:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=_kb_walletuser(uid),
        )
    except Exception as e:
        # same content → Telegram raises "message is not modified"
        if "not modified" not in str(e).lower():
            logger.warning("wu refresh edit failed: %s", e)


@router.callback_query(F.data.startswith("adm:wu:export:"))
async def cb_wu_export(callback: CallbackQuery) -> None:
    if _deny_cb(callback):
        await callback.answer("Unauthorized", show_alert=True)
        return

    uid = int(callback.data.split(":")[-1])
    await callback.answer("Exporting keys…")
    await _do_export_keys(callback.message, callback.from_user.id, uid, "all")


@router.callback_query(F.data.startswith("adm:aw:page:"))
async def cb_aw_page(callback: CallbackQuery) -> None:
    if _deny_cb(callback):
        await callback.answer("Unauthorized", show_alert=True)
        return

    page = int(callback.data.split(":")[-1])
    await callback.answer()
    await callback.message.edit_text("⏳ Loading page…", parse_mode="HTML")
    text, page, total_pages = await _build_allwallets_page(page)
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=_kb_allwallets(page, total_pages),
    )


@router.callback_query(F.data.startswith("adm:aw:refresh:"))
async def cb_aw_refresh(callback: CallbackQuery) -> None:
    if _deny_cb(callback):
        await callback.answer("Unauthorized", show_alert=True)
        return

    page = int(callback.data.split(":")[-1])
    await callback.answer("Refreshing balances…")
    text, page, total_pages = await _build_allwallets_page(page)
    try:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=_kb_allwallets(page, total_pages),
        )
    except Exception as e:
        if "not modified" not in str(e).lower():
            logger.warning("aw refresh edit failed: %s", e)
