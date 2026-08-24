from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from lm_launcher import pi_bootstrap


class PiBootstrapTests(unittest.TestCase):
    def test_endpoint_models_rejects_invalid_response_shape(self) -> None:
        class Response(io.BytesIO):
            def __enter__(self) -> "Response":
                return self

            def __exit__(self, *args: object) -> None:
                self.close()

        def opener(*args: object, **kwargs: object) -> Response:
            del args, kwargs
            return Response(b'{"data": {"id": "demo"}}')

        with self.assertRaisesRegex(pi_bootstrap.BootstrapError, "invalid response"):
            pi_bootstrap.endpoint_model_ids("http://127.0.0.1:8001/v1", 1.0, opener=opener)

    def test_sampler_service_selects_proxy_endpoint(self) -> None:
        state = pi_bootstrap.service_state(
            "lm-based",
            frozenset({"model:demo", "sampler-proxy"}),
        )

        self.assertEqual(state.endpoint, "http://127.0.0.1:8002/v1")
        self.assertEqual(state.model_slugs, ("demo",))

    def test_running_services_requires_owned_live_shim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            service = Path(temporary) / "model:demo"
            service.mkdir()
            (service / "session").write_text("lm-based\n")
            (service / "status").write_text("2026-07-17T00:00:00Z running\n")
            (service / "shim.pid").write_text("42\n")

            def runner(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
                command = args[0]
                del kwargs
                if command[0] == "tmux":
                    return subprocess.CompletedProcess([], 0, stdout="0|42\n", stderr="")
                return subprocess.CompletedProcess(
                    [],
                    0,
                    stdout=f"{pi_bootstrap.ROOT}/support/tmux-service-shim model:demo",
                    stderr="",
                )

            services = pi_bootstrap.running_services(
                "lm-based",
                services_dir=Path(temporary),
                runner=runner,
            )

        self.assertEqual(services, frozenset({"model:demo"}))

    def test_orphaned_shim_is_not_treated_as_running_service(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            service = Path(temporary) / "model:demo"
            service.mkdir()
            (service / "session").write_text("lm-based\n")
            (service / "status").write_text("2026-07-17T00:00:00Z running\n")
            (service / "shim.pid").write_text("42\n")

            def runner(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
                del args, kwargs
                return subprocess.CompletedProcess([], 1, stdout="", stderr="missing session")

            services = pi_bootstrap.running_services(
                "lm-based",
                services_dir=Path(temporary),
                runner=runner,
            )

        self.assertEqual(services, frozenset())

    def test_mlx_api_path_matches_sidecar(self) -> None:
        sidecar = pi_bootstrap.load_sidecars()["ternary-bonsai-27b-mlx-2bit"]
        api_id = str(pi_bootstrap.ROOT / "Ternary-Bonsai-27B-MLX-2bit")

        self.assertTrue(pi_bootstrap.api_id_matches_sidecar(api_id, sidecar))

    def test_provider_uses_pi_openai_and_thinking_compatibility(self) -> None:
        sidecar = pi_bootstrap.load_sidecars()["ternary-bonsai-27b-mlx-2bit"]
        state = pi_bootstrap.ServiceState(
            services=frozenset({"model:ternary-bonsai-27b-mlx-2bit", "sampler-proxy"}),
            model_slugs=("ternary-bonsai-27b-mlx-2bit",),
            endpoint="http://127.0.0.1:8002/v1",
        )
        plan = pi_bootstrap.build_plan("lm-based", None, state, (sidecar,))

        provider = pi_bootstrap.provider_config(plan)

        self.assertEqual(provider["api"], "openai-completions")
        self.assertEqual(provider["baseUrl"], "http://127.0.0.1:8002/v1")
        self.assertEqual(provider["models"][0]["contextWindow"], 262144)
        self.assertEqual(
            provider["models"][0]["compat"]["thinkingFormat"],
            "qwen-chat-template",
        )

    def test_configuration_preserves_unrelated_pi_settings(self) -> None:
        sidecar = pi_bootstrap.load_sidecars()["ternary-bonsai-27b-mlx-2bit"]
        state = pi_bootstrap.ServiceState(
            services=frozenset({"model:ternary-bonsai-27b-mlx-2bit"}),
            model_slugs=("ternary-bonsai-27b-mlx-2bit",),
            endpoint="http://127.0.0.1:8001/v1",
        )
        plan = pi_bootstrap.build_plan("lm-based", None, state, (sidecar,))
        with tempfile.TemporaryDirectory() as temporary:
            agent_dir = Path(temporary)
            (agent_dir / "models.json").write_text(json.dumps({"providers": {"cloud": {"models": []}}}))
            (agent_dir / "settings.json").write_text(json.dumps({"theme": "dark"}))

            changed = pi_bootstrap.configure_pi(plan, agent_dir, set_default=True)
            models = json.loads((agent_dir / "models.json").read_text())
            settings = json.loads((agent_dir / "settings.json").read_text())

        self.assertEqual(changed, (True, True))
        self.assertIn("cloud", models["providers"])
        self.assertIn("lm-based", models["providers"])
        self.assertEqual(settings["theme"], "dark")
        self.assertEqual(settings["defaultProvider"], "lm-based")
        self.assertEqual(settings["defaultModel"], "ternary-bonsai-27b-mlx-2bit")


if __name__ == "__main__":
    unittest.main()
