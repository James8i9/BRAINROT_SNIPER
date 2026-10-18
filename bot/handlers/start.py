"""
bot/handlers/start.py
=====================
Handles the /start command.
Sends the welcome message and the main menu keyboard.
"""

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.keyboards.main_menu import build_main_menu
from utils.config import settings

router = Router()

_BOOT_FRAMES = [
    (
        "<code>█░░░░░░░░░ INITIALIZING...</code>\n\n"
        "⚡ <b>SHADOWSNIPE BOT</b>\n"
        "<code>[ CONNECTING TO SOLANA ]</code>"
    ),
    (
        "<code>████░░░░░░ LOADING MODULES...</code>\n\n"
        "⚡ <b>SHADOWSNIPE BOT</b>\n"
        "<code>[ SYNCING CHAIN DATA   ]</code>"
    ),
    (
        "<code>██████████ ONLINE</code>\n\n"
        "⚡ <b>SHADOWSNIPE BOT</b>\n"
        "<code>[ ALL SYSTEMS NOMINAL  ]</code>"
    ),
]

WELCOME_TEXT = (
    "⚡ <b>SHADOWSNIPE</b>\n"
    "<code>ONLINE  //  SOLANA</code>\n\n"
    "🎯 <b>Sniper Tool</b> — Auto-buy on launch\n"
    "📋 <b>Copy Trade</b> — Mirror smart wallets\n"
    "🕯️ <b>Candle Sniper</b> — Pattern entries\n"
    "💼 <b>Multi-Wallet</b> — Fund + Buy + Distribute\n\n"
    "<i>Select a module below.</i>"
)


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    import asyncio
    # Boot sequence flash animation
    msg = await message.answer(_BOOT_FRAMES[0])
    await asyncio.sleep(0.6)
    await msg.edit_text(_BOOT_FRAMES[1], parse_mode="HTML")
    await asyncio.sleep(0.6)
    await msg.edit_text(_BOOT_FRAMES[2], parse_mode="HTML")
    await asyncio.sleep(0.5)
    await msg.edit_text(WELCOME_TEXT, reply_markup=build_main_menu(), parse_mode="HTML")
