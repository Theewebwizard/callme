"""
Backward-compatibility proxy re-exporting from the standalone 'tools.registry' package.
"""

from tools.registry import (
    ToolRegistry,
    build_default_tool_registry,
    get_tool_registry,
)

__all__ = [
    "ToolRegistry",
    "build_default_tool_registry",
    "get_tool_registry",
]
