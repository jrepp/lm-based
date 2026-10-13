"""Serve a merged MLX kev decision pack (e.g. RoderickQiu/kev-4b-mlx-8bit).

kev.serve --run only accepts checkpoint directories whose head.pt weights-mode
agrees with the files present: adapter checkpoints (backbone downloaded and
merged at load), or full-weight checkpoints like Kev-27B (meta.weights
"full"). The MLX-8bit conversion ships merged, quantized backbone weights
alongside the canonical adapter-mode head.pt, which Checkpoint.full() rejects.

This shim follows the loading path documented on the artifact card (and used
by Qualm): the canonical checkpoint supplies the metadata (tokenizer base,
pointer head, fitted temperature) while the backbone weights come from the
local merged pack. The model is then handed to kev.serve's own Server and
FastAPI app unchanged, so batching, the state prefix cache, /v1/systemone and
/v1/models behave exactly as upstream.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEFAULT_CHECKPOINT = (
    "jaredpalmer/kev-4b@139fdd94f1b6a6ad80cc15e08fcb99cac885a101"
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Serve a merged MLX kev pack through kev.serve."
    )
    parser.add_argument(
        "--weights",
        required=True,
        type=Path,
        help="Directory with config.json + model.safetensors (merged 8-bit pack).",
    )
    parser.add_argument(
        "--checkpoint",
        default=DEFAULT_CHECKPOINT,
        help="Canonical kev checkpoint supplying head/meta (Hub id[@revision]).",
    )
    parser.add_argument(
        "--kev-repo",
        required=True,
        type=Path,
        help="Path to the kev runtime checkout (provides the kev package).",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8008)
    args = parser.parse_args()

    sys.path.insert(0, str(args.kev_repo))

    from kev import serve as kev_serve
    from kev.checkpoint import Checkpoint
    from kev.mlx_model import MLXDecisionModel, load_base
    from kev.model import PointerHead, load_tokenizer, pad_id

    ck = Checkpoint(args.checkpoint)
    tok = load_tokenizer(ck.meta.base, revision=ck.meta.base_revision)

    # mlx-lm loads the merged, quantized pack directly (config.json carries
    # the quantization block); no adapter merge happens on this path.
    lm = load_base(args.weights)
    model = MLXDecisionModel(lm, pad_id(tok), head_dim=ck.meta.head_dim)
    # The head is sized from the embedding width, which is packed in the
    # quantized weights: size it from the real one (artifact card, "Use").
    model.head = PointerHead(model.text.embed_tokens.dims, dp=ck.meta.head_dim).eval()
    model.head.load_state_dict(ck.meta.head)
    model.head.temperature = ck.meta.temperature

    kev_serve.app.state.server = kev_serve.Server(ck, tok, model, "mps")
    print(
        f"serving merged mlx pack {args.weights} (meta {ck.requested}) on mps via "
        f"{model.backend} ({model.dtype}) {args.host}:{args.port}"
    )
    import uvicorn

    uvicorn.run(kev_serve.app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
