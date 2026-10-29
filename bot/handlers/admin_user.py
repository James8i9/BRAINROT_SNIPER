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
  /deactivate <user_id>         — revoke activation
  /adminuser <user_id>          — user + wallet + activation summary
  /stats                        — activation / key counts
  /listkeys                     — recent unused license keys
  /activations                  — recent activations
"""

import logging

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

logger = logging.getLogger(__name__)
router = Router()


def _deny(message: Message) -> bool:
    """Return True if caller is NOT admin (and optionally notify)."""
    if is_admin(message.from_user.id):
        return False
    # Silent for random users probing admin commands
    return True


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
        "<b>Overview</b>\n"
        "/stats — counts\n"
        "/activations — recent activations\n\n"
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
        await message.answer(f"No activation row found for <code>{uid}</code> (already inactive or never activated).", parse_mode="HTML")


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
        f"<b>Multi-wallets:</b>\n{wallets_text}",
        parse_mode="HTML",
    )
