"""
bot/handlers/activation.py
==========================
Guided license + payment activation flow
"""

import logging
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from services.license_service import (
    get_license_key,
    mark_key_used,
    is_user_activated,
    activate_user,
    verify_payment_transaction,
    create_license_key,
)
from utils.config import settings
from bot.keyboards.main_menu import build_main_menu

logger = logging.getLogger(__name__)
router = Router()


class ActivationStates(StatesGroup):
    waiting_for_license_key = State()
    waiting_for_payment_signature = State()


def _activation_wallet() -> str:
    return getattr(settings, "ACTIVATION_WALLET", "NOT_CONFIGURED")


# ── /start ────────────────────────────────────────────────────────────────────
@router.message(CommandStart())
async def handle_start(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if await is_user_activated(user_id):
        # Already activated → normal welcome
        await message.answer(
            "⚡ <b>SHADOWSNIPE</b>\n"
            "<code>ONLINE  //  SOLANA</code>\n\n"
            "Your license is active.\n"
            "Select a module below.",
            reply_markup=build_main_menu(),
            parse_mode="HTML"
        )
        return

    # Not activated → start guided flow
    await state.set_state(ActivationStates.waiting_for_license_key)
    await message.answer(
        "👋 <b>Welcome!</b>\n\n"
        "Please enter your <b>license key</b> to continue.\n\n"
        "Format example: <code>6H16K-J6LB6-ZK8U1-CWP1</code>",
        parse_mode="HTML"
    )


# ── License key received ──────────────────────────────────────────────────────
@router.message(ActivationStates.waiting_for_license_key)
async def process_license_key(message: Message, state: FSMContext):
    key = message.text.strip().upper()
    record = await get_license_key(key)

    if not record:
        await message.answer("❌ Invalid license key. Please try again.")
        return

    if record["is_used"]:
        await message.answer("❌ This license key has already been used.")
        return

    # Valid unused key → ask for payment
    await state.update_data(license_key=key)
    await state.set_state(ActivationStates.waiting_for_payment_signature)

    wallet = _activation_wallet()
    amount = getattr(settings, "ACTIVATION_AMOUNT_SOL", 1.0)

    await message.answer(
        f"✅ <b>License key verified</b>\n\n"
        f"Your activation fee is: <b>{amount} SOL</b>\n\n"
        f"Send exactly <b>{amount} SOL</b> to:\n"
        f"<code>{wallet}</code>\n\n"
        f"After sending the payment, reply with the <b>transaction signature</b>.",
        parse_mode="HTML"
    )


# ── Payment signature received ────────────────────────────────────────────────
@router.message(ActivationStates.waiting_for_payment_signature)
async def process_payment_signature(message: Message, state: FSMContext):
    signature = message.text.strip()
    data = await state.get_data()
    license_key = data.get("license_key")

    if not license_key:
        await message.answer("Session expired. Please /start again.")
        await state.clear()
        return

    await message.answer("⏳ Checking the transaction on Solana...")

    result = await verify_payment_transaction(signature)

    if not result["valid"]:
        await message.answer(
            f"❌ Payment verification failed.\n\n"
            f"<code>{result.get('error')}</code>\n\n"
            f"Please make sure you sent the correct amount to the correct address and try again.",
            parse_mode="HTML"
        )
        return

    # Success
    user_id = message.from_user.id
    await mark_key_used(license_key, user_id)
    await activate_user(user_id, license_key, signature)
    await state.clear()

    await message.answer(
        "✅ <b>ACTIVATION SUCCESSFUL!</b>\n\n"
        "✅ License verified\n"
        "✅ 1 SOL payment confirmed\n"
        "✅ License activated\n\n"
        "Your bot access is now enabled.\n\n"
        "Use /wallet to open Wallet Manager.",
        parse_mode="HTML"
    )


# ── Admin: Generate license keys ──────────────────────────────────────────────
@router.message(Command("genkey"))
async def cmd_genkey(message: Message):
    # Simple admin check
    admin_ids = getattr(settings, "ADMIN_IDS", []) or []
    if str(message.from_user.id) not in [str(x) for x in admin_ids]:
        return  # silent ignore

    try:
        key = await create_license_key(message.from_user.id)
        await message.answer(
            f"🔑 <b>New License Key generated:</b>\n\n"
            f"<code>{key}</code>\n\n"
            f"Share this key with the user.",
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"Failed to generate key: {e}")
