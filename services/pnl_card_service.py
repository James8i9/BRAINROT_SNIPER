"""
services/pnl_card_service.py
==============================
Generate professional ShadowSnipe PnL share cards and aggregate trade stats.

Brand mark: assets/shadowsnipe_skull.png (or .webp) — cyberpunk neon skull.
Falls back to geometric mark if asset missing.
"""

from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import aiohttp
from database.sqlite_db import get_db
from utils.config import settings

logger = logging.getLogger(__name__)

# Repo root (…/services/pnl_card_service.py → parent.parent)
_ROOT = Path(__file__).resolve().parent.parent
_LOGO_CANDIDATES = [
    _ROOT / "assets" / "shadowsnipe_skull.png",
    _ROOT / "assets" / "shadowsnipe_skull.webp",
    _ROOT / "assets" / "logo.png",
    Path(__file__).resolve().parent / "brand_assets" / "skull.png",
]


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
    urls = [
        "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd",
        "https://price.jup.ag/v6/price?ids=SOL",
    ]
    try:
        async with aiohttp.ClientSession() as session:
            for url in urls:
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()
                        if "solana" in data:
                            px = float((data.get("solana") or {}).get("usd") or 0)
                        else:
                            px = float(((data.get("data") or {}).get("SOL") or {}).get("price") or 0)
                        if px > 0:
                            return px
                except Exception:
                    continue
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
    token_address = (token_address or "").strip()
    buy_in = 0.0
    sold = 0.0

    async with get_db() as db:
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
                        open_residual += amt
                if buy_in <= 0 and pos_buy > 0:
                    buy_in = pos_buy
                if hold_sol_override is None and open_residual > 0:
                    hold_sol_override = open_residual
        except Exception as e:
            logger.warning("position aggregate failed: %s", e)

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
    if abs(n) >= 1000:
        return f"{n:,.1f}"
    if abs(n) >= 100:
        return f"{n:.2f}"
    if abs(n) >= 1:
        return f"{n:.2f}"
    return f"{n:.4f}"


def _fmt_usd(n: float) -> str:
    sign = "+" if n >= 0 else "-"
    v = abs(n)
    if v >= 1_000_000:
        return f"{sign}${v/1_000_000:.2f}M"
    if v >= 10_000:
        return f"{sign}${v:,.0f}"
    if v >= 100:
        return f"{sign}${v:,.0f}"
    return f"{sign}${v:,.2f}"


def _fmt_roi(n: float) -> str:
    sign = "+" if n >= 0 else ""
    if abs(n) >= 1000:
        return f"{sign}{n:,.0f}%"
    if abs(n) >= 100:
        return f"{sign}{n:.0f}%"
    return f"{sign}{n:.1f}%"


def _load_font(size: int, bold: bool = False):
    from PIL import ImageFont

    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf" if bold else "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _blend(c1: Tuple[int, int, int], c2: Tuple[int, int, int], t: float) -> Tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def _vertical_gradient(draw, box, top, bottom, steps: int = 48):
    x0, y0, x1, y1 = box
    h = max(1, y1 - y0)
    for i in range(steps):
        y_a = y0 + int(h * i / steps)
        y_b = y0 + int(h * (i + 1) / steps)
        c = _blend(top, bottom, i / max(1, steps - 1))
        draw.rectangle([x0, y_a, x1, y_b], fill=c)


def _draw_glow_ellipse(base, center, rx, ry, color, layers: int = 8):
    from PIL import Image, ImageDraw

    W, H = base.size
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    cx, cy = center
    for i in range(layers, 0, -1):
        t = i / layers
        alpha = int(22 * t)
        pad = int(32 * (1 - t) + 4)
        od.ellipse(
            [cx - rx - pad, cy - ry - pad, cx + rx + pad, cy + ry + pad],
            fill=(*color, alpha),
        )
    base.alpha_composite(overlay)


