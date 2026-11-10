"""
bot/handlers/commands.py
========================
Handles the slash commands shown in the Telegram menu.
All important commands are gated behind license activation.
"""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.fsm.context import FSMContext

from bot.keyboards.multi_wallet_menu import (
    build_multi_wallet_menu,
    build_cancel_import,
)
from bot.handlers.multi_wallet import MultiWalletStates, _build_wallet_overview
from services.multi_wallet_service import get_fund_wallet
from services.license_service import is_user_activated
from utils.config import settings

router = Router()


async def _require_license(message: Message) -> bool:
    if await is_user_activated(message.from_user.id):
        return True
    await message.answer(
        "🔒 ShadowSnipe license is not active.",
        parse_mode="HTML",
    )
    return False


def _mini_app_keyboard() -> InlineKeyboardMarkup | None:
    url = (settings.MINI_APP_URL or "").rstrip("/")
    if not url:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="☠ Open ShadowSnipe Terminal",
            web_app=WebAppInfo(url=url),
        )]
    ])


@router.message(Command("app"))
async def cmd_app(message: Message):
    """Open the ShadowSnipe Mini App terminal."""
    kb = _mini_app_keyboard()
    if not kb:
        await message.answer(
            "⚠️ Mini App URL is not configured.\n\n"
            "Set <code>MINI_APP_URL</code> to your Railway public HTTPS URL\n"
            "(example: <code>https://your-app.up.railway.app</code>), then redeploy.",
            parse_mode="HTML",
        )
        return

    activated = await is_user_activated(message.from_user.id)
    note = (
        "Your portfolio & wallets open in the terminal."
        if activated
        else "You can open the shell; trading unlocks after activation."
    )
    await message.answer(
        "☠ <b>SHADOW_SNIPE TERMINAL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{note}\n\n"
        "Tap the button below to launch the Mini App.",
        reply_markup=kb,
        parse_mode="HTML",
    )


@router.message(Command("wallet"))
async def cmd_wallet(message: Message, state: FSMContext):
    if not await _require_license(message):
        return

    user_id = message.from_user.id
    fund = await get_fund_wallet(user_id)

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
            reply_markup=build_cancel_import(),
            parse_mode="HTML",
        )
        return

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
