"""
bot/handlers/pnl.py
===================
Manual PnL card command.

  /pnl <token_mint_or_symbol>
  /pnl                       — help
"""

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from services.license_service import is_user_activated
from services.pnl_card_service import send_pnl_card, get_token_symbol
from database.sqlite_db import get_db

logger = logging.getLogger(__name__)
router = Router()


async def _resolve_token(user_id: int, query: str) -> str | None:
    """Resolve symbol or mint to a token_address the user has traded."""
    q = (query or "").strip()
    if not q:
        return None

    # Looks like a mint
    if len(q) >= 32:
        return q

    symbol = q.lstrip("$").upper()
    async with get_db() as db:
        async with db.execute(
            """
            SELECT token_address FROM tracked_positions
            WHERE user_id = ? AND UPPER(REPLACE(token_symbol, '$', '')) = ?
            ORDER BY id DESC LIMIT 1
            """,
            (user_id, symbol),
        ) as cur:
            row = await cur.fetchone()
            if row:
                return row["token_address"]

        async with db.execute(
            """
            SELECT token_address FROM submitted_transactions
            WHERE user_id = ? AND token_address LIKE ?
            ORDER BY id DESC LIMIT 1
            """,
            (user_id, f"%{q}%"),
        ) as cur:
            row = await cur.fetchone()
            if row:
                return row["token_address"]

    return None


@router.message(Command("pnl"))
async def cmd_pnl(message: Message) -> None:
    user_id = message.from_user.id

    if not await is_user_activated(user_id):
        await message.answer("🔒 ShadowSnipe license is not active.")
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        # Show recent tokens if any
        async with get_db() as db:
            async with db.execute(
                """
                SELECT DISTINCT token_address, token_symbol FROM tracked_positions
                WHERE user_id = ?
                ORDER BY id DESC LIMIT 8
                """,
                (user_id,),
            ) as cur:
                rows = await cur.fetchall()

        if not rows:
            await message.answer(
                "📈 <b>PnL Card</b>\n\n"
                "Usage: <code>/pnl TOKEN</code> or <code>/pnl <mint></code>\n\n"
                "No positions found yet. Trade first, then generate a card.",
                parse_mode="HTML",
            )
            return

        lines = ["📈 <b>PnL Card</b>\n", "Recent tokens:"]
        for r in rows:
            sym = r["token_symbol"] or "TOKEN"
            mint = r["token_address"]
            short = f"{mint[:4]}…{mint[-4:]}" if mint and len(mint) > 10 else mint
            lines.append(f"• <code>/pnl {sym}</code>  ({short})")
        lines.append("\nOr pass the full mint address.")
        await message.answer("\n".join(lines), parse_mode="HTML")
        return

    query = parts[1].strip()
    status = await message.answer("⏳ Building PnL card…")

    token = await _resolve_token(user_id, query)
    if not token:
        await status.edit_text(
            f"No trades found for <code>{query}</code>.\n"
            f"Use a symbol you traded or the full mint address.",
            parse_mode="HTML",
        )
        return

    stats = await send_pnl_card(
        message.bot,
        chat_id=message.chat.id,
        user_id=user_id,
        token_address=token,
    )

    if stats:
        try:
            await status.delete()
        except Exception:
            pass
    else:
        await status.edit_text(
            "❌ Could not render PnL card. Check logs / ensure Pillow is installed."
        )