def _load_brand_logo(size: int = 280):
    """
    Load the cyberpunk skull brand mark.
    Prefer assets/shadowsnipe_skull.png (upload your logo there).
    Also tries services.brand_logo if present.
    """
    from PIL import Image

    # 1) Files on disk
    for path in _LOGO_CANDIDATES:
        try:
            if path.is_file():
                im = Image.open(path).convert("RGBA")
                im = im.resize((size, size), Image.Resampling.LANCZOS)
                logger.info("PnL logo loaded from %s", path)
                return im
        except Exception as e:
            logger.warning("logo load failed %s: %s", path, e)

    # 2) Embedded module (optional)
    try:
        from services.brand_logo import load_logo_bytes
        im = Image.open(io.BytesIO(load_logo_bytes())).convert("RGBA")
        im = im.resize((size, size), Image.Resampling.LANCZOS)
        return im
    except Exception:
        pass

    return None


def _draw_metric_chip(draw, box, label, value, value_color, f_label, f_value, accent, sol_tag: bool = True):
    x0, y0, x1, y1 = box
    draw.rounded_rectangle([x0, y0, x1, y1], radius=16, fill=(10, 16, 22), outline=(28, 55, 45), width=1)
    draw.rounded_rectangle([x0, y0 + 10, x0 + 4, y1 - 10], radius=2, fill=accent)

    draw.text((x0 + 18, y0 + 14), label, fill=(120, 150, 140), font=f_label)
    draw.text((x0 + 18, y0 + 42), value, fill=value_color, font=f_value)
    if sol_tag and label != "ROI":
        try:
            vw = draw.textlength(value, font=f_value)
        except Exception:
            vw = len(value) * 14
        draw.text((x0 + 18 + vw + 8, y0 + 50), "SOL", fill=accent, font=f_label)


def _draw_fallback_mark(draw, cx: int, cy: int, accent):
    import math
    dim = (0, 80, 55)
    r = 118
    pts = [(cx + r * math.cos(math.radians(60 * i - 30)),
            cy + r * math.sin(math.radians(60 * i - 30))) for i in range(6)]
    draw.polygon(pts, outline=dim, width=3)
    r2 = 88
    pts2 = [(cx + r2 * math.cos(math.radians(60 * i - 30)),
             cy + r2 * math.sin(math.radians(60 * i - 30))) for i in range(6)]
    draw.polygon(pts2, outline=accent, width=2)
    d = 36
    draw.polygon([(cx, cy - d), (cx + d, cy), (cx, cy + d), (cx - d, cy)], outline=accent, width=3)
    draw.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], fill=accent)


