from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lm_launcher.service_endpoints import DEFAULT_SWAP_LISTEN, swap_api_base, swap_listen


class ServiceEndpointTests(unittest.TestCase):
    def test_reads_swap_listen_from_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            policy = Path(temporary) / "serve-policy.yaml"
            policy.write_text('{"ingress": {"swap_listen": "127.0.0.1:9001"}}')

            self.assertEqual(swap_listen(policy), "127.0.0.1:9001")
            self.assertEqual(swap_api_base(policy), "http://127.0.0.1:9001/v1")

    def test_invalid_policy_uses_default(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            policy = Path(temporary) / "missing.json"

            self.assertEqual(swap_listen(policy), DEFAULT_SWAP_LISTEN)


if __name__ == "__main__":
    unittest.main()
