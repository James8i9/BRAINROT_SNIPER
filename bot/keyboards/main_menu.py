"""
bot/keyboards/main_menu.py
==========================
Post-activation main menu: Wallet only.
Flow: import fund wallet → generate buy wallets → distribute SOL.
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
