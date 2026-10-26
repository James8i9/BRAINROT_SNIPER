"""
database/db.py
==============
SQLite database layer using aiosqlite (async).
All tables are created here on startup.
"""

import aiosqlite
import logging

from database.paths import get_db_path

logger = logging.getLogger(__name__)


async def init_db() -> None:
    """Creates all required tables if they don't already exist."""
    db_path = get_db_path()
    logger.info("SQLite database path: %s", db_path)
    async with aiosqlite.connect(db_path) as db:

        async def _migrate(sql: str) -> None:
            try:
                await db.execute(sql)
            except Exception:
                pass

        # ── License & activation ──────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS license_keys (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                key_code    TEXT    NOT NULL UNIQUE,
                created_by  INTEGER,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_used     INTEGER DEFAULT 0,
                used_by     INTEGER,
                used_at     TIMESTAMP,
                assigned_to INTEGER
            )
        """)
        await _migrate("ALTER TABLE license_keys ADD COLUMN assigned_to INTEGER")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_activations (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id             INTEGER NOT NULL UNIQUE,
                license_key         TEXT    NOT NULL,
                payment_signature   TEXT,
                activated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active           INTEGER DEFAULT 1
            )
        """)

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

        # ── Users / wallet links ──────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL UNIQUE,
                username         TEXT,
                first_name       TEXT,
                created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS wallet_links (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id        INTEGER NOT NULL UNIQUE,
                wallet_address TEXT    NOT NULL,
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ── Multi-wallet ──────────────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS multi_wallets (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id               INTEGER NOT NULL,
                wallet_address        TEXT    NOT NULL,
                encrypted_private_key TEXT    NOT NULL,
                wallet_type           TEXT    NOT NULL CHECK(wallet_type IN ('fund', 'buy')),
                label                 TEXT    DEFAULT '',
                is_active             INTEGER DEFAULT 1,
                created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, wallet_address)
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_multi_wallets_user ON multi_wallets(user_id)")

        # ── Sniper ────────────────────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sniper_settings (
                id                            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id                       INTEGER NOT NULL UNIQUE,
                min_liquidity                 REAL    DEFAULT 2000,
                min_volume                    REAL    DEFAULT 1000,
                min_buys                      INTEGER DEFAULT 10,
                max_token_age_minutes         INTEGER DEFAULT 60,
                max_risk_level                INTEGER DEFAULT 3,
                default_buy_size              REAL    DEFAULT 0.05,
                default_slippage              REAL    DEFAULT 15.0,
                strict_mode                   INTEGER DEFAULT 0,
                auto_filter_enabled           INTEGER DEFAULT 0,
                prioritize_fresh_launches     INTEGER DEFAULT 0,
                prioritize_liquidity_strength INTEGER DEFAULT 0,
                auto_hide_weak_metadata       INTEGER DEFAULT 0,
                auto_hide_low_momentum        INTEGER DEFAULT 0,
                instant_alert_on_match        INTEGER DEFAULT 0,
                premium_ranking_boost         INTEGER DEFAULT 0,
                preferred_platform            TEXT    DEFAULT 'auto',
                updated_at                    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await _migrate("ALTER TABLE sniper_settings ADD COLUMN preferred_platform TEXT DEFAULT 'auto'")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS sniper_presets (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                name        TEXT    NOT NULL,
                settings_json TEXT  NOT NULL,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS sniper_watch_targets (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                token_address TEXT    NOT NULL,
                added_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, token_address)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS sniper_blacklist (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                token_address TEXT    NOT NULL,
                added_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, token_address)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS whale_sniper_settings (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id           INTEGER NOT NULL UNIQUE,
                enabled           INTEGER DEFAULT 0,
                kill_switch       INTEGER DEFAULT 0,
                min_whale_sol     REAL    DEFAULT 1.0,
                curve_depth_pct   REAL    DEFAULT 0.0,
                copy_buy_size_sol REAL    DEFAULT 0.01,
                slippage          REAL    DEFAULT 20.0,
                priority_fee      REAL    DEFAULT 0.0002,
                max_buys_per_hour INTEGER DEFAULT 5,
                updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS creator_blacklist (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id          INTEGER NOT NULL,
                creator_address  TEXT    NOT NULL,
                note             TEXT    DEFAULT '',
                added_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, creator_address)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS sniper_alert_settings (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL UNIQUE,
                alerts_enabled  INTEGER DEFAULT 1,
                min_score       INTEGER DEFAULT 60,
                updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS trading_wallets (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id        INTEGER NOT NULL UNIQUE,
                wallet_address TEXT    NOT NULL,
                label          TEXT    DEFAULT 'Main',
                added_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await _migrate("ALTER TABLE trading_wallets ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS auto_buy_settings (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id             INTEGER NOT NULL UNIQUE,
                enabled             INTEGER DEFAULT 0,
                kill_switch         INTEGER DEFAULT 0,
                max_buy_size_sol    REAL    DEFAULT 0.05,
                max_buys_per_hour   INTEGER DEFAULT 5,
                score_threshold     INTEGER DEFAULT 45,
                slippage            REAL    DEFAULT 15.0,
                priority_fee        REAL    DEFAULT 0.005,
                cooldown_seconds    INTEGER DEFAULT 60,
                min_initial_buy_sol REAL    DEFAULT 0,
                liq_exit_preset_id  INTEGER DEFAULT NULL,
                min_wallet_balance_sol REAL DEFAULT 0.05,
                daily_spend_limit_sol  REAL DEFAULT 0.0,
                updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS auto_buy_jobs (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                token_address TEXT    NOT NULL,
                status        TEXT    DEFAULT 'pending',
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS submitted_transactions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER,
                signature   TEXT UNIQUE,
                kind        TEXT,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS tracked_positions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                token_address TEXT    NOT NULL,
                status        TEXT    DEFAULT 'open',
                entry_sol     REAL,
                amount_sol    REAL,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await _migrate("ALTER TABLE tracked_positions ADD COLUMN amount_sol REAL")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS cached_token_data (
                token_address TEXT PRIMARY KEY,
                data_json     TEXT,
                updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ── Auto-exit ─────────────────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS auto_exit_settings (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id              INTEGER NOT NULL UNIQUE,
                enabled              INTEGER DEFAULT 0,
                live_mode            INTEGER DEFAULT 1,
                selected_preset_id   INTEGER,
                notifications_enabled INTEGER DEFAULT 1,
                custom_slippage      REAL DEFAULT 15.0,
                custom_priority_fee  REAL DEFAULT 0.005,
                updated_at           TIMESTAMP
            )
        """)
        await _migrate("ALTER TABLE auto_exit_settings ADD COLUMN live_mode INTEGER DEFAULT 1")
        await _migrate("ALTER TABLE auto_exit_settings ADD COLUMN notifications_enabled INTEGER DEFAULT 1")
        await _migrate("ALTER TABLE auto_exit_settings ADD COLUMN custom_slippage REAL DEFAULT 15.0")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS exit_presets (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id              INTEGER,
                name                 TEXT    NOT NULL,
                description          TEXT    DEFAULT '',
                is_system            INTEGER DEFAULT 0,
                tp1_pct              REAL,
                tp1_sell_pct         REAL,
                tp2_pct              REAL,
                tp2_sell_pct         REAL,
                tp3_pct              REAL,
                tp3_sell_pct         REAL,
                moon_bag_pct         REAL    DEFAULT 0,
                sl_pct               REAL,
                trailing_stop_pct    REAL,
                trailing_after_tp    INTEGER DEFAULT 1,
                break_even_after_tp  INTEGER DEFAULT 1,
                max_hold_minutes     INTEGER,
                created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await _migrate("ALTER TABLE exit_presets ADD COLUMN description TEXT DEFAULT ''")
        await _migrate("ALTER TABLE exit_presets ADD COLUMN tp1_pct REAL")
        await _migrate("ALTER TABLE exit_presets ADD COLUMN tp1_sell_pct REAL")
        await _migrate("ALTER TABLE exit_presets ADD COLUMN tp2_pct REAL")
        await _migrate("ALTER TABLE exit_presets ADD COLUMN tp2_sell_pct REAL")
        await _migrate("ALTER TABLE exit_presets ADD COLUMN tp3_pct REAL")
        await _migrate("ALTER TABLE exit_presets ADD COLUMN tp3_sell_pct REAL")
        await _migrate("ALTER TABLE exit_presets ADD COLUMN moon_bag_pct REAL DEFAULT 0")
        await _migrate("ALTER TABLE exit_presets ADD COLUMN sl_pct REAL")
        await _migrate("ALTER TABLE exit_presets ADD COLUMN trailing_stop_pct REAL")
        await _migrate("ALTER TABLE exit_presets ADD COLUMN trailing_after_tp INTEGER DEFAULT 1")
        await _migrate("ALTER TABLE exit_presets ADD COLUMN break_even_after_tp INTEGER DEFAULT 1")
        await _migrate("ALTER TABLE exit_presets ADD COLUMN max_hold_minutes INTEGER")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS position_state (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                position_id        INTEGER,
                user_id            INTEGER NOT NULL,
                token_address      TEXT    NOT NULL,
                entry_price_sol    REAL,
                current_price_sol  REAL,
                highest_price_sol  REAL,
                preset_id          INTEGER,
                status             TEXT    DEFAULT 'watching',
                opened_at          TIMESTAMP,
                data_json          TEXT,
                updated_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await _migrate("ALTER TABLE position_state ADD COLUMN position_id INTEGER")
        await _migrate("ALTER TABLE position_state ADD COLUMN entry_price_sol REAL")
        await _migrate("ALTER TABLE position_state ADD COLUMN current_price_sol REAL")
        await _migrate("ALTER TABLE position_state ADD COLUMN highest_price_sol REAL")
        await _migrate("ALTER TABLE position_state ADD COLUMN preset_id INTEGER")
        await _migrate("ALTER TABLE position_state ADD COLUMN opened_at TIMESTAMP")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS position_events (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER,
                event_type TEXT,
                data_json  TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS sell_executions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER,
                signature     TEXT,
                token_address TEXT,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ── Copy trade ────────────────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS copy_trade_wallets (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id        INTEGER NOT NULL,
                wallet_address TEXT    NOT NULL,
                label          TEXT    DEFAULT '',
                enabled        INTEGER DEFAULT 1,
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, wallet_address)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS copy_trade_settings (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id          INTEGER NOT NULL UNIQUE,
                enabled          INTEGER DEFAULT 0,
                kill_switch      INTEGER DEFAULT 0,
                copy_buys        INTEGER DEFAULT 1,
                copy_sells       INTEGER DEFAULT 1,
                fixed_amount_sol REAL    DEFAULT 0.01,
                slippage         REAL    DEFAULT 15.0,
                priority_fee     REAL    DEFAULT 0.005,
                updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS copy_trade_token_blacklist (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                token_address TEXT    NOT NULL,
                UNIQUE(user_id, token_address)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS copy_trade_token_whitelist (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                token_address TEXT    NOT NULL,
                UNIQUE(user_id, token_address)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS processed_copy_txs (
                signature    TEXT PRIMARY KEY,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS copy_trade_jobs (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                status        TEXT    DEFAULT 'pending',
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS copy_trade_history (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER,
                token_address TEXT,
                side          TEXT,
                amount_sol    REAL,
                signature     TEXT,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ── Wallet scout / discovery ──────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS wallet_scout_settings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL UNIQUE,
                enabled     INTEGER DEFAULT 0,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS discovered_wallets (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet_address  TEXT NOT NULL UNIQUE,
                score           REAL DEFAULT 0,
                meta_json       TEXT,
                discovered_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS wallet_preset_subscriptions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                preset_name TEXT    NOT NULL,
                UNIQUE(user_id, preset_name)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS discovery_runs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                finished_at TIMESTAMP,
                status      TEXT
            )
        """)

        # ── Bot wallets (encrypted) ───────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_wallets (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id               INTEGER NOT NULL UNIQUE,
                wallet_address        TEXT    NOT NULL,
                encrypted_private_key TEXT    NOT NULL,
                created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ── FSM storage ───────────────────────────────────────────────────────
        await db.execute("""
            CREATE TABLE IF NOT EXISTS fsm_states (
                chat_id    INTEGER NOT NULL,
                user_id    INTEGER NOT NULL,
                bot_id     INTEGER NOT NULL,
                state      TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, user_id, bot_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS fsm_data (
                chat_id    INTEGER NOT NULL,
                user_id    INTEGER NOT NULL,
                bot_id     INTEGER NOT NULL,
                data       TEXT DEFAULT '{}',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, user_id, bot_id)
            )
        """)

        await db.commit()
        logger.info("Database initialized — all tables ready.")
