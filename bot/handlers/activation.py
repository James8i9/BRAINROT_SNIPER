"""
bot/handlers/activation.py
==========================
Guided subscription + license + payment activation flow.

Flow A — buy a plan:
  select plan → pay plan amount → auto key → pay 1 SOL activate

Flow B — already have a key:
  enter key → pay 1 SOL activate

Keys are single-use and bound to one Telegram account.
Payment signatures are single-use (replay blocked).
"""

import logging
from aiogram import Router, F
from aiogram.filters import CommandStart
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

PLANS = {
    "1m": {"title": "1 MONTH PLAN", "amount": 9.25, "days": 30, "button": "💎  1 MONTH — 9.25 SOL"},
    "2m": {"title": "2 MONTHS PLAN", "amount": 20.25, "days": 60, "button": "⚡  2 MONTHS — 20.25 SOL"},
    "3m": {"title": "3 MONTHS PLAN", "amount": 30.25, "days": 90, "button": "🔥  3 MONTHS — 30.25 SOL"},
    "1y": {"title": "1 YEAR PLAN", "amount": 100.25, "days": 365, "button": "👑  1 YEAR — 100.25 SOL"},
    "master": {"title": "MASTER PLAN", "amount": 1000.25, "days": None, "button": "☠️  MASTER — 1000.25 SOL"},
}


class ActivationStates(StatesGroup):
    waiting_for_referral_code = State()
    waiting_for_plan_payment = State()
    waiting_for_license_key = State()
    waiting_for_payment_signature = State()


def _activation_wallet() -> str:
    return getattr(settings, "ACTIVATION_WALLET", "") or "NOT_CONFIGURED"


def _activation_fee() -> float:
    return float(getattr(settings, "ACTIVATION_AMOUNT_SOL", 1.0))


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
    rows = [[InlineKeyboardButton(text=p["button"], callback_data=f"act:plan:{pid}")] for pid, p in PLANS.items()]
    rows.append([InlineKeyboardButton(text="🔐  CONTINUE TO LICENSE", callback_data="act:have_license")])
    rows.append([InlineKeyboardButton(text="◀️  BACK", callback_data="act:back_start")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _plan_pay_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️  BACK TO PLANS", callback_data="act:skip_plans")],
    ])


def _subscription_text(plan_id: str) -> str:
    plan = PLANS[plan_id]
    wallet = _activation_wallet()
    network = activation_network_label()
    days_line = f"⏱  <b>{plan['days']} days</b>\n" if plan["days"] is not None else "⏱  <b>Lifetime access</b>\n"
    return (
        f"💎 <b>SHADOWSNIPE SUBSCRIPTION</b>\n\n"
        f"<b>{plan['title']}</b>\n"
        f"💵  <b>{plan['amount']} SOL</b>\n"
        f"{days_line}\n"
        f"Network: {_network_hint()}\n\n"
        f"Send exactly <b>{plan['amount']} SOL</b> to:\n"
        f"<code>{wallet}</code>\n\n"
        f"After sending the payment, reply with the <b>transaction signature</b>.\n\n"
        f"Once verified, ShadowSnipe will automatically generate your license key. "
        f"You must then activate that key with the existing "
        f"<b>{_activation_fee()} SOL</b> activation payment.\n\n"
        f"<i>Use the {network} cluster when checking the explorer.</i>"
    )


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
                "Your license is active.\n\n"
                "Next steps:\n"
                "1. Import your <b>Fund Wallet</b>\n"
                "2. Generate <b>Buy Wallets</b>\n"
                "3. <b>Distribute SOL</b> from Fund → Buy wallets\n\n"
                "Open Wallet to continue:",
                reply_markup=build_main_menu(),
                parse_mode="HTML",
            )
            return

        await message.answer(WELCOME_TEXT, reply_markup=_welcome_keyboard(), parse_mode="HTML")
    except Exception as e:
        logger.exception(f"/start failed for user={message.from_user.id}: {e}")
        try:
            await message.answer(
                "⚡ <b>ShadowSnipe</b> is online.\n\nSomething went wrong — try /start again.",
                parse_mode="HTML",
            )
        except Exception:
            pass


@router.callback_query(F.data == "act:view_plan")
async def cb_view_plan(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ActivationStates.waiting_for_referral_code)
    await callback.message.edit_text(REFERRAL_TEXT, reply_markup=_referral_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "act:skip_plans")
