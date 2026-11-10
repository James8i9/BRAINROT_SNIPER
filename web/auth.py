"""
web/auth.py
===========
Validate Telegram WebApp initData and resolve access.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import parse_qsl

from utils.admin import is_admin
from utils.config import settings
from services.license_service import is_user_activated

logger = logging.getLogger(__name__)

# Reject initData older than this (seconds)
_INIT_DATA_MAX_AGE = 86400  # 24h


@dataclass
class WebAppUser:
    user_id: int
    username: str = ""
    first_name: str = ""
    activated: bool = False
    referral: bool = False  # stub until referral system ships
    is_admin: bool = False

    @property
    def can_access(self) -> bool:
        return self.activated or self.referral or self.is_admin


def _secret_key(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()


def validate_init_data(init_data: str, bot_token: Optional[str] = None) -> Optional[dict[str, Any]]:
    """
    Verify Telegram WebApp initData HMAC.
    Returns parsed fields (without hash) or None if invalid.
    """
    if not init_data or not isinstance(init_data, str):
        return None

    token = bot_token or settings.BOT_TOKEN
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    except Exception:
        return None

    received = pairs.pop("hash", None)
    if not received:
        return None

    check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    expected = hmac.new(_secret_key(token), check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        logger.warning("initData hash mismatch")
        return None

    # Optional freshness check
    try:
        auth_date = int(pairs.get("auth_date") or 0)
        if auth_date and (time.time() - auth_date) > _INIT_DATA_MAX_AGE:
            logger.warning("initData expired auth_date=%s", auth_date)
            return None
    except Exception:
        pass

    return pairs


def parse_user_from_init(pairs: dict[str, Any]) -> Optional[dict[str, Any]]:
    raw = pairs.get("user")
    if not raw:
        return None
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return None


async def resolve_webapp_user(init_data: str) -> Optional[WebAppUser]:
    """Full gate: validate signature → load activation / referral / admin."""
    pairs = validate_init_data(init_data)
    if not pairs:
        return None

    tg_user = parse_user_from_init(pairs)
    if not tg_user or "id" not in tg_user:
        return None

    uid = int(tg_user["id"])
    activated = await is_user_activated(uid)
    referral = await has_referral_access(uid)  # stub
    admin = is_admin(uid)

    return WebAppUser(
        user_id=uid,
        username=str(tg_user.get("username") or ""),
        first_name=str(tg_user.get("first_name") or ""),
        activated=activated,
        referral=referral,
        is_admin=admin,
    )


async def has_referral_access(user_id: int) -> bool:
    """
    Placeholder for the future referral system.
    When referrals ship: return True if user unlocked via valid referral.
    """
    return False
