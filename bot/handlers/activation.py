"""
bot/handlers/activation.py
==========================
Guided license + payment activation flow
+ Access Plan / referral / pricing screens
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
    waiting_for_referral_code = State()


def _activation_wallet() -> str:
    return getattr(settings, "ACTIVATION_WALLET", "NOT_CONFIGURED")


# ── Keyboards ─────────────────────────────────────────────────────────────────

def _welcome_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="☠️  VIEW ACCESS PLAN", callback_data="act:view_plan")],
        [InlineKeyboardButton(text="🔑  I HAVE A LICENSE", callback_data="act:have_license")],
    ])


def _referral_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️▶️  SKIP — VIEW PLANS", callback_data="act:skip_plans")],
        [InlineKeyboardButton(text="◀️  BACK", callback_data="act:back_start")],
    ])


def _plans_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎  1 MONTH — 9.25 SOL", callback_data="act:plan:1m")],
        [InlineKeyboardButton(text="⚡  2 MONTHS — 20.25 SOL", callback_data="act:plan:2m")],
        [InlineKeyboardButton(text="🔥  3 MONTHS — 30.25 SOL", callback_data="act:plan:3m")],
        [InlineKeyboardButton(text="👑  1 YEAR — 100.25 SOL", callback_data="act:plan:1y")],
        [InlineKeyboardButton(text="☠️  MASTER — 1000.25 SOL", callback_data="act:plan:master")],
        [InlineKeyboardButton(text="🔐  CONTINUE TO LICENSE", callback_data="act:have_license")],
        [InlineKeyboardButton(text="◀️  BACK", callback_data="act:back_start")],
    ])


# ── Text content ──────────────────────────────────────────────────────────────

WELCOME_TEXT = (
    "⚡ <b>WELCOME TO ShadowSnipe</b> 🎯\n\n"
    "<b>PRIVATE ON-CHAIN EXECUTION</b>\n"
    "Fast. Intelligent. Automated.\n\n"
    "Choose an option below to continue."
)

REFERRAL_TEXT = (
    "☠️ <b>SHADOW_SNIPE REFERRAL CODE</b>\n\n"
    "Enter your referral code to unlock its subscription offer.\n\n"
    "If you have a code, enter it below. Otherwise, skip to view the regular plans."
)

PLANS_TEXT = (
    "☠️ <b>SHADOW_SNIPE ACCESS PLAN</b>\n\n"
    "Regular subscription pricing.\n\n"
    "💎 <b>24/7 DAILY SCAN & GEM HUNTING AI ADVANCED SYSTEM</b>\n\n"
    "🎯 <b>AUTOMATED MULTI-WALLET SNIPE BOT</b>\n"
    "License key with buy & sell execution.\n\n"
    "⚡ <b>REAL-TIME DATA</b>\n"
    "Live price, MC, real volume & liquidity.\n\n"
    "📢 <b>EARLY TOKEN CALLS</b>\n"
    "Track ATH and profit live on the bot.\n\n"
    "🤖 <b>AI AUTOMATED MEMECOIN SCANNER</b>\n"
    "Advanced automated market scanning.\n\n"
    "🌐 <b>SUPPORTED ECOSYSTEMS</b>\n"
    "Solana • EVM • Base • Robinhood • and more.\n\n"
    "☠️ <b>ALL PLANS INCLUDE ALL UPDATED SHADOW_SNIPE FEATURES</b>\n\n"
    "👛 <b>INTERNAL SNIPE WALLETS: 10</b>\n"
    "❗️ <b>STANDARD 1-MONTH PLAN: 9.25 SOL</b> before referral discounts\n\n"
    "Select your subscription plan:"
)


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

    await message.answer(
        WELCOME_TEXT,
        reply_markup=_welcome_keyboard(),
        parse_mode="HTML"
    )


# ── VIEW ACCESS PLAN → Referral screen ────────────────────────────────────────
@router.callback_query(F.data == "act:view_plan")
async def cb_view_plan(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ActivationStates.waiting_for_referral_code)
    await callback.message.edit_text(
        REFERRAL_TEXT,
        reply_markup=_referral_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


# ── SKIP — VIEW PLANS → Pricing screen ────────────────────────────────────────
@router.callback_query(F.data == "act:skip_plans")
async def cb_skip_plans(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        PLANS_TEXT,
        reply_markup=_plans_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


# ── BACK → Start (both options) ───────────────────────────────────────────────
@router.callback_query(F.data == "act:back_start")
async def cb_back_start(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        WELCOME_TEXT,
        reply_markup=_welcome_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


# ── Plan selected (show info, then route to license) ──────────────────────────
@router.callback_query(F.data.startswith("act:plan:"))
async def cb_plan_selected(callback: CallbackQuery, state: FSMContext):
    plan = callback.data.split(":")[-1]
    labels = {
        "1m": "1 MONTH — 9.25 SOL",
        "2m": "2 MONTHS — 20.25 SOL",
        "3m": "3 MONTHS — 30.25 SOL",
        "1y": "1 YEAR — 100.25 SOL",
        "master": "MASTER — 1000.25 SOL",
    }
    label = labels.get(plan, plan)
    await callback.answer(f"Selected: {label}", show_alert=False)
    # Move user into license entry so they can activate
    await state.set_state(ActivationStates.waiting_for_license_key)
    await callback.message.edit_text(
        f"✅ <b>Plan selected:</b> {label}\n\n"
        "🔐 <b>LICENSE ACCESS</b>\n\n"
        "Enter your ShadowSnipe license key to continue.\n\n"
        "<i>Contact admin if you need a key for this plan.</i>",
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


# ── Referral code typed (optional — just acknowledge and show plans) ──────────
@router.message(ActivationStates.waiting_for_referral_code)
async def process_referral_code(message: Message, state: FSMContext):
    if message.text and message.text.startswith("/"):
        return

    code = (message.text or "").strip()
    if code:
        await state.update_data(referral_code=code)
        await message.answer(
            f"✅ Referral code <code>{code}</code> noted.\n\nShowing plans…",
            parse_mode="HTML"
        )

    await state.clear()
    await message.answer(
        PLANS_TEXT,
        reply_markup=_plans_keyboard(),
        parse_mode="HTML"
    )


# ── License key received ──────────────────────────────────────────────────────
@router.message(ActivationStates.waiting_for_license_key)
async def process_license_key(message: Message, state: FSMContext):
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
        "✅ Payment confirmed\n"
        "✅ License activated\n\n"
        "Your bot access is now enabled.\n\n"
        "Use /wallet to open Wallet Manager.",
        parse_mode="HTML"
    )


# ── Admin: Generate license keys ──────────────────────────────────────────────
@router.message(Command("genkey"))
async def cmd_genkey(message: Message, state: FSMContext):
    await state.clear()

    admin_ids = getattr(settings, "ADMIN_IDS", []) or []
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
