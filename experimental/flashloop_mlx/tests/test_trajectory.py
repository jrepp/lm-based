import copy
import unittest

from experimental.flashloop_mlx.trajectory import validate


class TrajectoryTests(unittest.TestCase):
    def fixture(self):
        receipts = []
        for step in range(2):
            for loop, rows in enumerate(([100, 100, 25, 10] if step == 0 else [1] * 4), 1):
                receipts.append({
                    "phase": "prefill" if step == 0 else "decode",
                    "position": 0 if step == 0 else 100, "loop": loop,
                    "active_rows": rows, "qkv_rows": rows * 6, "mlp_rows": rows * 2,
                    "selected_keys_per_head": 11 if step and loop >= 3 else 0,
                    "next_token": 20 + step, "hidden_delta_rms": 0.1,
                    "next_token_entropy": 2.5,
                })
        return receipts

    def check(self, receipts, completion="437 - 58 = 379.</think>\nAnswer: 379"):
        return validate(receipts, [20, 21], completion, prompt_tokens=100, layers=2, flash=True)

    def test_valid_trace(self):
        self.assertTrue(all(self.check(self.fixture()).values()))

    def test_answer_does_not_hide_runtime_failures(self):
        for field, value, check in (
            ("next_token", 99, "emitted_tokens_match_loop4"),
            ("loop", 3, "all_steps_have_four_loops"),
            ("position", 101, "positions_and_phases_valid"),
            ("qkv_rows", 0, "projection_counts_consistent"),
            ("selected_keys_per_head", 0, "sparse_execution_observed"),
            ("hidden_delta_rms", float("nan"), "finite_loop_metrics"),
        ):
            records = copy.deepcopy(self.fixture())
            records[-1][field] = value
            self.assertFalse(self.check(records)[check], field)

    def test_requires_complete_thinking_and_unambiguous_answer(self):
        self.assertFalse(self.check(self.fixture(), "Answer: 379")["thinking_closed"])
        self.assertFalse(self.check(self.fixture(), "</think>Answer: 379\nAnswer: 380")["answer_correct"])
        self.assertFalse(self.check([])["all_steps_have_four_loops"])
