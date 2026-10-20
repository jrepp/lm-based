"""Validate runtime evidence independently of the model's written explanation."""

import math
import re


def validate(receipts, generated, completion, *, prompt_tokens, layers, flash):
    groups = [receipts[i:i + 4] for i in range(0, len(receipts), 4)]
    structure = bool(generated) and len(groups) == len(generated)
    structure = structure and all([r["loop"] for r in group] == [1, 2, 3, 4] for group in groups)
    token_alignment = structure and all(group[-1]["next_token"] == token
                                       for group, token in zip(groups, generated))
    positions = structure and all(
        all(r["phase"] == ("prefill" if i == 0 else "decode")
            and r["position"] == (0 if i == 0 else prompt_tokens + i - 1) for r in group)
        for i, group in enumerate(groups))
    counts = structure and all(
        r["qkv_rows"] == 3 * layers * r["active_rows"] and r["mlp_rows"] == layers * r["active_rows"]
        for r in receipts)
    sparse = True
    if flash and structure:
        expected = [prompt_tokens, prompt_tokens, math.ceil(prompt_tokens * 0.25),
                    math.ceil(prompt_tokens * 0.10)]
        sparse = [r["active_rows"] for r in groups[0]] == expected
        sparse = sparse and all(group[2]["selected_keys_per_head"] > 0
                                and group[3]["selected_keys_per_head"] > 0 for group in groups[1:])
    final = completion.split("</think>", 1)[-1]
    answers = re.findall(r"Answer:\s*(\d+)", final)
    return {
        "answer_correct": answers == [str(19 * 23 - 58)],
        "thinking_closed": completion.count("</think>") == 1,
        "all_steps_have_four_loops": structure,
        "emitted_tokens_match_loop4": token_alignment,
        "positions_and_phases_valid": positions,
        "projection_counts_consistent": counts,
        "sparse_execution_observed": sparse,
        "finite_loop_metrics": bool(receipts) and all(
            math.isfinite(r[k]) for r in receipts for k in ("hidden_delta_rms", "next_token_entropy")),
    }
