"""
bot/handlers/multi_wallet.py
============================
Multi-Wallet Manager handlers (Fund Wallet + Buy Wallets).
"""

import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.keyboards.multi_wallet_menu import (
    build_multi_wallet_menu,
    build_generate_count_menu,
    build_back_to_mw,
)
from services.multi_wallet_service import (
    import_fund_wallet,
    get_fund_wallet,
    generate_buy_wallets,
    get_buy_wallets,
    list_all_wallets,
)

logger = logging.getLogger(__name__)
router = Router()


class MultiWalletStates(StatesGroup):
    waiting_for_fund_key = State()


def _short(addr: str) -> str:
    if not addr:
        return "—"
    return addr[:6] + "..." + addr[-4:] if len(addr) > 10 else addr


# ── Main Menu ────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "mw:main")
async def cb_mw_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "💼 <b>Multi-Wallet Manager</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "• <b>Fund Wallet</b> — your main capital wallet (import private key)\n"
        "• <b>Buy Wallets</b> — wallets the bot will use for sniping\n\n"
        "Select an option below:",
        reply_markup=build_multi_wallet_menu(),
        parse_mode="HTML",
    )
    await callback.answer()


# ── Import Fund Wallet ────────────────────────────────────────────────────────
@router.callback_query(F.data == "mw:import_fund")
async def cb_import_fund(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(MultiWalletStates.waiting_for_fund_key)
    await callback.message.edit_text(
        "📥 <b>Import Fund Wallet</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Send the <b>private key</b> of the wallet you want to use as Fund Wallet.\n\n"
        "Accepted formats:\n"
        "• Base58 private key\n"
        "• 64-byte hex\n"
        "• JSON array\n\n"
        "⚠️ <b>Only import a wallet you own.</b>\n"
        "The key will be encrypted and the message will be deleted if possible.",
        reply_markup=build_back_to_mw(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(MultiWalletStates.waiting_for_fund_key)
async def process_fund_key(message: Message, state: FSMContext) -> None:
    private_key = message.text.strip() if message.text else ""

    # Try to delete the message containing the private key
    try:
        await message.delete()
    except Exception:
        pass

    result = await import_fund_wallet(message.from_user.id, private_key)

    if result.get("success"):
        addr = result["address"]
        await message.answer(
            f"✅ <b>Fund Wallet imported successfully!</b>\n\n"
            f"Address: <code>{addr}</code>\n\n"
            f"You can now generate Buy Wallets and distribute SOL to them.",
            reply_markup=build_multi_wallet_menu(),
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"❌ Failed to import wallet.\n\n"
            f"Error: <code>{result.get('error', 'Unknown error')}</code>\n\n"
            f"Please try again with a valid private key.",
            reply_markup=build_back_to_mw(),
            parse_mode="HTML",
        )

    await state.clear()


# ── Generate Buy Wallets ──────────────────────────────────────────────────────
@router.callback_query(F.data == "mw:generate")
async def cb_generate(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "⚙️ <b>Generate Buy Wallets</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "How many Buy Wallets do you want to create?",
        reply_markup=build_generate_count_menu(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mw:gen:"))
async def cb_generate_count(callback: CallbackQuery) -> None:
    count = int(callback.data.split(":")[-1])
    user_id = callback.from_user.id

    try:
        created = await generate_buy_wallets(user_id, count)
        lines = [f"• <code>{w['address']}</code>" for w in created]
        text = (
            f"✅ <b>Generated {count} Buy Wallet(s)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            + "\n".join(lines)
        )
    except Exception as e:
        text = f"❌ Failed to generate wallets: {e}"

    await callback.message.edit_text(
        text,
        reply_markup=build_multi_wallet_menu(),
        parse_mode="HTML",
    )
    await callback.answer()


# ── List Wallets ──────────────────────────────────────────────────────────────
@router.callback_query(F.data == "mw:list")
async def cb_list_wallets(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    wallets = await list_all_wallets(user_id)

    if not wallets:
        text = (
            "📋 <b>My Wallets</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "No wallets yet.\n\n"
            "Import a Fund Wallet or generate Buy Wallets first."
        )
    else:
        fund = [w for w in wallets if w["wallet_type"] == "fund"]
        buys = [w for w in wallets if w["wallet_type"] == "buy"]

        lines = []
        if fund:
            lines.append("<b>🏦 Fund Wallet</b>")
            for w in fund:
                lines.append(f"• <code>{w['wallet_address']}</code>")
            lines.append("")

        if buys:
            lines.append(f"<b>🛒 Buy Wallets ({len(buys)})</b>")
            for i, w in enumerate(buys, 1):
                lines.append(f"{i}. <code>{w['wallet_address']}</code>")

        text = (
            "📋 <b>My Wallets</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            + "\n".join(lines)
        )

    await callback.message.edit_text(
        text,
        reply_markup=build_multi_wallet_menu(),
        parse_mode="HTML",
    )
    await callback.answer()