async def cb_skip_plans(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(PLANS_TEXT, reply_markup=_plans_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "act:back_start")
async def cb_back_start(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(WELCOME_TEXT, reply_markup=_welcome_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("act:plan:"))
async def cb_plan_selected(callback: CallbackQuery, state: FSMContext):
    plan_id = callback.data.split(":")[-1]
    if plan_id not in PLANS:
        await callback.answer("Unknown plan.", show_alert=True)
        return

    plan = PLANS[plan_id]
    await state.set_state(ActivationStates.waiting_for_plan_payment)
    await state.update_data(plan_id=plan_id, plan_amount=plan["amount"], plan_title=plan["title"])
    await callback.message.edit_text(_subscription_text(plan_id), reply_markup=_plan_pay_keyboard(), parse_mode="HTML")
    await callback.answer()


@router.message(ActivationStates.waiting_for_plan_payment)
async def process_plan_payment(message: Message, state: FSMContext):
    if message.text and message.text.startswith("/"):
        return

    signature = (message.text or "").strip()
    data = await state.get_data()
    plan_id = data.get("plan_id")
    plan_amount = data.get("plan_amount")
    plan_title = data.get("plan_title", "PLAN")
    user_id = message.from_user.id

    if not plan_id or plan_amount is None:
        await message.answer("Session expired. Please /start again.")
        await state.clear()
        return

    if await is_user_activated(user_id):
        await message.answer("This Telegram account is already activated.")
        await state.clear()
        return

    network = activation_network_label()
    await message.answer(
        f"⏳ Checking your <b>{plan_title}</b> payment on Solana <b>{network}</b>…",
        parse_mode="HTML",
    )

    result = await verify_payment_transaction(
        signature, required_sol=float(plan_amount),
        user_id=user_id, purpose="plan",
    )

    if not result["valid"]:
        await message.answer(
            f"❌ Payment verification failed.\n\n"
            f"<code>{result.get('error')}</code>\n\n"
            f"Send exactly <b>{plan_amount} SOL</b> on <b>{network}</b> "
            f"and paste the correct signature.",
            parse_mode="HTML",
        )
        return

    try:
        key = await create_license_key(created_by=user_id, assigned_to=user_id)
    except Exception as e:
        logger.exception(f"Auto key gen failed for user={user_id}: {e}")
        await message.answer("Payment verified, but license key generation failed. Contact admin.")
        return

    fee = _activation_fee()
    wallet = _activation_wallet()

    await state.update_data(license_key=key, plan_payment_sig=signature)
    await state.set_state(ActivationStates.waiting_for_payment_signature)

    await message.answer(
        f"✅ <b>Subscription payment verified!</b>\n"
        f"Received ~{result.get('received_sol', plan_amount):.4f} SOL on {network}.\n\n"
        f"🔑 <b>Your license key</b> (locked to this Telegram account):\n"
        f"<code>{key}</code>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔐 <b>FINAL STEP — ACTIVATION FEE</b>\n\n"
        f"Network: {_network_hint()}\n"
        f"Send exactly <b>{fee} SOL</b> to:\n"
        f"<code>{wallet}</code>\n\n"
        f"After sending, reply with the <b>transaction signature</b> to finish activation.",
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
        await message.answer(f"✅ Referral code <code>{code}</code> noted.\n\nShowing plans…", parse_mode="HTML")

    await state.clear()
    await message.answer(PLANS_TEXT, reply_markup=_plans_keyboard(), parse_mode="HTML")


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
    fee = _activation_fee()
    network = activation_network_label()

    await message.answer(
        f"✅ <b>License key accepted</b>\n"
        f"<i>This key will be locked to your Telegram account after payment.</i>\n\n"
        f"Network: {_network_hint()}\n"
        f"Activation fee: <b>{fee} SOL</b>\n\n"
        f"Send exactly <b>{fee} SOL</b> to:\n"
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
    fee = _activation_fee()
    await message.answer(
        f"⏳ Checking the <b>{fee} SOL</b> activation payment on Solana <b>{network}</b>…",
        parse_mode="HTML",
    )

    result = await verify_payment_transaction(
        signature, required_sol=fee,
        user_id=user_id, purpose="activation",
    )

    if not result["valid"]:
        await message.answer(
            f"❌ Payment verification failed.\n\n"
            f"<code>{result.get('error')}</code>\n\n"
            f"Make sure you paid <b>{fee} SOL</b> on <b>{network}</b> "
            f"and paste the correct signature.",
            parse_mode="HTML",
        )
        return

    bound = await mark_key_used(license_key, user_id)
    if not bound:
        await message.answer(
            "❌ This license key was just claimed by another account. Contact admin for a new key."
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
        "Next: /wallet → import Fund Wallet → generate Buy Wallets → Distribute SOL.",
        parse_mode="HTML",
    )
