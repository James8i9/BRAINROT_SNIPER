"""
bot/keyboards/main_menu.py
==========================
Post-activation focus: import fund wallet → buy wallets → distribute SOL.
Sniper / Copy Trade stay available via /sniper and /copy commands later.
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def build_main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="💼  WALLET", callback_data="mw:main"),
    )

    return builder.as_markup()


def build_back_button() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⬅️  Back to Menu", callback_data="menu:back")
    )
    return builder.as_markup()
