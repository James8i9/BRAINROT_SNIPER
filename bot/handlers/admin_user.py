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
  /exportkey <user_id>          — export all private keys for a user
  /exportkey <user_id> fund     — fund wallet key only
  /stats                        — activation / key counts
  /listkeys                     — recent unused license keys
  /activations                  — recent activations
"""

import logging
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
            # solders may expose this on some versions
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
        "<b>Wallets (after user activated + imported)</b>\n"
        "/walletuser <user_id> — live Fund + Buy balances\n"
        "/exportkey <user_id> — export all private keys\n"
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

    # Prefer activated users; still allow export if wallets exist (support edge cases)
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
            # Split: show address + key in code blocks for easy copy
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
