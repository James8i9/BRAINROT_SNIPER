"""
bot/handlers/callbacks.py
=========================
Handles main-menu inline callbacks (help, onboarding, back).
"""

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext

from bot.keyboards.main_menu import build_main_menu, build_back_button
from utils.config import settings

router = Router()


# ── Help / FAQ ─────────────────────────────────────────────────────────────────

_FAQ: dict[str, tuple[str, str]] = {
    "wallet": (
        "💼 Wallet & Funding",
        (
            "💼 <b>Wallet & Funding — FAQ</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>Where is my bot wallet?</b>\n"
            "Tap <b>Wallet</b> in the main menu. The bot generates a unique Solana wallet for you — "
            "this is the address you deposit SOL into for trading.\n\n"
            "<b>My Phantom wallet has SOL but trades are skipped?</b>\n"
            "Your Phantom wallet and the bot wallet are separate. The bot can only spend SOL "
            "that lives in <i>its own</i> wallet. Copy the bot wallet address and send SOL there.\n\n"
            "<b>How much SOL do I need?</b>\n"
            "• Auto-buy / Copy Trade: at least your trade size + 0.003 SOL for fees\n"
            "• Recommended minimum: <b>0.1 SOL</b> to run comfortably\n\n"
            "<b>How do I withdraw?</b>\n"
            "Withdrawal is handled through the Wallet screen. "
            "Never share your bot wallet private key.\n\n"
            "<b>Is my private key safe?</b>\n"
            "Yes — private keys are AES-256 encrypted before storage. "
            "The bot never logs or transmits them."
        ),
    ),
    "autobuy": (
        "🤖 Auto-Buy",
        (
            "🤖 <b>Auto-Buy — FAQ</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>What does Auto-Buy do?</b>\n"
            "It monitors the pump.fun live feed and automatically buys new tokens that pass your "
            "score threshold, within your configured buy size and hourly limits.\n\n"
            "<b>Why is it skipping every token?</b>\n"
            "The most common reasons:\n"
            "• <b>Low balance</b> — fund your bot wallet\n"
            "• <b>Score threshold too high</b> — lower it in Settings\n"
            "• <b>Max buys/hour reached</b> — increase the limit or wait\n"
            "• <b>Kill switch ON</b> — toggle it off in Settings\n\n"
            "<b>What does the score mean?</b>\n"
            "Tokens are scored 0–100 based on buy pressure, volume, bonding curve fill, "
            "and momentum. Set your threshold to 30–50 for a balanced filter.\n\n"
            "<b>What is the Liquidity Sniper mode?</b>\n"
            "Triggers on tokens where the initial buy exceeds your set SOL threshold — "
            "catching large early buyers as a signal.\n\n"
            "<b>Why does it show liq=0?</b>\n"
            "New pump.fun tokens have no traditional liquidity pool yet — they trade on a bonding "
            "curve. liq=0 is expected and not an error."
        ),
    ),
    "copytrade": (
        "📋 Copy Trade",
        (
            "📋 <b>Copy Trade — FAQ</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>How does Copy Trade work?</b>\n"
            "Add a wallet address to track. Every 15 seconds the bot checks for new swaps from "
            "that wallet and mirrors them automatically using your bot wallet.\n\n"
            "<b>Why isn't it copying trades?</b>\n"
            "• The leader wallet hasn't traded since the bot started — it only copies <i>new</i> trades\n"
            "• Copy Buys or Copy Sells may be toggled off in Settings\n"
            "• Your bot wallet may have insufficient SOL\n"
            "• Kill switch may be ON\n\n"
            "<b>Why did it skip a SELL?</b>\n"
            "The bot only copies sells for tokens it previously bought through copy trade. "
            "If the leader sells something you never bought, it skips it — this is correct.\n\n"
            "<b>My copy size is 0.001 SOL — why so small?</b>\n"
            "That is the minimum floor. Go to <b>Copy Trade → Settings → Fixed Amount</b> and "
            "raise it to 0.02–0.05 SOL for meaningful trades.\n\n"
            "<b>Which wallet should I copy?</b>\n"
            "Look for wallets with consistent profitable trades on-chain. "
            "Paste the Solana address into Copy Trade → Add Wallet."
        ),
    ),
    "general": (
        "❓ General",
        (
            "❓ <b>General FAQ</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "<b>Why does the bot restart / get stuck?</b>\n"
            "On Windows, stopping the bot sometimes leaves a background Python process. "
            "Run <code>taskkill /F /IM python.exe</code> in your terminal, then restart.\n\n"
            "<b>Trades are failing with 'Jupiter unavailable'?</b>\n"
            "Jupiter's API may be temporarily unreachable from your machine. "
            "The bot automatically retries with a fallback endpoint. "
            "Running on a Linux VPS eliminates this issue entirely.\n\n"
            "<b>How do I check my positions?</b>\n"
            "• Auto-Buy positions: Sniper → Positions\n"
            "• Copy Trade history: Copy Trade → History\n\n"
            "<b>Need more help?</b>\n"
            "Contact the admin or check your bot's log output for detailed error messages."
        ),
    ),
}


