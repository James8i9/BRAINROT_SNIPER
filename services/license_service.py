"""
services/license_service.py
===========================
License key generation + user activation + payment verification.

Keys are single-use and bound to exactly one Telegram account.
Payment verification uses ACTIVATION_NETWORK (mainnet / devnet / testnet).
"""

import logging
import random
import string
from typing import Optional

import aiohttp
from database.sqlite_db import get_db
from utils.config import settings

logger = logging.getLogger(__name__)

_ACTIVATION_RPC = {
    "mainnet": "https://api.mainnet-beta.solana.com",
    "devnet":  "https://api.devnet.solana.com",
    "testnet": "https://api.testnet.solana.com",
}


def _generate_key_code() -> str:
    def block():
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"{block()}-{block()}-{block()}-{block()}"


def get_activation_rpc_url() -> str:
    network = (getattr(settings, "ACTIVATION_NETWORK", None) or "testnet").strip().lower()
    if network not in _ACTIVATION_RPC:
        network = "testnet"
    override = getattr(settings, "ACTIVATION_RPC_URL", "") or ""
    if override.strip():
        return override.strip()
    return _ACTIVATION_RPC[network]


def activation_network_label() -> str:
    network = (getattr(settings, "ACTIVATION_NETWORK", None) or "testnet").strip().lower()
    return network if network in _ACTIVATION_RPC else "testnet"


async def create_license_key(created_by: int, assigned_to: Optional[int] = None) -> str:
    """Generate and store a new license key. Optionally reserve for one Telegram user."""
    for _ in range(10):
        key = _generate_key_code()
        try:
            async with get_db() as db:
                await db.execute(
                    "INSERT INTO license_keys (key_code, created_by, assigned_to) VALUES (?, ?, ?)",
                    (key, created_by, assigned_to),
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


async def validate_key_for_user(key_code: str, user_id: int) -> dict:
    record = await get_license_key(key_code)
    if not record:
        return {"ok": False, "error": "Invalid license key.", "record": None}

    assigned = record.get("assigned_to")
    if assigned is not None and int(assigned) != int(user_id):
        return {
            "ok": False,
            "error": "This license key is reserved for a different Telegram account.",
            "record": record,
        }

    if record.get("is_used"):
        used_by = record.get("used_by")
        if used_by is not None and int(used_by) == int(user_id):
            return {
                "ok": False,
                "error": "You already used this license key on this account.",
                "record": record,
            }
        return {
            "ok": False,
            "error": "This license key is already bound to another Telegram account.",
            "record": record,
        }

    if await is_user_activated(user_id):
        return {
            "ok": False,
            "error": "This Telegram account is already activated.",
            "record": record,
        }

    return {"ok": True, "error": None, "record": record}


async def mark_key_used(key_code: str, user_id: int) -> bool:
    key = key_code.upper().strip()
    async with get_db() as db:
        cur = await db.execute("""
            UPDATE license_keys
            SET is_used = 1, used_by = ?, used_at = CURRENT_TIMESTAMP
            WHERE key_code = ?
              AND is_used = 0
              AND (assigned_to IS NULL OR assigned_to = ?)
        """, (user_id, key, user_id))
        await db.commit()
        return cur.rowcount > 0


async def is_user_activated(user_id: int) -> bool:
    async with get_db() as db:
        async with db.execute(
            "SELECT is_active FROM user_activations WHERE user_id = ? AND is_active = 1",
            (user_id,),
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


async def verify_payment_transaction(
    signature: str,
    required_sol: Optional[float] = None,
) -> dict:
    """
    Verify the tx sent ~required_sol to ACTIVATION_WALLET on ACTIVATION_NETWORK.
    If required_sol is None, uses ACTIVATION_AMOUNT_SOL (default 1.0).
    """
    activation_wallet = getattr(settings, "ACTIVATION_WALLET", None)
    if required_sol is None:
        required_sol = float(getattr(settings, "ACTIVATION_AMOUNT_SOL", 1.0))
    else:
        required_sol = float(required_sol)

    network = activation_network_label()
    rpc_url = get_activation_rpc_url()

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
                "commitment": "confirmed",
            },
        ],
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                rpc_url, json=body, timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                data = await resp.json()

                if "error" in data:
                    return {"valid": False, "error": f"RPC error ({network}): {data['error']}"}

                result = data.get("result")
                if not result:
                    return {
                        "valid": False,
                        "error": (
                            f"Transaction not found on {network}. "
                            f"Confirm you sent on Solana {network} and the signature is correct."
                        ),
                    }

                meta = result.get("meta", {})
                if meta.get("err"):
                    return {"valid": False, "error": "Transaction failed on-chain"}

                pre_balances = meta.get("preBalances", [])
                post_balances = meta.get("postBalances", [])
                account_keys = result.get("transaction", {}).get("message", {}).get("accountKeys", [])

                target_index = None
                for i, acc in enumerate(account_keys):
                    pubkey = acc if isinstance(acc, str) else acc.get("pubkey")
                    if pubkey == activation_wallet:
                        target_index = i
                        break

                if target_index is None:
                    return {
                        "valid": False,
                        "error": (
                            f"Payment wallet not found in this transaction. "
                            f"Send {required_sol} SOL on {network} to {activation_wallet}"
                        ),
                    }

                pre = pre_balances[target_index] if target_index < len(pre_balances) else 0
                post = post_balances[target_index] if target_index < len(post_balances) else 0
                received_lamports = post - pre
                received_sol = received_lamports / 1_000_000_000

                if received_sol < (required_sol * 0.95):
                    return {
                        "valid": False,
                        "error": (
                            f"Insufficient amount on {network}. "
                            f"Received {received_sol:.4f} SOL, required ~{required_sol} SOL"
                        ),
                    }

                return {
                    "valid": True,
                    "error": None,
                    "received_sol": received_sol,
                    "network": network,
                }

    except Exception as e:
        logger.error(f"Payment verification failed ({network}): {e}")
        return {"valid": False, "error": str(e)}
