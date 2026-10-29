"""
services/license_service.py
===========================
License key generation + user activation + payment verification.

Keys are single-use and bound to exactly one Telegram account.
Payment signatures are single-use (replay blocked).
Payment verification uses ACTIVATION_NETWORK + optional ACTIVATION_RPC_URL / Helius.
"""

import asyncio
import logging
import random
import re
import string
from typing import Optional

import aiohttp
from database.sqlite_db import get_db
from utils.config import settings

logger = logging.getLogger(__name__)

# Primary + fallback public RPCs per cluster (public endpoints can be flaky)
_ACTIVATION_RPC = {
    "mainnet": [
        "https://api.mainnet-beta.solana.com",
    ],
    "devnet": [
        "https://api.devnet.solana.com",
        "https://rpc.ankr.com/solana_devnet",
    ],
    "testnet": [
        "https://api.testnet.solana.com",
    ],
}

_sig_table_ready = False

# Base58-ish Solana signatures are typically 87–88 chars
_SIG_RE = re.compile(r"[1-9A-HJ-NP-Za-km-z]{80,90}")


def _generate_key_code() -> str:
    def block():
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    return f"{block()}-{block()}-{block()}-{block()}"


def activation_network_label() -> str:
    network = (getattr(settings, "ACTIVATION_NETWORK", None) or "testnet").strip().lower()
    return network if network in _ACTIVATION_RPC else "testnet"


def _normalize_signature(raw: str) -> str:
    """Accept raw signature or explorer URL and return the signature string."""
    text = (raw or "").strip()
    if not text:
        return ""

    # Common explorer / Solscan / SolanaFM URLs
    for marker in ("/tx/", "/transaction/", "signature="):
        if marker in text:
            part = text.split(marker, 1)[1]
            part = part.split("?", 1)[0].split("&", 1)[0].split("/", 1)[0].strip()
            if part:
                return part

    # Bare signature (maybe with whitespace / backticks)
    text = text.strip("`'\" \t\n\r")
    m = _SIG_RE.search(text)
    if m:
        return m.group(0)
    return text


def get_activation_rpc_urls() -> list[str]:
    """
    Ordered list of RPCs for payment verification.
    Priority:
      1) ACTIVATION_RPC_URL (explicit single override)
      2) SOLANA_RPC_URL when network is mainnet (e.g. Helius)
      3) public cluster endpoints (+ fallbacks)
    """
    network = activation_network_label()
    urls: list[str] = []

    override = (getattr(settings, "ACTIVATION_RPC_URL", "") or "").strip()
    if override:
        urls.append(override)

    if network == "mainnet":
        trading = (getattr(settings, "SOLANA_RPC_URL", "") or "").strip()
        if trading and "api.mainnet-beta.solana.com" not in trading and trading not in urls:
            urls.append(trading)

    for u in _ACTIVATION_RPC.get(network, _ACTIVATION_RPC["testnet"]):
        if u not in urls:
            urls.append(u)

    return urls or ["https://api.devnet.solana.com"]


def get_activation_rpc_url() -> str:
    """Back-compat single URL (first preferred)."""
    return get_activation_rpc_urls()[0]


async def _rpc_post(session: aiohttp.ClientSession, rpc_url: str, method: str, params: list) -> dict:
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    async with session.post(rpc_url, json=body, timeout=aiohttp.ClientTimeout(total=20)) as resp:
        return await resp.json()


async def _fetch_transaction(sig: str, network: str) -> tuple[Optional[dict], Optional[str]]:
    """
    Try multiple RPCs and a short retry loop until the tx appears.
    Returns (result_dict, error_message).
    """
    rpc_urls = get_activation_rpc_urls()
    last_error = None

    async with aiohttp.ClientSession() as session:
        # 1) Quick status probe (faster / often more available than full getTransaction)
        for rpc_url in rpc_urls:
            try:
                data = await _rpc_post(
                    session,
                    rpc_url,
                    "getSignatureStatuses",
                    [[sig], {"searchTransactionHistory": True}],
                )
                if "error" in data:
                    last_error = f"RPC error ({network}): {data['error']}"
                    logger.warning("getSignatureStatuses error on %s: %s", rpc_url[:48], data["error"])
                    continue
                statuses = (data.get("result") or {}).get("value") or []
                status = statuses[0] if statuses else None
                if status is None:
                    last_error = (
                        f"Transaction not found on {network}. "
                        f"Confirm you sent on Solana {network} and the signature is correct."
                    )
                    continue
                if status.get("err"):
                    return None, "Transaction failed on-chain"
                # Found on this RPC — pull full tx next
                break
            except Exception as e:
                last_error = str(e)
                logger.warning("getSignatureStatuses failed on %s: %s", rpc_url[:48], e)

        # 2) Full transaction — retry a few times (index lag on public Devnet RPCs)
        for attempt in range(4):
            for rpc_url in rpc_urls:
                try:
                    for commitment in ("confirmed", "finalized"):
                        data = await _rpc_post(
                            session,
                            rpc_url,
                            "getTransaction",
                            [
                                sig,
                                {
                                    "encoding": "jsonParsed",
                                    "maxSupportedTransactionVersion": 0,
                                    "commitment": commitment,
                                },
                            ],
                        )
                        if "error" in data:
                            last_error = f"RPC error ({network}): {data['error']}"
                            logger.warning(
                                "getTransaction error on %s (%s): %s",
                                rpc_url[:48], commitment, data["error"],
                            )
                            continue

                        result = data.get("result")
                        if result:
                            logger.info(
                                "Payment tx found on %s via %s (attempt %s, %s)",
                                network, rpc_url[:48], attempt + 1, commitment,
                            )
                            return result, None

                        last_error = (
                            f"Transaction not found on {network}. "
                            f"Confirm you sent on Solana {network} and the signature is correct."
                        )
                except Exception as e:
                    last_error = str(e)
                    logger.warning("getTransaction failed on %s: %s", rpc_url[:48], e)

            if attempt < 3:
                await asyncio.sleep(1.5 * (attempt + 1))

    return None, last_error or (
        f"Transaction not found on {network}. "
        f"Confirm you sent on Solana {network} and the signature is correct."
    )


