"""
bot/handlers/activation.py
==========================
Guided license + payment activation flow.
Keys are single-use and bound to one Telegram account.
"""

import logging
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from services.license_service import (
    validate_key_for_user,
    mark_key_used,
    is_user_activated,
    activate_user,
    verify_payment_transaction,
    create_license_key,
    activation_network_label,
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


def _network_hint() -> str:
    net = activation_network_label()
    if net == "mainnet":
        return "Solana <b>mainnet</b>"
    return f"Solana <b>{net}</b> (test SOL — not real money)"


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


@router.message(CommandStart())
async def handle_start(message: Message, state: FSMContext):
    try:
        try:
            await state.clear()
        except Exception as e:
            logger.warning(f"state.clear failed on /start: {e}")

        user_id = message.from_user.id

        if await is_user_activated(user_id):
            await message.answer(
                "⚡ <b>SHADOWSNIPE</b>\n"
                "<code>ONLINE  //  SOLANA</code>\n\n"
                "Your license is active.\n"
                "Select a module below.",
                reply_markup=build_main_menu(),
                parse_mode="HTML",
            )
            return

        await message.answer(
            WELCOME_TEXT,
            reply_markup=_welcome_keyboard(),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.exception(f"/start failed for user={message.from_user.id}: {e}")
        try:
            await message.answer(
                "⚡ <b>ShadowSnipe</b> is online.\n\n"
                "Something went wrong loading your session — try /start again.",
                parse_mode="HTML",
            )
        except Exception:
            pass


@router.callback_query(F.data == "act:view_plan")
async def cb_view_plan(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ActivationStates.waiting_for_referral_code)
    await callback.message.edit_text(
        REFERRAL_TEXT,
        reply_markup=_referral_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "act:skip_plans")
async def cb_skip_plans(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        PLANS_TEXT,
        reply_markup=_plans_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "act:back_start")
async def cb_back_start(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        WELCOME_TEXT,
        reply_markup=_welcome_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


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
    await state.set_state(ActivationStates.waiting_for_license_key)
    await callback.message.edit_text(
        f"✅ <b>Plan selected:</b> {label}\n\n"
        "🔐 <b>LICENSE ACCESS</b>\n\n"
        "Enter your ShadowSnipe license key to continue.\n\n"
        "<i>Each key works for one Telegram account only.</i>",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "act:have_license")
async def cb_have_license(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ActivationStates.waiting_for_license_key)
    await callback.message.edit_text(
        "🔐 <b>LICENSE ACCESS</b>\n\n"
        "Enter your ShadowSnipe license key to continue.\n\n"
        "<i>Each key works for one Telegram account only.</i>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(ActivationStates.waiting_for_referral_code)
async def process_referral_code(message: Message, state: FSMContext):
    if message.text and message.text.startswith("/"):
        return

    code = (message.text or "").strip()
    if code:
        await state.update_data(referral_code=code)
        await message.answer(
            f"✅ Referral code <code>{code}</code> noted.\n\nShowing plans…",
            parse_mode="HTML",
        )

    await state.clear()
    await message.answer(
        PLANS_TEXT,
        reply_markup=_plans_keyboard(),
        parse_mode="HTML",
    )


@router.message(ActivationStates.waiting_for_license_key)
async def process_license_key(message: Message, state: FSMContext):
    if message.text and message.text.startswith("/"):
        return

    key = (message.text or "").strip().upper()
    user_id = message.from_user.id

    check = await validate_key_for_user(key, user_id)
    if not check["ok"]:
        await message.answer(f"❌ {check['error']}")
        return

    await state.update_data(license_key=key)
    await state.set_state(ActivationStates.waiting_for_payment_signature)

    wallet = _activation_wallet()
    amount = getattr(settings, "ACTIVATION_AMOUNT_SOL", 1.0)
    network = activation_network_label()

    await message.answer(
        f"✅ <b>License key accepted</b>\n"
        f"<i>This key will be locked to your Telegram account after payment.</i>\n\n"
        f"Network: {_network_hint()}\n"
        f"Activation fee: <b>{amount} SOL</b>\n\n"
        f"Send exactly <b>{amount} SOL</b> to:\n"
        f"<code>{wallet}</code>\n\n"
        f"After sending, reply with the <b>transaction signature</b>.\n"
        f"<i>Use the {network} cluster when checking the explorer.</i>",
        parse_mode="HTML",
    )


@router.message(ActivationStates.waiting_for_payment_signature)
async def process_payment_signature(message: Message, state: FSMContext):
    if message.text and message.text.startswith("/"):
        return

    signature = (message.text or "").strip()
    data = await state.get_data()
    license_key = data.get("license_key")
    user_id = message.from_user.id

    if not license_key:
        await message.answer("Session expired. Please /start again.")
        await state.clear()
        return

    check = await validate_key_for_user(license_key, user_id)
    if not check["ok"]:
        await message.answer(f"❌ {check['error']}\n\nUse /start to begin again.")
        await state.clear()
        return

    network = activation_network_label()
    await message.answer(f"⏳ Checking the transaction on Solana <b>{network}</b>…", parse_mode="HTML")

    result = await verify_payment_transaction(signature)

    if not result["valid"]:
        await message.answer(
            f"❌ Payment verification failed.\n\n"
            f"<code>{result.get('error')}</code>\n\n"
            f"Make sure you paid on <b>{network}</b> and paste the correct signature.",
            parse_mode="HTML",
        )
        return

    bound = await mark_key_used(license_key, user_id)
    if not bound:
        await message.answer(
            "❌ This license key was just claimed by another account. "
            "Contact admin for a new key."
        )
        await state.clear()
        return

    await activate_user(user_id, license_key, signature)
    await state.clear()

    await message.answer(
        "✅ <b>ACTIVATION SUCCESSFUL!</b>\n\n"
        "✅ License verified\n"
        "✅ Payment confirmed\n"
        "✅ Key locked to your Telegram account\n\n"
        "Your bot access is now enabled.\n\n"
        "Use /wallet to open Wallet Manager.",
        parse_mode="HTML",
    )


@router.message(Command("genkey"))
async def cmd_genkey(message: Message, state: FSMContext):
    """
    /genkey              — open key (first account to pay binds it)
    /genkey <telegram_id> — key reserved for that Telegram user only
    """
    await state.clear()

    admin_ids = getattr(settings, "ADMIN_IDS", []) or []
    if isinstance(admin_ids, str):
        admin_ids = [x.strip() for x in admin_ids.split(",") if x.strip()]

    if str(message.from_user.id) not in [str(x) for x in admin_ids]:
        await message.answer("Unauthorized.")
        return

    parts = (message.text or "").split()
    assigned_to = None
    if len(parts) >= 2 and parts[1].isdigit():
        assigned_to = int(parts[1])

    try:
        key = await create_license_key(message.from_user.id, assigned_to=assigned_to)
        if assigned_to:
            note = f"Reserved for Telegram ID <code>{assigned_to}</code> only."
        else:
            note = "Open key — first account that completes payment locks it permanently."
        await message.answer(
            f"🔑 <b>New License Key:</b>\n\n"
            f"<code>{key}</code>\n\n"
            f"{note}\n\n"
            f"Share this key with the user.",
            parse_mode="HTML",
        )
    except Exception as e:
        await message.answer(f"Failed to generate key: {e}")
