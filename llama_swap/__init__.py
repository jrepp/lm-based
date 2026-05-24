"""llama_swap: Python wrapper for the llama-swap binary.

Provides binary discovery, config generation, and process management
for the https://github.com/mostlygeek/llama-swap hot-swap proxy.
"""

from llama_swap.bin import ensure_binary, find_binary, install_binary
from llama_swap.config import LlamaSwapConfig, build_config
from llama_swap.wrapper import LlamaSwap

__all__ = [
    "ensure_binary",
    "find_binary",
    "install_binary",
    "LlamaSwap",
    "LlamaSwapConfig",
    "build_config",
]
__version__ = "0.1.0"
