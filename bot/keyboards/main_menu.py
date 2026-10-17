"""
bot/keyboards/main_menu.py
==========================
Clean main menu — only the modules we actually use.
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils.config import settings


def build_main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    # ── Wallet (Multi-Wallet Manager) ─────────────────────────────────────────
    builder.row(
        InlineKeyboardButton(text="💼  WALLET", callback_data="mw:main"),
    )

    # ── Core Trading Modules ──────────────────────────────────────────────────
    builder.row(
        InlineKeyboardButton(text="🎯  SNIPER TOOL", callback_data="sniper:main"),
    )
    builder.row(
        InlineKeyboardButton(text="📋  COPY TRADE", callback_data="ct:main"),
    )
    builder.row(
        InlineKeyboardButton(text="🕯️  CANDLE SNIPER", callback_data="cs:main"),
    )

    # ── Portfolio + Profile ────────────────────────────────────────────────────
    builder.row(
        InlineKeyboardButton(text="📈  VIEW MY PORTFOLIO", callback_data="menu:portfolio_guide"),
    )
    builder.row(
        InlineKeyboardButton(text="👤  PROFILE", callback_data="profile:main"),
    )

    return builder.as_markup()


def build_watchlist_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🪙 TOKENS",  callback_data="wl:tokens"),
        InlineKeyboardButton(text="👛 WALLETS", callback_data="wl:wallets"),
    )
    builder.row(
        InlineKeyboardButton(text="⬅️  BACK", callback_data="menu:back"),
    )
    return builder.as_markup()


def build_back_button() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⬅️  Back to Menu", callback_data="menu:back")
    )
    return builder.as_markup()
