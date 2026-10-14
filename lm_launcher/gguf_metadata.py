"""Read key/value metadata from a GGUF header without loading tensors.

Only the header is parsed (arrays such as the tokenizer vocabulary are skipped),
so this is cheap even for multi-GB or sharded files; pass the first shard.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any, BinaryIO

GGUF_MAGIC = b"GGUF"

# GGUF value types -> struct format for scalars.
_SCALARS = {
    0: "<B",  # uint8
    1: "<b",  # int8
    2: "<H",  # uint16
    3: "<h",  # int16
    4: "<I",  # uint32
    5: "<i",  # int32
    6: "<f",  # float32
    7: "<?",  # bool
    10: "<Q",  # uint64
    11: "<q",  # int64
    12: "<d",  # float64
}
_STRING = 8
_ARRAY = 9


def _read(f: BinaryIO, fmt: str) -> Any:
    size = struct.calcsize(fmt)
    data = f.read(size)
    if len(data) != size:
        raise ValueError("truncated GGUF header")
    return struct.unpack(fmt, data)[0]


def _read_string(f: BinaryIO) -> str:
    length = _read(f, "<Q")
    return f.read(length).decode("utf-8", errors="replace")


def _read_value(f: BinaryIO, value_type: int, keep: bool) -> Any:
    if value_type in _SCALARS:
        return _read(f, _SCALARS[value_type])
    if value_type == _STRING:
        return _read_string(f)
    if value_type == _ARRAY:
        item_type = _read(f, "<I")
        count = _read(f, "<Q")
        if item_type in _SCALARS and not keep:
            f.seek(struct.calcsize(_SCALARS[item_type]) * count, 1)
            return None
        items = [_read_value(f, item_type, keep) for _ in range(count)]
        return items if keep else None
    raise ValueError(f"unknown GGUF value type {value_type}")


def read_metadata(path: Path, keys: set[str] | None = None) -> dict[str, Any]:
    """Return header metadata; with `keys`, only those keys (arrays are never kept)."""
    out: dict[str, Any] = {}
    with Path(path).open("rb") as f:
        if f.read(4) != GGUF_MAGIC:
            raise ValueError(f"{path} is not a GGUF file")
        version = _read(f, "<I")
        if version < 2:
            raise ValueError(f"{path}: GGUF v{version} is not supported")
        _read(f, "<Q")  # tensor count
        kv_count = _read(f, "<Q")
        for _ in range(kv_count):
            key = _read_string(f)
            value_type = _read(f, "<I")
            wanted = keys is None or key in keys
            value = _read_value(f, value_type, keep=False)
            if wanted and value is not None:
                out[key] = value
    return out


def context_length(path: Path) -> int | None:
    """The model's training context (`<arch>.context_length`) from a GGUF header."""
    meta = read_metadata(path)
    arch = meta.get("general.architecture")
    value = meta.get(f"{arch}.context_length") if arch else None
    return int(value) if isinstance(value, int) else None
