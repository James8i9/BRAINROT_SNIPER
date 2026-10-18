"""
bot/handlers/multi_wallet.py
============================
Multi-Wallet Manager — Fund Wallet + Buy Wallets + Distribute + Withdraw
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
    build_confirm_distribute,
)
from services.multi_wallet_service import (
    import_fund_wallet,
    get_fund_wallet,
    generate_buy_wallets,
    get_buy_wallets,
    list_all_wallets,
    distribute_sol,
    get_keypair_from_wallet,
)
from services.bot_wallet_service import get_sol_balance

logger = logging.getLogger(__name__)
router = Router()


class MultiWalletStates(StatesGroup):
    waiting_for_fund_key = State()
    waiting_for_amount = State()
    waiting_for_withdraw_amount = State()
    waiting_for_withdraw_address = State()


def _short(addr: str) -> str:
    if not addr:
        return "—"
    return f"{addr[:4]}...{addr[-4:]}" if len(addr) > 10 else addr


async def _build_wallet_overview(user_id: int) -> str:
    """Build a clean overview of Fund + Buy wallets with balances."""
    fund = await get_fund_wallet(user_id)
    buys = await get_buy_wallets(user_id)

    lines = ["💼 <b>Multi-Wallet Manager</b>", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━", ""]

    # Fund Wallet
    if fund:
        bal = await get_sol_balance(fund["wallet_address"])
        bal_str = f"{bal:.4f} SOL" if bal is not None else "?.???? SOL"
        lines.append("<b>🏦 Fund Wallet</b>")
        lines.append(f"<code>{fund['wallet_address']}</code>")
        lines.append(f"Balance: <b>{bal_str}</b>")
    else:
        lines.append("<b>🏦 Fund Wallet</b>")
        lines.append("<i>Not imported yet</i>")

    lines.append("")

    # Buy Wallets
    if buys:
        lines.append(f"<b>🛒 Buy Wallets ({len(buys)})</b>")
        for i, w in enumerate(buys, 1):
            bal = await get_sol_balance(w["wallet_address"])
            bal_str = f"{bal:.4f}" if bal is not None else "?"
            lines.append(f"{i}. <code>{_short(w['wallet_address'])}</code>  ·  {bal_str} SOL")
    else:
        lines.append("<b>🛒 Buy Wallets</b>")
        lines.append("<i>None generated yet</i>")

    lines.append("")
    lines.append("Select an action below:")
    return "\n".join(lines)


# ── Main Menu ────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "mw:main")
async def cb_mw_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text = await _build_wallet_overview(callback.from_user.id)
    await callback.message.edit_text(
        text,
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
        "⚠️ Only import a wallet you own.\n"
        "The key will be encrypted at rest.",
        reply_markup=build_back_to_mw(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(MultiWalletStates.waiting_for_fund_key)
async def process_fund_key(message: Message, state: FSMContext) -> None:
    private_key = message.text.strip() if message.text else ""

    try:
        await message.delete()
    except Exception:
        pass

    result = await import_fund_wallet(message.from_user.id, private_key)

    if result.get("success"):
        text = await _build_wallet_overview(message.from_user.id)
        await message.answer(
            f"✅ <b>Fund Wallet imported!</b>\n\n{text}",
            reply_markup=build_multi_wallet_menu(),
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"❌ Failed to import wallet.\n\nError: <code>{result.get('error')}</code>",
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
        await generate_buy_wallets(user_id, count)
        text = await _build_wallet_overview(user_id)
        await callback.message.edit_text(
            f"✅ Generated <b>{count}</b> Buy Wallet(s)\n\n{text}",
            reply_markup=build_multi_wallet_menu(),
            parse_mode="HTML",
        )
    except Exception as e:
        await callback.message.edit_text(
            f"❌ Failed: {e}",
            reply_markup=build_back_to_mw(),
            parse_mode="HTML",
        )
    await callback.answer()


# ── List Wallets (refresh) ────────────────────────────────────────────────────
@router.callback_query(F.data == "mw:list")
async def cb_list_wallets(callback: CallbackQuery) -> None:
    text = await _build_wallet_overview(callback.from_user.id)
    await callback.message.edit_text(
        text,
        reply_markup=build_multi_wallet_menu(),
        parse_mode="HTML",
    )
    await callback.answer("Refreshed")


# ── Distribute SOL ────────────────────────────────────────────────────────────
@router.callback_query(F.data == "mw:distribute")
async def cb_distribute(callback: CallbackQuery, state: FSMContext) -> None:
    user_id = callback.from_user.id
    fund = await get_fund_wallet(user_id)
    buys = await get_buy_wallets(user_id)

    if not fund:
        await callback.message.edit_text(
            "❌ No Fund Wallet found.\nImport one first.",
            reply_markup=build_back_to_mw(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    if not buys:
        await callback.message.edit_text(
            "❌ No Buy Wallets found.\nGenerate some first.",
            reply_markup=build_back_to_mw(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    await state.set_state(MultiWalletStates.waiting_for_amount)
    await callback.message.edit_text(
        f"💸 <b>Distribute SOL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Fund: <code>{_short(fund['wallet_address'])}</code>\n"
        f"Buy Wallets: <b>{len(buys)}</b>\n\n"
        f"Enter the amount of SOL to send to <b>each</b> Buy Wallet:\n"
        f"(Example: <code>0.05</code>)",
        reply_markup=build_back_to_mw(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(MultiWalletStates.waiting_for_amount)
async def process_amount(message: Message, state: FSMContext) -> None:
    try:
        amount = float(message.text.strip())
        if amount <= 0:
            raise ValueError()
    except Exception:
        await message.answer("❌ Invalid amount. Send a number like <code>0.05</code>", parse_mode="HTML")
        return

    buys = await get_buy_wallets(message.from_user.id)
    total = amount * len(buys)

    await state.clear()
    await message.answer(
        f"⚠️ <b>Confirm Distribution</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"• <b>{amount} SOL</b> → each of <b>{len(buys)}</b> wallets\n"
        f"• Total: <b>{total:.4f} SOL</b>\n\n"
        f"This cannot be undone.",
        reply_markup=build_confirm_distribute(amount),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("mw:confirm_dist:"))
async def cb_confirm_distribute(callback: CallbackQuery) -> None:
    amount = float(callback.data.split(":")[-1])
    user_id = callback.from_user.id

    await callback.message.edit_text("⏳ Sending transaction...\nPlease wait.", parse_mode="HTML")

    result = await distribute_sol(user_id, amount)

    if result["success"]:
        text = (
            f"✅ <b>Distribution Successful</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Sent <b>{result['amount_each']} SOL</b> to <b>{result['count']}</b> wallets\n"
            f"Total: <b>{result['total_sent']:.4f} SOL</b>\n\n"
            f"<code>{result['signature']}</code>\n"
            f"<a href='https://solscan.io/tx/{result['signature']}'>View on Solscan</a>"
        )
    else:
        text = f"❌ <b>Failed</b>\n\n<code>{result.get('error')}</code>"

    overview = await _build_wallet_overview(user_id)
    await callback.message.edit_text(
        f"{text}\n\n{overview}",
        reply_markup=build_multi_wallet_menu(),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    await callback.answer()
