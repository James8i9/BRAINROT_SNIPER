"""
bot/handlers/menu.py
====================
Handles the /menu command.
"""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.keyboards.main_menu import build_main_menu

router = Router()

MENU_TEXT = (
    "📋 <b>Main Menu</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "Next steps:\n"
    "1. Import your <b>Fund Wallet</b>\n"
    "2. Generate <b>Buy Wallets</b>\n"
    "3. <b>Distribute SOL</b> from Fund → Buy wallets\n\n"
    "Open Wallet to continue:"
)


@router.message(Command("menu"))
async def handle_menu(message: Message) -> None:
    await message.answer(
        text=MENU_TEXT,
        reply_markup=build_main_menu(),
        parse_mode="HTML",
    )
