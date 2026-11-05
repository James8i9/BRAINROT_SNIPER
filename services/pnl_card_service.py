"""
services/pnl_card_service.py
==============================
Generate BLOCK_BOT-style PnL share cards and aggregate trade stats.

Card fields:
  symbol, buy_in_sol, sold_sol, hold_sol, roi_pct, profit_sol, profit_usd, wallets
"""

from __future__ import annotations

import io
import logging
import math
from dataclasses import dataclass
from typing import Optional

import aiohttp
from database.sqlite_db import get_db
from utils.config import settings

logger = logging.getLogger(__name__)


@dataclass
class PnlStats:
    token_address: str
    symbol: str
    buy_in_sol: float
    sold_sol: float
    hold_sol: float
    wallets: int
    roi_pct: float
    profit_sol: float
    profit_usd: float
    sol_price_usd: float


async def fetch_sol_price_usd() -> float:
    """Best-effort SOL/USD. Falls back to 0 if offline."""
    urls = [
        "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd",
        "https://price.jup.ag/v6/price?ids=SOL",
    ]
    try:
        async with aiohttp.ClientSession() as session:
            # CoinGecko
            try:
                async with session.get(urls[0], timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        px = float((data.get("solana") or {}).get("usd") or 0)
                        if px > 0:
                            return px
            except Exception:
                pass
            # Jupiter
            try:
                async with session.get(urls[1], timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        px = float(((data.get("data") or {}).get("SOL") or {}).get("price") or 0)
                        if px > 0:
                            return px
            except Exception:
                pass
    except Exception as e:
        logger.warning("SOL price fetch failed: %s", e)
    return 0.0


async def get_token_symbol(token_address: str, fallback: str = "TOKEN") -> str:
    async with get_db() as db:
        async with db.execute(
            """
            SELECT token_symbol FROM tracked_positions
            WHERE token_address = ? AND token_symbol IS NOT NULL AND token_symbol != ''
            ORDER BY id DESC LIMIT 1
            """,
            (token_address,),
        ) as cur:
            row = await cur.fetchone()
            if row and row["token_symbol"]:
                return str(row["token_symbol"]).lstrip("$").upper()
    return fallback.lstrip("$").upper()


async def aggregate_pnl_stats(
    user_id: int,
    token_address: str,
    hold_sol_override: Optional[float] = None,
    wallets_override: Optional[int] = None,
) -> PnlStats:
    """
    Aggregate buy/sell SOL from submitted_transactions + open position residual.
    hold_sol_override: pass remaining position value if known from exit engine.
    """
    token_address = (token_address or "").strip()
    buy_in = 0.0
    sold = 0.0

    async with get_db() as db:
        # Buys / sells from tx log
        try:
            async with db.execute(
                """
                SELECT direction, amount_sol FROM submitted_transactions
                WHERE user_id = ? AND token_address = ?
                """,
                (user_id, token_address),
            ) as cur:
                for row in await cur.fetchall():
                    amt = float(row["amount_sol"] or 0)
                    direction = (row["direction"] or "").lower()
                    if direction in ("buy", "in"):
                        buy_in += amt
                    elif direction in ("sell", "out"):
                        sold += amt
        except Exception as e:
            logger.warning("tx aggregate failed: %s", e)

        # Fallback / supplement from tracked_positions
        try:
            async with db.execute(
                """
                SELECT amount_sol, status FROM tracked_positions
                WHERE user_id = ? AND token_address = ?
                """,
                (user_id, token_address),
            ) as cur:
                pos_buy = 0.0
                open_residual = 0.0
                for row in await cur.fetchall():
                    amt = float(row["amount_sol"] or 0)
                    pos_buy += amt
                    if (row["status"] or "").lower() == "open":
                        open_residual += amt  # approximate if no mark-to-market
                if buy_in <= 0 and pos_buy > 0:
                    buy_in = pos_buy
                if hold_sol_override is None and open_residual > 0:
                    hold_sol_override = open_residual
        except Exception as e:
            logger.warning("position aggregate failed: %s", e)

        # Wallets used: distinct buy multi-wallets for this user (best effort)
        wallets = wallets_override if wallets_override is not None else 0
        if wallets <= 0:
            try:
                async with db.execute(
                    """
                    SELECT COUNT(*) AS n FROM multi_wallets
                    WHERE user_id = ? AND is_active = 1 AND wallet_type = 'buy'
                    """,
                    (user_id,),
                ) as cur:
                    row = await cur.fetchone()
                    wallets = int(row["n"] or 0) if row else 0
            except Exception:
                wallets = 0
            if wallets <= 0:
                wallets = 1

    hold = float(hold_sol_override or 0.0)
    profit_sol = (sold + hold) - buy_in
    roi_pct = (profit_sol / buy_in * 100.0) if buy_in > 0 else 0.0

    sol_px = await fetch_sol_price_usd()
    profit_usd = profit_sol * sol_px if sol_px > 0 else 0.0

    symbol = await get_token_symbol(token_address)

    return PnlStats(
        token_address=token_address,
        symbol=symbol,
        buy_in_sol=buy_in,
        sold_sol=sold,
        hold_sol=hold,
        wallets=wallets,
        roi_pct=roi_pct,
        profit_sol=profit_sol,
        profit_usd=profit_usd,
        sol_price_usd=sol_px,
    )


def _fmt_sol(n: float) -> str:
    if abs(n) >= 100:
        return f"{n:.2f}"
    if abs(n) >= 1:
        return f"{n:.2f}"
    return f"{n:.4f}"


def _fmt_usd(n: float) -> str:
    sign = "+" if n >= 0 else "-"
    return f"{sign}${abs(n):,.0f}"


def _fmt_roi(n: float) -> str:
    sign = "+" if n >= 0 else ""
    return f"{sign}{n:.0f}%"


def render_pnl_card_image(stats: PnlStats) -> bytes:
    """
    Draw a dark neon PnL card (Pillow). Returns PNG bytes.
    No external assets required.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as e:
        raise RuntimeError(
            "Pillow is required for PnL cards. Add pillow to requirements.txt"
        ) from e

    W, H = 1200, 675
    bg = (6, 10, 18)
    cyan = (0, 229, 255)
    cyan_dim = (0, 160, 190)
    white = (240, 248, 255)
    muted = (140, 160, 180)
    green = (0, 255, 180)
    red = (255, 80, 100)

    img = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)

    # Soft grid / glow frames
    draw.rounded_rectangle([24, 24, W - 24, H - 24], radius=28, outline=(20, 40, 60), width=2)
    draw.rounded_rectangle([40, 40, W - 40, H - 40], radius=22, outline=(15, 30, 50), width=1)

    # Top bar brand
    brand = getattr(settings, "BOT_USERNAME", "") or "ShadowSnipe"
    brand = brand.lstrip("@") or "ShadowSnipe"

    def font(size: int, bold: bool = False):
        # DejaVu is commonly present on Linux (Railway). Fallback to default.
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
        for path in candidates:
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
        return ImageFont.load_default()

    f_brand = font(28, True)
    f_sym = font(96, True)
    f_label = font(22, True)
    f_num = font(36, True)
    f_profit = font(28, True)
    f_usd = font(72, True)
    f_small = font(20, False)

    draw.text((64, 56), brand.upper().replace("_", " "), fill=cyan_dim, font=f_brand)

    # Wallets badge top-right
    badge = f"{stats.wallets} WALLETS"
    bw = draw.textlength(badge, font=f_small) + 36
    bx0, by0 = W - 64 - bw, 52
    draw.rounded_rectangle([bx0, by0, bx0 + bw, by0 + 36], radius=18, outline=cyan_dim, width=2)
    draw.text((bx0 + 18, by0 + 8), badge, fill=cyan, font=f_small)

    # Symbol
    symbol = stats.symbol if stats.symbol.startswith("$") else f"${stats.symbol}"
    draw.text((64, 130), symbol, fill=white, font=f_sym)
    # underline accent
    draw.rectangle([64, 240, 280, 246], fill=cyan)

    # Metrics row
    labels = ["BUY IN", "SOLD", "HOLD", "ROI"]
    values = [
        _fmt_sol(stats.buy_in_sol),
        _fmt_sol(stats.sold_sol),
        _fmt_sol(stats.hold_sol),
        _fmt_roi(stats.roi_pct),
    ]
    colors = [white, white, white, green if stats.roi_pct >= 0 else red]

    x = 64
    y_lab, y_val = 290, 330
    col_w = 200
    for i, (lab, val, col) in enumerate(zip(labels, values, colors)):
        draw.text((x + i * col_w, y_lab), lab, fill=muted, font=f_label)
        draw.text((x + i * col_w, y_val), val, fill=col, font=f_num)

    # Profit SOL
    profit_sign = "+" if stats.profit_sol >= 0 else ""
    draw.text((64, 420), "PROFIT", fill=muted, font=f_label)
    draw.text(
        (64, 455),
        f"{profit_sign}{_fmt_sol(stats.profit_sol)} SOL",
        fill=green if stats.profit_sol >= 0 else red,
        font=f_profit,
    )

    # Big USD
    usd = _fmt_usd(stats.profit_usd) if stats.sol_price_usd > 0 else (
        f"{'+' if stats.profit_sol >= 0 else ''}{_fmt_sol(stats.profit_sol)} SOL"
    )
    draw.text(
        (64, 520),
        usd,
        fill=cyan if stats.profit_sol >= 0 else red,
        font=f_usd,
    )

    # Stylized skull placeholder (geometric)
    cx, cy = 980, 340
    draw.ellipse([cx - 110, cy - 130, cx + 110, cy + 90], outline=cyan_dim, width=3)
    draw.ellipse([cx - 55, cy - 70, cx - 10, cy - 25], outline=cyan, width=3)  # eye L
    draw.ellipse([cx + 10, cy - 70, cx + 55, cy - 25], outline=cyan, width=3)  # eye R
    draw.polygon(
        [(cx - 15, cy + 5), (cx + 15, cy + 5), (cx, cy + 40)],
        outline=cyan_dim,
    )
    draw.arc([cx - 50, cy + 20, cx + 50, cy + 70], 20, 160, fill=cyan_dim, width=3)

    # Footer links
    bot_user = getattr(settings, "BOT_USERNAME", "") or "ShadowSnipe"
    footer = f"t.me/{bot_user.lstrip('@')}  ·  ShadowSnipe"
    draw.text((64, H - 70), footer, fill=muted, font=f_small)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


async def build_pnl_card(
    user_id: int,
    token_address: str,
    *,
    hold_sol: Optional[float] = None,
    wallets: Optional[int] = None,
    symbol: Optional[str] = None,
) -> tuple[PnlStats, bytes]:
    stats = await aggregate_pnl_stats(
        user_id, token_address,
        hold_sol_override=hold_sol,
        wallets_override=wallets,
    )
    if symbol:
        stats.symbol = symbol.lstrip("$").upper()
    png = render_pnl_card_image(stats)
    return stats, png


async def send_pnl_card(
    bot,
    chat_id: int,
    user_id: int,
    token_address: str,
    *,
    hold_sol: Optional[float] = None,
    wallets: Optional[int] = None,
    symbol: Optional[str] = None,
    caption_extra: str = "",
) -> Optional[PnlStats]:
    """Render + send photo. Returns stats or None on failure."""
    from aiogram.types import BufferedInputFile

    try:
        stats, png = await build_pnl_card(
            user_id, token_address,
            hold_sol=hold_sol, wallets=wallets, symbol=symbol,
        )
        sym = stats.symbol if stats.symbol.startswith("$") else f"${stats.symbol}"
        roi = _fmt_roi(stats.roi_pct)
        caption = (
            f"⚡ <b>ShadowSnipe</b> · <code>{sym}</code> · {roi}\n"
            f"Profit: <b>{'+' if stats.profit_sol >= 0 else ''}{_fmt_sol(stats.profit_sol)} SOL</b>"
        )
        if caption_extra:
            caption += f"\n{caption_extra}"

        await bot.send_photo(
            chat_id=chat_id,
            photo=BufferedInputFile(png, filename=f"pnl_{stats.symbol}.png"),
            caption=caption,
            parse_mode="HTML",
        )
        return stats
    except Exception as e:
        logger.exception("send_pnl_card failed: %s", e)
        return None
