"""
bot/handlers/commands.py
========================
Handles the slash commands shown in the Telegram menu.
All important commands are gated behind license activation.
"""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from bot.keyboards.multi_wallet_menu import build_multi_wallet_menu
from services.license_service import is_user_activated

router = Router()


async def _require_license(message: Message) -> bool:
    """Return True if user is activated, otherwise send locked message and return False."""
    if await is_user_activated(message.from_user.id):
        return True
    await message.answer(
        "🔒 <b>Access Locked</b>\n\n"
        "You need an active license to use this feature.\n\n"
        "Use /start to activate your license.",
        parse_mode="HTML"
    )
    return False


@router.message(Command("wallet"))
async def cmd_wallet(message: Message):
    if not await _require_license(message):
        return

    await message.answer(
        "💼 <b>Multi-Wallet Manager</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "• <b>Fund Wallet</b> — your main capital wallet\n"
        "• <b>Buy Wallets</b> — wallets used for sniping\n\n"
        "Select an option:",
        reply_markup=build_multi_wallet_menu(),
        parse_mode="HTML",
    )


@router.message(Command("sniper"))
async def cmd_sniper(message: Message):
    if not await _require_license(message):
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 Open Sniper Tool", callback_data="sniper:main")]
    ])
    await message.answer("🎯 <b>Sniper Tool</b>", reply_markup=kb, parse_mode="HTML")


@router.message(Command("copy"))
async def cmd_copy(message: Message):
    if not await _require_license(message):
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Open Copy Trade", callback_data="ct:main")]
    ])
    await message.answer("📋 <b>Copy Trade</b>", reply_markup=kb, parse_mode="HTML")


@router.message(Command("candle"))
async def cmd_candle(message: Message):
    if not await _require_license(message):
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🕯️ Open Candle Sniper", callback_data="cs:main")]
    ])
    await message.answer("🕯️ <b>Candle Sniper</b>", reply_markup=kb, parse_mode="HTML")