async def _ensure_signature_table() -> None:
    global _sig_table_ready
    if _sig_table_ready:
        return
    async with get_db() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS used_payment_signatures (
                signature   TEXT    PRIMARY KEY,
                user_id     INTEGER NOT NULL,
                purpose     TEXT    NOT NULL DEFAULT 'activation',
                amount_sol  REAL,
                network     TEXT,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()
    _sig_table_ready = True


async def is_signature_used(signature: str) -> bool:
    await _ensure_signature_table()
    sig = signature.strip()
    async with get_db() as db:
        async with db.execute(
            "SELECT 1 FROM used_payment_signatures WHERE signature = ?",
            (sig,),
        ) as cur:
            return await cur.fetchone() is not None


async def claim_payment_signature(
    signature: str,
    user_id: int,
    purpose: str = "activation",
    amount_sol: Optional[float] = None,
    network: Optional[str] = None,
) -> bool:
    """
    Atomically claim a payment signature so it cannot be reused.
    Returns True if this is the first claim, False if already used.
    """
    await _ensure_signature_table()
    sig = signature.strip()
    if not sig:
        return False
    async with get_db() as db:
        try:
            await db.execute(
                """
                INSERT INTO used_payment_signatures
                    (signature, user_id, purpose, amount_sol, network)
                VALUES (?, ?, ?, ?, ?)
                """,
                (sig, user_id, purpose, amount_sol, network),
            )
            await db.commit()
            return True
        except Exception:
            # UNIQUE constraint — already claimed
            return False


async def create_license_key(created_by: int, assigned_to: Optional[int] = None) -> str:
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
    user_id: Optional[int] = None,
    purpose: str = "activation",
) -> dict:
    """
    Verify the tx sent ~required_sol to ACTIVATION_WALLET on ACTIVATION_NETWORK.
    If user_id is provided, rejects signatures already claimed (replay protection).
    On success with user_id, claims the signature so it cannot be reused.
    """
    activation_wallet = getattr(settings, "ACTIVATION_WALLET", None)
    if required_sol is None:
        required_sol = float(getattr(settings, "ACTIVATION_AMOUNT_SOL", 1.0))
    else:
        required_sol = float(required_sol)

    network = activation_network_label()
    sig = _normalize_signature(signature)

    if not sig:
        return {"valid": False, "error": "Empty transaction signature"}

    if len(sig) < 80:
        return {
            "valid": False,
            "error": (
                f"Signature looks too short ({len(sig)} chars). "
                f"Paste the full transaction signature (or explorer /tx/ URL)."
            ),
        }

    if not activation_wallet:
        return {"valid": False, "error": "Activation wallet not configured"}

    # Fail fast on known replay (use normalized sig)
    if user_id is not None and await is_signature_used(sig):
        return {
            "valid": False,
            "error": "This transaction signature was already used for activation.",
        }

    try:
        result, fetch_error = await _fetch_transaction(sig, network)
        if not result:
            return {"valid": False, "error": fetch_error or f"Transaction not found on {network}"}

        meta = result.get("meta", {}) or {}
        if meta.get("err"):
            return {"valid": False, "error": "Transaction failed on-chain"}

        pre_balances = meta.get("preBalances", []) or []
        post_balances = meta.get("postBalances", []) or []
        account_keys = (
            result.get("transaction", {}).get("message", {}).get("accountKeys", []) or []
        )

        target_index = None
        for i, acc in enumerate(account_keys):
            pubkey = acc if isinstance(acc, str) else (acc or {}).get("pubkey")
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

        # Claim after chain validation so bad sigs are not burned
        if user_id is not None:
            claimed = await claim_payment_signature(
                sig,
                user_id=user_id,
                purpose=purpose,
                amount_sol=received_sol,
                network=network,
            )
            if not claimed:
                return {
                    "valid": False,
                    "error": "This transaction signature was already used for activation.",
                }

        return {
            "valid": True,
            "error": None,
            "received_sol": received_sol,
            "network": network,
            "signature": sig,
        }

    except Exception as e:
        logger.error(f"Payment verification failed ({network}): {e}")
        return {"valid": False, "error": str(e)}
