"""
bot/keyboards/main_menu.py
==========================
Clean main menu — only the modules we actually use.
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def build_main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="💼  WALLET", callback_data="mw:main"),
    )
    builder.row(
        InlineKeyboardButton(text="🎯  SNIPER TOOL", callback_data="sniper:main"),
    )
    builder.row(
        InlineKeyboardButton(text="📋  COPY TRADE", callback_data="ct:main"),
    )

    return builder.as_markup()


def build_back_button() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⬅️  Back to Menu", callback_data="menu:back")
    )
    return builder.as_markup()
