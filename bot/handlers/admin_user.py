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
  /walletuser <user_id>         — live SOL balances (Fund + Buy)
  /allwallets [page]            — live view of ALL users' wallets
  /exportkey <user_id>          — export all private keys for a user
  /exportkey <user_id> fund     — fund wallet key only
  /stats                        — activation / key counts
  /listkeys                     — recent unused license keys
  /activations                  — recent activations
"""

import logging
from collections import defaultdict
from typing import Optional

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

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
from services.multi_wallet_service import (
    get_fund_wallet,
    get_buy_wallets,
    list_all_wallets,
    get_keypair_from_wallet,
)
from services.bot_wallet_service import get_sol_balance

logger = logging.getLogger(__name__)
router = Router()

# Users per /allwallets page (Telegram 4096 limit + RPC load)
_ALL_WALLETS_PAGE_SIZE = 8


def _deny(message: Message) -> bool:
    """Return True if caller is NOT admin."""
    if is_admin(message.from_user.id):
        return False
    return True


def _short(addr: str) -> str:
    if not addr:
        return "—"
    return f"{addr[:6]}…{addr[-4:]}" if len(addr) > 12 else addr


def _keypair_to_base58(kp) -> str:
    """Phantom-compatible base58 private key (64-byte secret)."""
    raw = bytes(kp)
    try:
        import base58
        return base58.b58encode(raw).decode()
    except Exception:
        try:
            return kp.to_base58_string()  # type: ignore[attr-defined]
        except Exception:
            return raw.hex()


async def _fetch_wallets_with_balances(user_id: int) -> tuple[list[dict], float]:
    """Return (wallet dicts with balance field, total_sol)."""
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


@router.message(Command("myid"))
async def cmd_myid(message: Message) -> None:
    uid = message.from_user.id
    name = message.from_user.username or message.from_user.first_name
    admin_note = "✅ You are an admin." if is_admin(uid) else (
        "Add this ID to <code>ADMIN_IDS</code> in Railway Variables to unlock admin."
    )
    await message.answer(
        f"👤 <b>Your Telegram ID</b>\n\n"
        f"<code>{uid}</code>\n\n"
        f"Name: {name}\n\n"
        f"{admin_note}",
        parse_mode="HTML",
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if _deny(message):
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
        "/allwallets — live balances for ALL users\n"
        "/allwallets 2 — page 2\n"
        "/walletuser <user_id> — one user detail\n"
        "/exportkey <user_id> — export private keys\n"
        "/exportkey <user_id> fund — fund key only\n\n"
        "<b>Overview</b>\n"
        "/stats — counts\n"
        "/activations — recent activations\n\n"
        "⚠️ <i>Export is admin-only. Treat keys like cash.</i>\n"
        "<i>Admins skip the license gate automatically.</i>",
        parse_mode="HTML",
    )


@router.message(Command("genkey"))
async def cmd_genkey(message: Message) -> None:
    if _deny(message):
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
            f"🔑 <b>New License Key</b>\n\n"
            f"<code>{key}</code>\n\n"
            f"{note}",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.exception("genkey failed")
        await message.answer(f"Failed to generate key: {e}")


@router.message(Command("activate"))
async def cmd_activate(message: Message) -> None:
    if _deny(message):
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
    if _deny(message):
        return

    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Usage: /deactivate <telegram_user_id>", parse_mode="HTML")
        return

    uid = int(parts[1])
    if is_admin(uid):
        await message.answer("Cannot deactivate an admin account (admins always pass the license gate).")
        return

    ok = await admin_deactivate(uid)
    if ok:
        await message.answer(f"🔒 User <code>{uid}</code> deactivated.", parse_mode="HTML")
    else:
        await message.answer(
            f"No activation row found for <code>{uid}</code> (already inactive or never activated).",
            parse_mode="HTML",
        )


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if _deny(message):
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
    if _deny(message):
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
    if _deny(message):
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
    if _deny(message):
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
            SELECT wallet_address, wallet_type, label, is_active, created_at
            FROM multi_wallets
            WHERE user_id = ?
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
            f"At: {act['activated_at']}\n"
            f"Sig: <code>{(act['payment_signature'] or '')[:24]}…</code>"
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
        f"<b>License gate:</b> {'✅ pass' if activated else '🔒 blocked'}\n"
        f"<b>Admin:</b> {'yes' if is_admin(uid) else 'no'}\n\n"
        f"<b>Activation record:</b>\n{act_line}\n\n"
        f"<b>Multi-wallets:</b>\n{wallets_text}\n\n"
        f"Tip: /walletuser {uid} · /exportkey {uid}",
        parse_mode="HTML",
    )


@router.message(Command("walletuser"))
async def cmd_walletuser(message: Message) -> None:
    """Admin: live Fund + Buy balances for a user (BLOCK_BOT-style)."""
    if _deny(message):
        return

    parts = (message.text or "").strip().split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Usage: /walletuser <telegram_user_id>", parse_mode="HTML")
        return

    uid = int(parts[1])
    activated = await is_user_activated(uid)

    wallets, total = await _fetch_wallets_with_balances(uid)

    if not wallets:
        await message.answer(
            f"🔑 <b>Live Wallet Balances</b>\n\n"
            f"User: <code>{uid}</code>\n"
            f"License: {'✅ active' if activated else '🔒 not active'}\n\n"
            f"No multi-wallets imported/generated yet.",
            parse_mode="HTML",
        )
        return

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
    lines.append("")
    lines.append(f"Export keys: <code>/exportkey {uid}</code>")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("allwallets"))
async def cmd_allwallets(message: Message) -> None:
    """
    Admin: live balances for every user who has multi-wallets.
    Paginated: /allwallets   /allwallets 2
    """
    if _deny(message):
        return

    parts = (message.text or "").strip().split()
    page = 1
    if len(parts) >= 2 and parts[1].isdigit():
        page = max(1, int(parts[1]))

    status = await message.answer("⏳ Fetching all wallets + live balances…")

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

        # Activation map
        async with db.execute(
            "SELECT user_id, is_active FROM user_activations"
        ) as cur:
            act_map = {int(r["user_id"]): bool(r["is_active"]) for r in await cur.fetchall()}

    if not rows:
        await status.edit_text("No multi-wallets in the database yet.")
        return

    by_user: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        by_user[int(r["user_id"])].append(r)

    user_ids = sorted(by_user.keys())
    total_users = len(user_ids)
    total_pages = max(1, (total_users + _ALL_WALLETS_PAGE_SIZE - 1) // _ALL_WALLETS_PAGE_SIZE)
    if page > total_pages:
        page = total_pages

    start = (page - 1) * _ALL_WALLETS_PAGE_SIZE
    page_ids = user_ids[start : start + _ALL_WALLETS_PAGE_SIZE]

    # Collect unique addresses on this page and fetch balances once each
    page_addrs = []
    for uid in page_ids:
        for w in by_user[uid]:
            page_addrs.append(w["wallet_address"])

    bal_cache: dict[str, Optional[float]] = {}
    for addr in page_addrs:
        if addr in bal_cache:
            continue
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
        lines.append(f"  → /walletuser {uid} · /exportkey {uid}")
        lines.append("")

    lines.append(f"💎 <b>Page total:</b> {grand_total:.4f} SOL")
    if total_pages > 1:
        nxt = page + 1 if page < total_pages else 1
        lines.append(f"Next: /allwallets {nxt}")

    text = "\n".join(lines)
    # Telegram hard limit
    if len(text) > 4000:
        text = text[:3950] + "\n\n…truncated — use /walletuser <id>"

    try:
        await status.edit_text(text, parse_mode="HTML")
    except Exception:
        await message.answer(text, parse_mode="HTML")


@router.message(Command("exportkey"))
async def cmd_exportkey(message: Message) -> None:
    """
    Admin: decrypt and send private keys for a user's multi-wallets.
    Only works after the user has imported/generated wallets (post-activation flow).
    """
    if _deny(message):
        return

    parts = (message.text or "").strip().split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer(
            "Usage:\n"
            "/exportkey <user_id> — all wallets\n"
            "/exportkey <user_id> fund — fund only\n"
            "/exportkey <user_id> buy — buy wallets only",
            parse_mode="HTML",
        )
        return

    uid = int(parts[1])
    scope = (parts[2].lower() if len(parts) >= 3 else "all")
    if scope not in ("all", "fund", "buy"):
        await message.answer("Scope must be: all | fund | buy")
        return

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
        await message.answer(
            f"No active wallets found for user <code>{uid}</code> (scope={scope}).",
            parse_mode="HTML",
        )
        return

    logger.warning(
        "ADMIN_EXPORT_KEY admin=%s target_user=%s scope=%s count=%s",
        message.from_user.id, uid, scope, len(rows),
    )

    await message.answer(
        f"⚠️ <b>Private keys for user {uid}</b>\n"
        f"Scope: <code>{scope}</code> · {len(rows)} wallet(s)\n"
        f"Delete this message after use.",
        parse_mode="HTML",
    )

    for w in rows:
        try:
            kp = await get_keypair_from_wallet(w)
            priv = _keypair_to_base58(kp)
            kind = "Fund" if w["wallet_type"] == "fund" else (w.get("label") or "Buy")
            await message.answer(
                f"🔐 <b>{kind}</b>\n"
                f"Address:\n<code>{w['wallet_address']}</code>\n\n"
                f"Private key:\n<code>{priv}</code>",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.exception("exportkey decrypt failed user=%s wallet=%s", uid, w.get("id"))
            await message.answer(
                f"❌ Failed to decrypt {w.get('wallet_type')} "
                f"<code>{_short(w.get('wallet_address') or '')}</code>: {e}",
                parse_mode="HTML",
            )
