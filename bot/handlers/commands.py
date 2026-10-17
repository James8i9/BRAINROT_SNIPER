"""
bot/handlers/commands.py
========================
Handles the slash commands shown in the Telegram menu.
"""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.keyboards.multi_wallet_menu import build_multi_wallet_menu
from bot.keyboards.main_menu import build_main_menu

router = Router()


@router.message(Command("wallet"))
async def cmd_wallet(message: Message):
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
    # Re-use the existing sniper main callback logic if possible
    # For now just send a message that opens the sniper
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 Open Sniper Tool", callback_data="sniper:main")]
    ])
    await message.answer("🎯 <b>Sniper Tool</b>", reply_markup=kb, parse_mode="HTML")


@router.message(Command("copy"))
async def cmd_copy(message: Message):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Open Copy Trade", callback_data="ct:main")]
    ])
    await message.answer("📋 <b>Copy Trade</b>", reply_markup=kb, parse_mode="HTML")


@router.message(Command("candle"))
async def cmd_candle(message: Message):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🕯️ Open Candle Sniper", callback_data="cs:main")]
    ])
    await message.answer("🕯️ <b>Candle Sniper</b>", reply_markup=kb, parse_mode="HTML")


@router.message(Command("portfolio"))
async def cmd_portfolio(message: Message):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📈 View Portfolio", callback_data="menu:portfolio_guide")]
    ])
    await message.answer("📈 <b>Portfolio</b>", reply_markup=kb, parse_mode="HTML")


@router.message(Command("profile"))
async def cmd_profile(message: Message):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Open Profile", callback_data="profile:main")]
    ])
    await message.answer("👤 <b>Profile</b>", reply_markup=kb, parse_mode="HTML")
