"""
bot/handlers/commands.py
========================
Handles the slash commands shown in the Telegram menu.
All important commands are gated behind license activation.
"""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from bot.keyboards.multi_wallet_menu import build_multi_wallet_menu, build_back_to_mw
from bot.handlers.multi_wallet import MultiWalletStates, _build_wallet_overview
from services.multi_wallet_service import get_fund_wallet
from services.license_service import is_user_activated

router = Router()


async def _require_license(message: Message) -> bool:
    if await is_user_activated(message.from_user.id):
        return True
    await message.answer(
        "🔒 ShadowSnipe license is not active.",
        parse_mode="HTML",
    )
    return False


@router.message(Command("wallet"))
async def cmd_wallet(message: Message, state: FSMContext):
    if not await _require_license(message):
        return

    user_id = message.from_user.id
    fund = await get_fund_wallet(user_id)

    # First-time setup: jump straight to Import Fund Wallet
    if not fund:
        await state.set_state(MultiWalletStates.waiting_for_fund_key)
        await message.answer(
            "📥 <b>Import Fund Wallet</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Send the <b>private key</b> of the wallet you want to use as Fund Wallet.\n\n"
            "Accepted formats:\n"
            "• Base58 private key\n"
            "• 64-byte hex\n"
            "• JSON array\n\n"
            "⚠️ Only import a wallet you own.\n"
            "The key will be encrypted at rest.",
            reply_markup=build_back_to_mw(),
            parse_mode="HTML",
        )
        return

    # Already has a fund wallet → full manager overview
    await state.clear()
    text = await _build_wallet_overview(user_id)
    await message.answer(
        text,
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
