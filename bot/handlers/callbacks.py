"""
bot/handlers/callbacks.py
=========================
Handles main-menu inline callbacks (help, onboarding, back).
"""

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext

from bot.keyboards.main_menu import build_main_menu, build_back_button
from utils.config import settings

router = Router()


_FAQ: dict[str, tuple[str, str]] = {
    "wallet": (
        "💼 Wallet & Funding",
        (
            "💼 <b>Wallet & Funding — FAQ</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>Where is my fund wallet?</b>\n"
            "Tap <b>Wallet</b> and import the private key of the wallet that holds your capital.\n\n"
            "<b>What are buy wallets?</b>\n"
            "Generated wallets used for sniping. Fund them from your Fund Wallet via Distribute SOL.\n\n"
            "<b>Is my private key safe?</b>\n"
            "Yes — private keys are AES-256 encrypted before storage. "
            "The bot never logs or transmits them."
        ),
    ),
    "general": (
        "❓ General",
        (
            "❓ <b>General FAQ</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "After activation, open <b>Wallet</b> to:\n"
            "1. Import your Fund Wallet\n"
            "2. Generate Buy Wallets\n"
            "3. Distribute SOL from Fund → Buy wallets\n\n"
            "Contact the admin if you need help."
        ),
    ),
}


def _build_help_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, (label, _) in _FAQ.items():
        builder.row(InlineKeyboardButton(text=label, callback_data=f"help:{key}"))
    builder.row(InlineKeyboardButton(text="⬅️ Back to Menu", callback_data="menu:back"))
    return builder.as_markup()


def _build_help_back() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ Back to Help", callback_data="menu:help"))
    return builder.as_markup()


@router.callback_query(F.data == "menu:help")
async def cb_help(callback: CallbackQuery) -> None:
    text = (
        "❓ <b>Help & FAQ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Select a topic below:"
    )
    await callback.message.edit_text(text, reply_markup=_build_help_menu(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("help:"))
async def cb_help_topic(callback: CallbackQuery) -> None:
    key = callback.data.split(":", 1)[1]
    if key not in _FAQ:
        await callback.answer("Topic not found.", show_alert=True)
        return
    _, text = _FAQ[key]
    await callback.message.edit_text(
        text,
        reply_markup=_build_help_back(),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    await callback.answer()


@router.callback_query(F.data == "menu:new_users")
async def cb_new_users(callback: CallbackQuery) -> None:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💼  Go to Wallet", callback_data="mw:main"))
    builder.row(InlineKeyboardButton(text="⬅️  Back to Menu", callback_data="menu:back"))
    text = (
        "🆕 <b>GET STARTED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "1. Import your <b>Fund Wallet</b> (private key)\n"
        "2. Generate <b>Buy Wallets</b>\n"
        "3. <b>Distribute SOL</b> from Fund → Buy wallets\n\n"
        "Open Wallet to continue."
    )
    await callback.message.edit_text(
        text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("wip:"))
async def cb_wip(callback: CallbackQuery) -> None:
    await callback.answer("🚧 Under Construction — coming soon!", show_alert=True)


@router.callback_query(F.data == "menu:back")
async def cb_back(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await state.clear()
    except Exception:
        pass
    await callback.message.edit_text(
        text=(
            "📋 <b>Main Menu</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Next steps:\n"
            "1. Import your <b>Fund Wallet</b>\n"
            "2. Generate <b>Buy Wallets</b>\n"
            "3. <b>Distribute SOL</b> from Fund → Buy wallets\n\n"
            "Open Wallet to continue:"
        ),
        reply_markup=build_main_menu(),
        parse_mode="HTML",
    )
    await callback.answer()
