"""
utils/states.py
===============
FSM state groups used by live modules.
"""

from aiogram.fsm.state import State, StatesGroup


class LinkWalletState(StatesGroup):
    """FSM for linking a Solana wallet to a Telegram account."""
    waiting_address = State()


class WithdrawState(StatesGroup):
    """FSM for withdrawing SOL from the bot wallet to an external address."""
    waiting_address = State()
    waiting_amount  = State()


class AutoExitFSM(StatesGroup):
    """FSM states for the Auto-Exit Manager (defined in auto_exit.py AEState)."""
    clone_name  = State()
    edit_field  = State()