def render_pnl_card_image(stats: PnlStats) -> bytes:
    """Professional dark PnL card with ShadowSnipe skull brand mark."""
    try:
        from PIL import Image, ImageDraw
    except ImportError as e:
        raise RuntimeError("Pillow is required for PnL cards.") from e

    W, H = 1280, 720

    img = Image.new("RGBA", (W, H), (5, 8, 12, 255))
    draw = ImageDraw.Draw(img)
    _vertical_gradient(draw, [0, 0, W, H], (6, 14, 12), (4, 6, 10), steps=64)

    positive = stats.profit_sol >= 0
    # Neon green matching the brand skull glow
    accent = (0, 255, 140) if positive else (255, 90, 110)
    accent_soft = (0, 180, 100) if positive else (180, 60, 80)
    green = (0, 255, 160)
    red = (255, 95, 115)
    white = (245, 250, 255)
    muted = (130, 155, 145)

    _draw_glow_ellipse(img, (240, 160), 240, 150, accent_soft, layers=10)
    _draw_glow_ellipse(img, (1040, 360), 200, 200, accent_soft, layers=12)

    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle([28, 28, W - 28, H - 28], radius=32, outline=(20, 50, 40), width=2)
    draw.rounded_rectangle([36, 36, W - 36, H - 36], radius=28, outline=(14, 32, 26), width=1)
    draw.rectangle([80, 36, W - 80, 38], fill=(*accent, 200))

    brand = (getattr(settings, "BOT_USERNAME", "") or "ShadowSnipe").lstrip("@") or "ShadowSnipe"
    brand_disp = brand.upper().replace("_", " ")

    f_brand = _load_font(26, True)
    f_sym = _load_font(92, True)
    f_label = _load_font(18, True)
    f_chip_val = _load_font(30, True)
    f_section = _load_font(18, True)
    f_profit = _load_font(32, True)
    f_usd = _load_font(78, True)
    f_small = _load_font(18, False)
    f_tiny = _load_font(15, False)

    draw.text((72, 58), brand_disp, fill=accent_soft, font=f_brand)

    badge = f"{stats.wallets} WALLETS"
    try:
        bw = int(draw.textlength(badge, font=f_small)) + 40
    except Exception:
        bw = 140
    bx0, by0 = W - 72 - bw, 56
    draw.rounded_rectangle([bx0, by0, bx0 + bw, by0 + 38], radius=19, outline=accent_soft, width=2)
    draw.text((bx0 + 20, by0 + 9), badge, fill=accent, font=f_small)

    symbol = stats.symbol if stats.symbol.startswith("$") else f"${stats.symbol}"
    draw.text((72, 118), symbol, fill=white, font=f_sym)
    try:
        sw = int(draw.textlength(symbol, font=f_sym))
    except Exception:
        sw = 220
    draw.rectangle([72, 222, 72 + min(sw, 320), 228], fill=accent)

    chip_y0, chip_y1 = 260, 350
    gap = 18
    chip_w = (W - 72 - 72 - gap * 3) // 4
    metrics = [
        ("BUY IN", _fmt_sol(stats.buy_in_sol), white, True),
        ("SOLD", _fmt_sol(stats.sold_sol), white, True),
        ("HOLD", _fmt_sol(stats.hold_sol), white, True),
        ("ROI", _fmt_roi(stats.roi_pct), green if stats.roi_pct >= 0 else red, False),
    ]
    for i, (lab, val, col, sol_tag) in enumerate(metrics):
        x0 = 72 + i * (chip_w + gap)
        _draw_metric_chip(
            draw, [x0, chip_y0, x0 + chip_w, chip_y1],
            lab, val, col, f_label, f_chip_val, accent, sol_tag=sol_tag,
        )

    profit_sign = "+" if stats.profit_sol >= 0 else ""
    profit_color = green if positive else red

    draw.text((72, 390), "NET PROFIT", fill=muted, font=f_section)
    draw.text(
        (72, 420),
        f"{profit_sign}{_fmt_sol(stats.profit_sol)} SOL",
        fill=profit_color,
        font=f_profit,
    )

    if stats.sol_price_usd > 0:
        usd_text = _fmt_usd(stats.profit_usd)
    else:
        usd_text = f"{profit_sign}{_fmt_sol(stats.profit_sol)} SOL"
    draw.text((72, 475), usd_text, fill=accent if positive else red, font=f_usd)

    draw.rectangle([72, H - 88, W - 72, H - 87], fill=(25, 50, 40))

    # Brand skull logo (right side)
    logo = _load_brand_logo(size=300)
    if logo is not None:
        # soft green glow behind logo
        _draw_glow_ellipse(img, (1040, 380), 150, 150, accent_soft, layers=10)
        lx, ly = 1040 - logo.width // 2, 380 - logo.height // 2
        img.alpha_composite(logo, (lx, ly))
        draw = ImageDraw.Draw(img)
    else:
        _draw_glow_ellipse(img, (1040, 380), 140, 140, accent_soft, layers=8)
        draw = ImageDraw.Draw(img)
        _draw_fallback_mark(draw, 1040, 380, accent)

    bot_user = (getattr(settings, "BOT_USERNAME", "") or "ShadowSnipe").lstrip("@")
    mint = stats.token_address or ""
    mint_short = f"{mint[:4]}…{mint[-4:]}" if len(mint) > 12 else mint
    footer_l = f"t.me/{bot_user}"
    footer_r = f"{mint_short}  ·  ShadowSnipe"
    draw.text((72, H - 62), footer_l, fill=muted, font=f_tiny)
    try:
        rw = draw.textlength(footer_r, font=f_tiny)
    except Exception:
        rw = 200
    draw.text((W - 72 - rw, H - 62), footer_r, fill=(80, 110, 95), font=f_tiny)

    out = Image.new("RGB", (W, H), (5, 8, 12))
    out.paste(img, mask=img.split()[3] if img.mode == "RGBA" else None)

    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
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
