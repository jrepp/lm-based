"""Batch-one Ouro/FlashLoop MLX correctness engine.

Port of the pinned FlashLoop execution contracts. Sparse late-loop rows execute
only selected projections/MLPs. Late-loop Metal reads reconstruct selected rows;
earlier loops retain full-history attention.
"""

import json
import math
from pathlib import Path

import mlx.core as mx

from .cache import CrossLoopCache
from .selected_kv import gather_selected


class DenseCache:
    def __init__(self, keys, values):
        self.keys, self.values = keys, values
        self.shape = keys[0].shape

    def rows(self, loop, start, end):
        return self.keys[loop][:, :, start:end], self.values[loop][:, :, start:end]

    def append(self, keys, values):
        return DenseCache([mx.concatenate((a, b), axis=2) for a, b in zip(self.keys, keys)],
                          [mx.concatenate((a, b), axis=2) for a, b in zip(self.values, values)])

    @property
    def storage_bytes(self):
        return sum(x.nbytes for x in (*self.keys, *self.values))


def select_rows(current, previous, fraction, eligible):
    scores = mx.sqrt(mx.sum((current.astype(mx.float32) - previous.astype(mx.float32)) ** 2, axis=-1))
    scores /= mx.maximum(mx.sqrt(mx.sum(current.astype(mx.float32) ** 2, axis=-1)), 1e-12)
    budget = min(len(eligible), max(1, math.ceil(current.shape[1] * fraction)))
    last = current.shape[1] - 1
    candidates = [p for p in eligible if p != last]
    chosen = []
    if budget > 1:
        order = mx.argsort(-scores[0, mx.array(candidates)])
        chosen = [candidates[i] for i in order[:budget - 1].tolist()]
    return sorted(chosen + [last])


def normalize(x, weight, epsilon):
    dtype = x.dtype
    work = x.astype(mx.float32)
    normalized = work * mx.rsqrt(mx.mean(work * work, axis=-1, keepdims=True) + epsilon)
    return normalized.astype(dtype) * weight


def gated_activation(gate, up):
    return (gate * mx.sigmoid(gate)) * up


compiled_normalize = mx.compile(normalize)
compiled_gated_activation = mx.compile(gated_activation)