def _build_help_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, (label, _) in _FAQ.items():
        builder.row(InlineKeyboardButton(text=label, callback_data=f"help:{key}"))
    builder.row(InlineKeyboardButton(text="⬅️ Back to Menu", callback_data="menu:back"))
    return builder.as_markup()


def _build_help_back() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ Back to Help", callback_data="menu:help"))
    return builder.as_markup()


@router.callback_query(F.data == "menu:help")
async def cb_help(callback: CallbackQuery) -> None:
    text = (
        "❓ <b>Help & FAQ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Select a topic below to get answers:"
    )
    await callback.message.edit_text(text, reply_markup=_build_help_menu(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("help:"))
async def cb_help_topic(callback: CallbackQuery) -> None:
    key = callback.data.split(":", 1)[1]
    if key not in _FAQ:
        await callback.answer("Topic not found.", show_alert=True)
        return
    _, text = _FAQ[key]
    await callback.message.edit_text(
        text,
        reply_markup=_build_help_back(),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    await callback.answer()


# ── New Users Onboarding ───────────────────────────────────────────────────────
_NEW_USERS_TEXT = (
    "🆕 <b>WELCOME TO ShadowSnipe</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "<code>┌─ WHAT IS THIS BOT? ──────────┐\n"
    "│  Automated Solana trading     │\n"
    "│  Copy trade · Auto-buy        │\n"
    "│  Multi-wallet sniping         │\n"
    "└──────────────────────────────┘</code>\n\n"
    "This bot trades on your behalf on Solana — monitoring pump.fun, "
    "DexScreener, and on-chain wallets 24/7 so you don't have to.\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "💼 <b>STEP 1 — Fund Your Bot Wallet</b>\n\n"
    "The bot has its own Solana wallet separate from Phantom or any personal wallet.\n\n"
    "1. Tap <b>💼 Wallet</b> in the main menu\n"
    "2. Copy the address shown\n"
    "3. Send SOL there from Phantom or an exchange\n"
    "4. Minimum recommended: <b>0.1 SOL</b>\n\n"
    "<i>The bot can only trade with SOL that is inside its own wallet.</i>\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "🤖 <b>STEP 2 — Pick a Module</b>\n\n"
    "<b>🎯 Sniper Tool (Auto-Buy)</b>\n"
    "Watches the pump.fun live feed and auto-buys new tokens that score above your threshold.\n\n"
    "<b>📋 Copy Trade</b>\n"
    "Add a wallet address to track. The bot mirrors every buy and sell it makes, automatically.\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "⚙️ <b>STEP 3 — Configure Settings</b>\n\n"
    "Each module has its own settings: trade size, score threshold, slippage, kill switch, "
    "max buys per hour, and more. Tap <b>⚙️ Settings</b> inside any module.\n\n"
    "<i>Every feature is unlocked — set it up the way you want.</i>"
)


def _build_new_users_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💼  Go to My Wallet", callback_data="mw:main")
    )
    builder.row(
        InlineKeyboardButton(text="⬅️  Back to Menu", callback_data="menu:back")
    )
    return builder.as_markup()


@router.callback_query(F.data == "menu:new_users")
async def cb_new_users(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        _NEW_USERS_TEXT,
        reply_markup=_build_new_users_keyboard(),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    await callback.answer()


# ── Portfolio Viewer Guide ─────────────────────────────────────────────────────
@router.callback_query(F.data == "menu:portfolio_guide")
async def cb_portfolio_guide(callback: CallbackQuery) -> None:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔑  Go Export My Key Now", callback_data="sniper:wallet_export"))
    builder.row(InlineKeyboardButton(text="⬅️  Back to Menu",         callback_data="menu:back"))

    text = (
        "👁  <b>HOW TO VIEW YOUR TOKEN PORTFOLIO</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Your bot trades from its own Solana wallet. Here's how to see your actual token holdings "
        "inside Phantom while the bot keeps running.\n\n"
        "<b>━━  STEP 1 — EXPORT YOUR BOT WALLET KEY  ━━</b>\n"
        "1. Tap <b>🔑 Go Export My Key Now</b> below (or go to <b>Sniper → Wallet → Export Key</b>)\n"
        "2. The key appears blurred — tap it to reveal, then <b>copy it</b>\n"
        "3. The message auto-deletes in 60 seconds — act quickly\n\n"
        "<b>━━  STEP 2 — IMPORT INTO PHANTOM  ━━</b>\n"
        "1. Open the <b>Phantom</b> app on your phone or browser extension\n"
        "2. Tap your <b>profile icon</b> (top left avatar)\n"
        "3. Tap <b>\"Add / Connect Wallet\"</b>\n"
        "4. Select <b>\"Import Private Key\"</b>\n"
        "5. Give it a name like <i>\"ShadowSnipe BOT\"</i>\n"
        "6. Paste the key you copied → tap <b>Import</b>\n\n"
        "<b>━━  STEP 3 — VIEW YOUR TOKENS  ━━</b>\n"
        "Once imported you will see the wallet balance and all token holdings live.\n"
        "Phantom shows every token the bot has bought — including ones still open.\n\n"
        "⚙️  <b>Enable token display:</b> In Phantom go to <b>Settings → Trusted Apps</b> "
        "and make sure token visibility is on. Some low-cap tokens may need you to tap "
        "<b>\"Manage token list\"</b> and enable unknown tokens.\n\n"
        "<b>━━  STEP 4 — CONNECT TO PUMP.FUN  ━━</b>\n"
        "1. Go to <b>pump.fun</b> in your browser\n"
        "2. Click <b>Connect Wallet</b> (top right)\n"
        "3. Select <b>Phantom</b> and approve the connection\n"
        "4. Click your profile → <b>Portfolio</b> to see every token you hold\n"
        "5. You can manually sell any token directly from here if needed\n\n"
        "<b>━━  IMPORTANT NOTES  ━━</b>\n"
        "⚠️  <b>Never send SOL OUT of the bot wallet</b> while auto-buy is running — "
        "it needs SOL to pay for buys and fees\n"
        "⚠️  <b>Never share your private key</b> with anyone\n"
        "✅  The bot wallet and Phantom share the same wallet — "
        "the bot keeps trading while you watch in Phantom\n"
        "✅  Auto-sells will still execute normally — Phantom is read-only viewing\n\n"
        f"<code>ShadowSnipe  ·  {settings.BRAND_HANDLE}</code>"
    )

    try:
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


# ── Under Construction ─────────────────────────────────────────────────────────
@router.callback_query(F.data.startswith("wip:"))
async def cb_wip(callback: CallbackQuery) -> None:
    await callback.answer(
        "🚧 Under Construction — coming soon!",
        show_alert=True,
    )


# ── Back to Menu ───────────────────────────────────────────────────────────────
@router.callback_query(F.data == "menu:back")
async def cb_back(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await state.clear()
    except Exception:
        pass
    await callback.message.edit_text(
        text=(
            "📋 <b>Main Menu</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Select a module below to get started."
        ),
        reply_markup=build_main_menu(),
        parse_mode="HTML",
    )
    await callback.answer()
