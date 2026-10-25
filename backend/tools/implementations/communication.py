"""
Backward-compatibility proxy re-exporting from standalone tools packages.
"""

from tools.take_message import (
    TakeMessageInput,
    handle_take_message,
)
from tools.transfer_call import (
    TransferCallInput,
    handle_transfer_call,
)

__all__ = [
    "TakeMessageInput",
    "TransferCallInput",
    "handle_take_message",
    "handle_transfer_call",
]
