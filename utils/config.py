"""
utils/config.py
===============
Loads and validates all environment variables.
Single shared settings object — import `settings` everywhere.
"""

import sys
import logging
from dataclasses import dataclass, field

from dotenv import load_dotenv
import os

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class Settings:
    BOT_TOKEN: str

    # ── Admin ──────────────────────────────────────────────────────────────────
    ADMIN_IDS: list[int] = field(default_factory=list)

    # ── Branding / public links ────────────────────────────────────────────
    BOT_USERNAME: str = ""
    DISCORD_URL:  str = ""
    TWITTER_URL:  str = ""
    WEBSITE_URL:  str = ""
    TOKEN_NAME:   str = "TOKEN"
    BRAND_HANDLE: str = ""
    SHARE_HASHTAG: str = ""

    # ── Wallet encryption ──────────────────────────────────────────────────────
    WALLET_ENCRYPTION_KEY: str = ""

    # ── License / Activation ───────────────────────────────────────────────────
    ACTIVATION_WALLET: str = ""
    ACTIVATION_AMOUNT_SOL: float = 1.0
    # mainnet | devnet | testnet — payment verification only (trading RPCs unchanged)
    ACTIVATION_NETWORK: str = "testnet"
    # Optional explicit RPC for activation checks; blank = use network default
    ACTIVATION_RPC_URL: str = ""

    # ── Solana trading RPC (mainnet by default) ───────────────────────────────
    SOLANA_RPC_URL: str = "https://api.mainnet-beta.solana.com"
    SOLANA_RPC_URLS: list[str] = field(default_factory=list)

    # ── Raid Hub behaviour ─────────────────────────────────────────────────────
    RAID_AUTO_APPROVE: bool = True
    DAILY_RAID_LIMIT: int = 2


def _load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        logger.critical(
            "BOT_TOKEN is missing. Copy .env.example to .env, paste the token "
            "@BotFather gave you, then restart. See SETUP.md."
        )
        sys.exit(1)

    enc_key = os.getenv("WALLET_ENCRYPTION_KEY", "").strip()
    if not enc_key:
        logger.critical(
            "WALLET_ENCRYPTION_KEY is missing. Generate your OWN key by "
            "running this command, then paste the output into .env:"
        )
        logger.critical(
            '    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
        sys.exit(1)

    admin_ids = [
        int(x.strip())
        for x in os.getenv("ADMIN_IDS", "").split(",")
        if x.strip().isdigit()
    ]

    auto_approve = os.getenv("RAID_AUTO_APPROVE", "true").strip().lower() == "true"
    daily_limit = int(os.getenv("DAILY_RAID_LIMIT", "2"))

    network = os.getenv("ACTIVATION_NETWORK", "testnet").strip().lower()
    if network not in ("mainnet", "devnet", "testnet"):
        network = "testnet"

    primary_rpc = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com").strip()
    extra_rpcs = [
        u.strip()
        for u in os.getenv("SOLANA_RPC_URLS", "").split(",")
        if u.strip()
    ]
    rpc_list = [primary_rpc] + [u for u in extra_rpcs if u != primary_rpc]

    return Settings(
        BOT_TOKEN=token,
        ADMIN_IDS=admin_ids,
        BOT_USERNAME=os.getenv("BOT_USERNAME", "").strip().lstrip("@"),
        DISCORD_URL=os.getenv("DISCORD_URL", "").strip(),
        TWITTER_URL=os.getenv("TWITTER_URL", "").strip(),
        WEBSITE_URL=os.getenv("WEBSITE_URL", "").strip(),
        TOKEN_NAME=os.getenv("TOKEN_NAME", "TOKEN").strip(),
        BRAND_HANDLE=os.getenv("BRAND_HANDLE", "").strip(),
        SHARE_HASHTAG=os.getenv("SHARE_HASHTAG", "").strip(),
        WALLET_ENCRYPTION_KEY=enc_key,
        ACTIVATION_WALLET=os.getenv("ACTIVATION_WALLET", "").strip(),
        ACTIVATION_AMOUNT_SOL=float(os.getenv("ACTIVATION_AMOUNT_SOL", "1.0")),
        ACTIVATION_NETWORK=network,
        ACTIVATION_RPC_URL=os.getenv("ACTIVATION_RPC_URL", "").strip(),
        SOLANA_RPC_URL=primary_rpc,
        SOLANA_RPC_URLS=rpc_list,
        RAID_AUTO_APPROVE=auto_approve,
        DAILY_RAID_LIMIT=daily_limit,
    )


settings: Settings = _load_settings()


def _warn_unconfigured() -> None:
    if not settings.BOT_USERNAME:
        logger.warning(
            "BOT_USERNAME is not set - share and referral links will be omitted."
        )
    if not settings.ADMIN_IDS:
        logger.warning(
            "ADMIN_IDS is empty - no one can use admin commands. "
            "Send /myid to your bot to get your Telegram ID, then add it to .env."
        )
    if not settings.ACTIVATION_WALLET:
        logger.warning(
            "ACTIVATION_WALLET is empty - license activation payments cannot be verified."
        )
    logger.info(
        "Activation fee network: %s (amount=%s SOL)",
        settings.ACTIVATION_NETWORK,
        settings.ACTIVATION_AMOUNT_SOL,
    )


_warn_unconfigured()


# ── RPC rotation (trading) ─────────────────────────────────────────────────────
import time as _time

_rpc_cooldowns: dict[str, float] = {}
_RPC_COOLDOWN_SEC = 10
_rpc_index = 0


def get_rpc_url() -> str:
    global _rpc_index
    urls = settings.SOLANA_RPC_URLS or [settings.SOLANA_RPC_URL]
    now = _time.time()

    for _ in range(len(urls)):
        url = urls[_rpc_index % len(urls)]
        _rpc_index += 1
        if now - _rpc_cooldowns.get(url, 0) > _RPC_COOLDOWN_SEC:
            return url

    return urls[0]


def mark_rpc_rate_limited(url: str) -> None:
    _rpc_cooldowns[url] = _time.time()
    logger.warning(f"RPC rate-limited, cooling down {_RPC_COOLDOWN_SEC}s: {url[:50]}")
