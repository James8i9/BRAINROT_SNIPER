"""
bot/handlers/activation.py
==========================
Guided license + payment activation flow
"""

import logging
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
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


def _welcome_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 I HAVE A LICENSE", callback_data="act:have_license")],
        # You can add "VIEW ACCESS PLAN" later if you want
    ])


# ── /start ────────────────────────────────────────────────────────────────────
@router.message(CommandStart())
async def handle_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id

    if await is_user_activated(user_id):
        await message.answer(
            "⚡ <b>SHADOWSNIPE</b>\n"
            "<code>ONLINE  //  SOLANA</code>\n\n"
            "Your license is active.\n"
            "Select a module below.",
            reply_markup=build_main_menu(),
            parse_mode="HTML"
        )
        return

    # Not activated
    await message.answer(
        "⚡ <b>WELCOME TO ShadowSnipe</b> 🎯\n\n"
        "<b>PRIVATE ON-CHAIN EXECUTION</b>\n"
        "Fast. Intelligent. Automated.\n\n"
        "Choose an option below to continue.",
        reply_markup=_welcome_keyboard(),
        parse_mode="HTML"
    )


# ── Button: I HAVE A LICENSE ──────────────────────────────────────────────────
@router.callback_query(F.data == "act:have_license")
async def cb_have_license(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ActivationStates.waiting_for_license_key)
    await callback.message.edit_text(
        "🔐 <b>LICENSE ACCESS</b>\n\n"
        "Enter your ShadowSnipe license key to continue.",
        parse_mode="HTML"
    )
    await callback.answer()


# ── License key received ──────────────────────────────────────────────────────
@router.message(ActivationStates.waiting_for_license_key)
async def process_license_key(message: Message, state: FSMContext):
    # Ignore commands while in this state
    if message.text and message.text.startswith("/"):
        return

    key = message.text.strip().upper()
    record = await get_license_key(key)

    if not record:
        await message.answer("❌ Invalid license key. Please try again.")
        return

    if record["is_used"]:
        await message.answer("❌ This license key has already been used.")
        return

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
    if message.text and message.text.startswith("/"):
        return

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
            f"Please try again with a valid transaction signature.",
            parse_mode="HTML"
        )
        return

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
async def cmd_genkey(message: Message, state: FSMContext):
    await state.clear()  # important so it doesn't get stuck in activation state

    admin_ids = getattr(settings, "ADMIN_IDS", []) or []
    # Support both list of ints and comma-separated string
    if isinstance(admin_ids, str):
        admin_ids = [x.strip() for x in admin_ids.split(",") if x.strip()]

    if str(message.from_user.id) not in [str(x) for x in admin_ids]:
        await message.answer("Unauthorized.")
        return

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
