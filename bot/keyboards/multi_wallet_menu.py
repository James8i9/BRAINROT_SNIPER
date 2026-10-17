"""
bot/keyboards/multi_wallet_menu.py
==================================
Keyboards for the Multi-Wallet Manager (Fund + Buy Wallets).
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def build_multi_wallet_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="📥 Import Fund Wallet", callback_data="mw:import_fund"),
    )
    builder.row(
        InlineKeyboardButton(text="⚙️ Generate Buy Wallets", callback_data="mw:generate"),
    )
    builder.row(
        InlineKeyboardButton(text="📋 My Wallets", callback_data="mw:list"),
    )
    builder.row(
        InlineKeyboardButton(text="💸 Distribute SOL", callback_data="mw:distribute"),
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Back to Menu", callback_data="menu:back"),
    )
    return builder.as_markup()


def build_generate_count_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="2", callback_data="mw:gen:2"),
        InlineKeyboardButton(text="3", callback_data="mw:gen:3"),
        InlineKeyboardButton(text="5", callback_data="mw:gen:5"),
    )
    builder.row(
        InlineKeyboardButton(text="10", callback_data="mw:gen:10"),
        InlineKeyboardButton(text="Cancel", callback_data="mw:main"),
    )
    return builder.as_markup()


def build_back_to_mw() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⬅️ Back", callback_data="mw:main")
    )
    return builder.as_markup()


def build_confirm_distribute(amount: float) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Confirm & Send", callback_data=f"mw:confirm_dist:{amount}"),
    )
    builder.row(
        InlineKeyboardButton(text="❌ Cancel", callback_data="mw:main"),
    )
    return builder.as_markup()
