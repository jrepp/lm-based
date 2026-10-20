"""Compare the MLX codec with an explicitly supplied, pinned upstream checkout."""

import argparse
import importlib.util
from pathlib import Path
import subprocess
import sys

import mlx.core as mx
import numpy as np
import torch

from .cache import pack

REVISION = "aeaadee10d75b7aa8c4a42a809f15c75d6d3bdc6"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("checkout", type=Path)
    args = parser.parse_args()
    revision = subprocess.check_output(
        ["git", "-C", str(args.checkout), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != REVISION:
        raise SystemExit(f"expected upstream revision {REVISION}, got {revision}")
    # Load the committed source, so worktree modifications cannot silently alter
    # the reference or run unexpected code. This module imports only torch.
    source = subprocess.check_output(
        ["git", "-C", str(args.checkout), "show", f"{REVISION}:flashloop/packing.py"],
        text=True,
    )
    spec = importlib.util.spec_from_loader("flashloop_packing_reference", loader=None)
    reference = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = reference
    exec(compile(source, "upstream/flashloop/packing.py", "exec"), reference.__dict__)
    rng = np.random.default_rng(901)
    cases = 0
    for shape in ((1, 2, 129, 128), (2, 1, 65, 7), (1, 1, 1, 1)):
        for dtype in (np.float16, np.float32):
            x = rng.normal(size=shape).astype(dtype)
            for axis, function in (("key", reference.pack_k_per_channel),
                                   ("value", reference.pack_v_per_token)):
                actual = pack(mx.array(x), axis=axis)
                expected = function(torch.from_numpy(x))
                for field in ("payload", "minimum", "scale"):
                    np.testing.assert_array_equal(np.array(getattr(actual, field)),
                                                  getattr(expected, field).numpy())
                np.testing.assert_allclose(np.array(actual.rows(0, shape[2])),
                                           expected.decode().numpy(), atol=1e-6)
                cases += 1
    print(f"PASS: {cases} MLX/Torch codec comparisons against {REVISION}; Metal={mx.metal.is_available()}")


if __name__ == "__main__":
    main()
