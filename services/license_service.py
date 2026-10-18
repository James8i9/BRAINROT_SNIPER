"""
services/license_service.py
===========================
License key generation + user activation + payment verification
"""

import logging
import random
import string
from typing import Optional

import aiohttp
from database.sqlite_db import get_db
from utils.config import settings

logger = logging.getLogger(__name__)


def _generate_key_code() -> str:
    """Generate a key in the format XXXXX-XXXXX-XXXXX-XXXXX"""
    def block():
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"{block()}-{block()}-{block()}-{block()}"


async def create_license_key(created_by: int) -> str:
    """Generate and store a new license key. Returns the key code."""
    for _ in range(10):  # retry if collision
        key = _generate_key_code()
        try:
            async with get_db() as db:
                await db.execute(
                    "INSERT INTO license_keys (key_code, created_by) VALUES (?, ?)",
                    (key, created_by)
                )
                await db.commit()
            return key
        except Exception:
            continue
    raise Exception("Failed to generate unique license key")


async def get_license_key(key_code: str) -> Optional[dict]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM license_keys WHERE key_code = ?", (key_code.upper().strip(),)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def mark_key_used(key_code: str, user_id: int) -> None:
    async with get_db() as db:
        await db.execute("""
            UPDATE license_keys
            SET is_used = 1, used_by = ?, used_at = CURRENT_TIMESTAMP
            WHERE key_code = ?
        """, (user_id, key_code.upper().strip()))
        await db.commit()


async def is_user_activated(user_id: int) -> bool:
    async with get_db() as db:
        async with db.execute(
            "SELECT is_active FROM user_activations WHERE user_id = ? AND is_active = 1",
            (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return bool(row)


async def activate_user(user_id: int, license_key: str, payment_signature: str) -> None:
    async with get_db() as db:
        await db.execute("""
            INSERT INTO user_activations (user_id, license_key, payment_signature, is_active)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(user_id) DO UPDATE SET
                license_key = excluded.license_key,
                payment_signature = excluded.payment_signature,
                is_active = 1,
                activated_at = CURRENT_TIMESTAMP
        """, (user_id, license_key.upper().strip(), payment_signature))
        await db.commit()


async def verify_payment_transaction(signature: str) -> dict:
    """
    Verify that the given transaction sent approximately 1 SOL
    to the ACTIVATION_WALLET.
    Returns {"valid": bool, "error": str|None}
    """
    from utils.config import get_rpc_url

    activation_wallet = getattr(settings, "ACTIVATION_WALLET", None)
    required_sol = float(getattr(settings, "ACTIVATION_AMOUNT_SOL", 1.0))

    if not activation_wallet:
        return {"valid": False, "error": "Activation wallet not configured"}

    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [
            signature.strip(),
            {
                "encoding": "jsonParsed",
                "maxSupportedTransactionVersion": 0,
                "commitment": "confirmed"
            }
        ]
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(get_rpc_url(), json=body, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                data = await resp.json()
                
                if "error" in data:
                    return {"valid": False, "error": f"RPC error: {data['error']}"}

                result = data.get("result")
                if not result:
                    return {"valid": False, "error": "Transaction not found or not confirmed yet"}

                # Look for SOL transfer to our activation wallet
                meta = result.get("meta", {})
                if meta.get("err"):
                    return {"valid": False, "error": "Transaction failed on-chain"}

                pre_balances = meta.get("preBalances", [])
                post_balances = meta.get("postBalances", [])
                account_keys = result.get("transaction", {}).get("message", {}).get("accountKeys", [])

                # Find the activation wallet index
                target_index = None
                for i, acc in enumerate(account_keys):
                    pubkey = acc if isinstance(acc, str) else acc.get("pubkey")
                    if pubkey == activation_wallet:
                        target_index = i
                        break

                if target_index is None:
                    return {"valid": False, "error": "Activation wallet not found in this transaction"}

                # Calculate SOL received by the activation wallet
                pre = pre_balances[target_index] if target_index < len(pre_balances) else 0
                post = post_balances[target_index] if target_index < len(post_balances) else 0
                received_lamports = post - pre
                received_sol = received_lamports / 1_000_000_000

                # Allow small tolerance (0.95 – 1.05 SOL)
                if received_sol < (required_sol * 0.95):
                    return {
                        "valid": False,
                        "error": f"Insufficient amount. Received {received_sol:.4f} SOL, required ~{required_sol} SOL"
                    }

                return {"valid": True, "error": None, "received_sol": received_sol}

    except Exception as e:
        logger.error(f"Payment verification failed: {e}")
        return {"valid": False, "error": str(e)}