class OuroEngine:
    def __init__(self, config, weights, *, flash=True, observer=None, selected_reads=True,
                 eval_every=8, compiled_ops=False):
        self.config, self.weights, self.flash = config, weights, flash
        if isinstance(eval_every, bool) or not isinstance(eval_every, int) or not 1 <= eval_every <= 48:
            raise ValueError("eval_every must be an integer in 1..48")
        self.eval_every = eval_every
        self.compiled_ops = compiled_ops
        self.observer = observer
        self.selected_reads = flash and selected_reads and mx.default_device() == mx.gpu
        if (config["model_type"] != "ouro" or config["total_ut_steps"] != 4
                or config["num_attention_heads"] != config["num_key_value_heads"]
                or config.get("rope_scaling") is not None
                or config.get("sliding_window") is not None):
            raise ValueError("requires four-loop, MHA Ouro with default full-attention RoPE")
        self.heads, self.dim = config["num_attention_heads"], config["head_dim"]
        self.layers = config["num_hidden_layers"]
        self.cache = None
        self.position = 0
        self.receipts = []

    @classmethod
    def load(cls, model, **kwargs):
        model = Path(model)
        config = json.loads((model / "config.json").read_text())
        weights = {}
        for path in sorted(model.glob("*.safetensors")):
            weights.update(mx.load(str(path)))
        if not weights:
            raise ValueError("no local safetensors weights")
        mx.eval(weights)
        return cls(config, weights, **kwargs)

    def linear(self, x, name):
        return x @ self.weights[name + ".weight"].T

    def norm(self, x, name):
        operation = compiled_normalize if self.compiled_ops else normalize
        return operation(x, self.weights[name + ".weight"], self.config["rms_norm_eps"])

    def qkv(self, x, layer, positions):
        prefix = f"model.layers.{layer}.self_attn"
        q, k, v = [self.linear(x, prefix + "." + name + "_proj").reshape(
            1, x.shape[1], self.heads, self.dim).transpose(0, 2, 1, 3)
            for name in ("q", "k", "v")]
        freq = self.config["rope_theta"] ** (-mx.arange(0, self.dim, 2, dtype=mx.float32) / self.dim)
        angle = mx.array(positions, dtype=mx.float32)[:, None] * freq
        angle = mx.concatenate((angle, angle), axis=-1)[None, None]
        cos, sin = mx.cos(angle).astype(q.dtype), mx.sin(angle).astype(q.dtype)
        def rotate(t):
            half = self.dim // 2
            return t * cos + mx.concatenate((-t[..., half:], t[..., :half]), axis=-1) * sin
        return rotate(q), rotate(k), v

    def attention(self, q, k, v, positions=None):
        logits = (q.astype(mx.float32) @ mx.swapaxes(k.astype(mx.float32), -1, -2)) / math.sqrt(self.dim)
        if positions is not None:
            allowed = mx.arange(k.shape[2])[None, :] <= mx.array(positions)[:, None]
            logits = mx.where(allowed[None, None], logits, -float("inf"))
        weights = mx.softmax(logits, axis=-1)
        return (weights @ v.astype(mx.float32)).astype(q.dtype), weights

    def finish_layer(self, hidden, projected, layer):
        prefix = f"model.layers.{layer}"
        hidden = hidden + self.norm(projected, prefix + ".input_layernorm_2")
        mlp_in = self.norm(hidden, prefix + ".post_attention_layernorm")
        gate = self.linear(mlp_in, prefix + ".mlp.gate_proj")
        up = self.linear(mlp_in, prefix + ".mlp.up_proj")
        activation = compiled_gated_activation if self.compiled_ops else gated_activation
        out = self.linear(activation(gate, up), prefix + ".mlp.down_proj")
        return hidden + self.norm(out, prefix + ".post_attention_layernorm_2")

    def project_attention(self, attention, layer):
        return self.linear(attention.transpose(0, 2, 1, 3).reshape(1, attention.shape[2], -1),
                           f"model.layers.{layer}.self_attn.o_proj")

    def receipt(self, hidden, previous, loop, phase, rows, selected=0):
        delta = mx.sqrt(mx.mean((hidden.astype(mx.float32) - previous.astype(mx.float32)) ** 2))
        logits = self.linear(hidden[:, -1:], "lm_head").astype(mx.float32)
        probs = mx.softmax(logits, axis=-1)
        entropy = -mx.sum(probs * mx.log(mx.maximum(probs, 1e-30)))
        mx.eval(delta, logits, entropy)
        self.receipts.append({"phase": phase, "position": self.position, "loop": loop + 1,
                              "active_rows": rows, "qkv_rows": rows * self.layers * 3,
                              "mlp_rows": rows * self.layers, "selected_keys_per_head": selected,
                              "hidden_delta_rms": delta.item(), "next_token": mx.argmax(logits).item(),
                              "next_token_entropy": entropy.item()})
        if self.observer is not None:
            self.observer(self.receipts[-1])
        return logits

    def prefill(self, tokens):
        if self.cache is not None or not tokens:
            raise ValueError("prefill needs a fresh engine and nonempty tokens")
        hidden = self.weights["model.embed_tokens.weight"][mx.array([tokens])]
        length = len(tokens)
        positions = list(range(length))
        snapshots_k, snapshots_v = [[] for _ in range(self.layers)], [[] for _ in range(self.layers)]
        previous_loop = None
        for loop in range(4):
            if self.flash and loop >= 2:
                positions = select_rows(hidden, previous_loop, 0.25 if loop == 2 else 0.10, positions)
            previous_loop = hidden
            indices = mx.array(positions)
            for layer in range(self.layers):
                active = hidden[:, indices]
                q, k, v = self.qkv(self.norm(active, f"model.layers.{layer}.input_layernorm"), layer, positions)
                if len(positions) != length:
                    full_k, full_v = mx.array(snapshots_k[layer][-1]), mx.array(snapshots_v[layer][-1])
                    full_k[:, :, indices, :] = k
                    full_v[:, :, indices, :] = v
                else:
                    full_k, full_v = k, v
                attn, _ = self.attention(q, full_k, full_v, positions)
                updated = self.finish_layer(active, self.project_attention(attn, layer), layer)
                hidden = mx.array(hidden)
                hidden[:, indices] = updated
                snapshots_k[layer].append(full_k)
                snapshots_v[layer].append(full_v)
                mx.eval(hidden, full_k, full_v)
            normalized = self.norm(hidden[:, indices], "model.norm")
            hidden = mx.array(hidden)
            hidden[:, indices] = normalized
            logits = self.receipt(hidden, previous_loop, loop, "prefill", len(positions))
        self.cache = [(CrossLoopCache.from_loops(k, v) if self.flash else DenseCache(k, v))
                      for k, v in zip(snapshots_k, snapshots_v)]
        self.position = length
        return logits

    def decode(self, token):
        if self.cache is None:
            raise ValueError("prefill first")
        hidden = self.weights["model.embed_tokens.weight"][mx.array([[token]])]
        new_k, new_v = [[] for _ in range(self.layers)], [[] for _ in range(self.layers)]
        sources = {}
        for loop in range(4):
            previous = hidden
            selected = 0
            for layer in range(self.layers):
                q, k, v = self.qkv(self.norm(hidden, f"model.layers.{layer}.input_layernorm"),
                                    layer, [self.position])
                new_k[layer].append(k)
                new_v[layer].append(v)
                if not (self.flash and loop >= 2 and self.selected_reads):
                    old_k, old_v = self.cache[layer].rows(loop, 0, self.position)
                    full_k, full_v = mx.concatenate((old_k, k), axis=2), mx.concatenate((old_v, v), axis=2)
                if self.flash and loop >= 2:
                    indices, mass, selected_output, projected_source = sources[layer]
                    if self.selected_reads:
                        target_k, target_v = gather_selected(self.cache[layer], loop, indices, k, v)
                    else:
                        gather = mx.broadcast_to(indices[..., None], (1, self.heads, indices.shape[-1], self.dim))
                        target_k = mx.take_along_axis(full_k, gather, axis=2)
                        target_v = mx.take_along_axis(full_v, gather, axis=2)
                    target, _ = self.attention(q, target_k, target_v)
                    correction = mass * (target.astype(mx.float32) - selected_output)
                    projected = projected_source + self.project_attention(correction.astype(q.dtype), layer)
                    selected = indices.shape[-1]
                else:
                    attn, probabilities = self.attention(q, full_k, full_v)
                    projected = self.project_attention(attn, layer)
                    if self.flash and loop == 1:
                        budget = max(1, math.ceil((self.position + 1) * 0.10))
                        indices = mx.sort(mx.argsort(-probabilities[:, :, 0], axis=-1)[..., :budget], axis=-1)
                        weights = mx.take_along_axis(probabilities[:, :, 0], indices, axis=-1)
                        mass = mx.sum(weights, axis=-1, keepdims=True)[..., None]
                        gather = mx.broadcast_to(indices[..., None], (1, self.heads, budget, self.dim))
                        selected_v = mx.take_along_axis(full_v, gather, axis=2).astype(mx.float32)
                        selected_output = (weights[..., None, :] / mass) @ selected_v
                        sources[layer] = (indices, mass, selected_output, projected)
                hidden = self.finish_layer(hidden, projected, layer)
                if (layer + 1) % self.eval_every == 0:
                    mx.eval(hidden)
            hidden = self.norm(hidden, "model.norm")
            logits = self.receipt(hidden, previous, loop, "decode", 1, selected)
        self.cache = [cache.append(k, v) for cache, k, v in zip(self.cache, new_k, new_v)]
        self.position += 1
        return logits
