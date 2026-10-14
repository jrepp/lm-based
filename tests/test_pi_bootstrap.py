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

    def test_swap_service_selects_policy_internal_endpoint(self) -> None:
        state = pi_bootstrap.service_state("lm-based", frozenset({"llama-swap"}))

        self.assertEqual(state.endpoint, "http://127.0.0.1:8081/v1")

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

    def test_qwen36_profile_is_marked_as_reasoning(self) -> None:
        sidecar = pi_bootstrap.load_sidecars()["qwen36-27b-q6k"]

        self.assertTrue(pi_bootstrap.model_supports_reasoning(sidecar))

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
        self.assertEqual(settings["packages"], [str(path) for path in pi_bootstrap.PI_PACKAGES])
        self.assertFalse(settings["enableInstallTelemetry"])

    def test_managed_packages_merge_without_duplicates(self) -> None:
        managed = (Path("/repo/support/pi/node_modules/pi-subagents"),)
        merged = pi_bootstrap.merge_packages(["npm:other", str(managed[0])], managed)
        self.assertEqual(merged, ["npm:other", str(managed[0])])
        self.assertEqual(pi_bootstrap.merge_packages(None, managed), [str(managed[0])])

    def test_no_default_still_registers_packages(self) -> None:
        sidecar = pi_bootstrap.load_sidecars()["ternary-bonsai-27b-mlx-2bit"]
        state = pi_bootstrap.ServiceState(
            services=frozenset({"model:ternary-bonsai-27b-mlx-2bit"}),
            model_slugs=("ternary-bonsai-27b-mlx-2bit",),
            endpoint="http://127.0.0.1:8001/v1",
        )
        plan = pi_bootstrap.build_plan("lm-based", None, state, (sidecar,))
        with tempfile.TemporaryDirectory() as temporary:
            agent_dir = Path(temporary)
            pi_bootstrap.configure_pi(plan, agent_dir, set_default=False)
            settings = json.loads((agent_dir / "settings.json").read_text())
        self.assertNotIn("defaultModel", settings)
        self.assertEqual(len(settings["packages"]), len(pi_bootstrap.PI_PACKAGES))

    def test_missing_pinned_install_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "pi"
            with self.assertRaises(pi_bootstrap.PiInstallError) as raised:
                pi_bootstrap.check_pi_install(missing, ())
        self.assertIn("just pi-install", raised.exception.hint)

    def test_pi_environment_isolates_agent_dir(self) -> None:
        env = pi_bootstrap.pi_environment(Path("/tmp/agent"), {"PATH": "/bin"})
        self.assertEqual(env["PI_CODING_AGENT_DIR"], str(Path("/tmp/agent").resolve()))
        self.assertEqual(env["PI_SKIP_VERSION_CHECK"], "1")
        self.assertEqual(env["PI_TELEMETRY"], "0")
        self.assertEqual(env["PATH"], "/bin")

    def test_swap_states_join_models_with_running(self) -> None:
        payload = {"running": [{"model": "qwen3-coder-next-q6k", "state": "ready"}]}

        def opener(request, timeout):
            self.assertEqual(request.full_url, "http://127.0.0.1:8081/running")
            return io.BytesIO(json.dumps(payload).encode())

        states = pi_bootstrap.swap_model_states(
            "http://127.0.0.1:8081/v1",
            ["qwen3-coder-next-q6k", "qwen36-27b-q6k"],
            1.0,
            opener=opener,
        )
        self.assertEqual(states, {"qwen3-coder-next-q6k": "ready", "qwen36-27b-q6k": "unloaded"})

    def test_swap_states_reject_non_swap_endpoint(self) -> None:
        with self.assertRaises(pi_bootstrap.BootstrapError):
            pi_bootstrap.swap_model_states(
                "http://127.0.0.1:8001/v1", ["x"], 1.0, opener=lambda request, timeout: io.BytesIO(b"{}")
            )

    def test_swap_plan_defaults_to_loaded_model(self) -> None:
        sidecars = pi_bootstrap.load_sidecars()
        state = pi_bootstrap.ServiceState(
            services=frozenset({"llama-swap"}), model_slugs=(), endpoint="http://127.0.0.1:8081/v1"
        )
        resolved = (sidecars["qwen3-coder-next-q6k"], sidecars["qwen36-27b-q6k"])
        states = {"qwen3-coder-next-q6k": "unloaded", "qwen36-27b-q6k": "ready"}
        plan = pi_bootstrap.build_plan("lm-based", None, state, resolved, states)
        self.assertEqual(plan.selected_model, "qwen36-27b-q6k")
        cold = dict.fromkeys(states, "unloaded")
        self.assertEqual(
            pi_bootstrap.build_plan("lm-based", None, state, resolved, cold).selected_model,
            "qwen3-coder-next-q6k",
        )
        self.assertEqual(
            pi_bootstrap.build_plan("lm-based", None, state, resolved, cold, "qwen36-27b-q6k").selected_model,
            "qwen36-27b-q6k",
        )

        env = pi_bootstrap.pi_environment(Path("/tmp/agent"), {}, plan)
        self.assertEqual(env["LM_BASED_SWAP_URL"], "http://127.0.0.1:8081")
        self.assertEqual(env["LM_BASED_PROVIDER"], "lm-based")
        self.assertNotIn("LM_BASED_SWAP_URL", pi_bootstrap.pi_environment(Path("/tmp/agent"), {}))

    def test_decision_models_are_not_chat_models(self) -> None:
        sidecars = pi_bootstrap.load_sidecars()
        state = pi_bootstrap.ServiceState(
            services=frozenset({"llama-swap"}), model_slugs=(), endpoint="http://127.0.0.1:8081/v1"
        )
        resolved = pi_bootstrap.resolve_sidecars(state, ["kev-4b-mlx-8bit", "qwen36-27b-q6k"], sidecars)
        self.assertEqual([sidecar.slug for sidecar in resolved], ["qwen36-27b-q6k"])

    def test_no_arguments_prefers_llama_swap_then_falls_back_to_tmux(self) -> None:
        args = pi_bootstrap.build_parser().parse_args([])
        swap_state = pi_bootstrap.ServiceState(
            services=frozenset({"llama-swap"}), model_slugs=(), endpoint="http://127.0.0.1:8081/v1"
        )
        direct_state = pi_bootstrap.ServiceState(
            services=frozenset({"model:qwen36-27b-q6k"}),
            model_slugs=("qwen36-27b-q6k",),
            endpoint="http://127.0.0.1:8001/v1",
        )
        original = (pi_bootstrap.swap_service, pi_bootstrap.service_state, pi_bootstrap.running_services,
                    pi_bootstrap.endpoint_model_ids)

        def swap_down(timeout):
            raise pi_bootstrap.BootstrapError("down")

        try:
            pi_bootstrap.running_services = lambda session: frozenset()
            pi_bootstrap.service_state = lambda session, services: direct_state
            pi_bootstrap.endpoint_model_ids = lambda endpoint, timeout: ["qwen36-27b-q6k"]
            pi_bootstrap.swap_service = lambda timeout: (swap_state, ["qwen36-27b-q6k"], {"qwen36-27b-q6k": "ready"})
            self.assertEqual(pi_bootstrap.derive_plan(args).endpoint, swap_state.endpoint)

            pi_bootstrap.swap_service = swap_down
            plan = pi_bootstrap.derive_plan(args)
            self.assertEqual(plan.endpoint, direct_state.endpoint)
            self.assertIsNone(plan.swap_states)

            with self.assertRaises(pi_bootstrap.BootstrapError):
                pi_bootstrap.derive_plan(pi_bootstrap.build_parser().parse_args(["--swap"]))
        finally:
            (pi_bootstrap.swap_service, pi_bootstrap.service_state, pi_bootstrap.running_services,
             pi_bootstrap.endpoint_model_ids) = original

    def test_decision_models_become_classifiers_via_swap_upstream(self) -> None:
        sidecars = pi_bootstrap.load_sidecars()
        state = pi_bootstrap.ServiceState(
            services=frozenset({"llama-swap"}), model_slugs=(), endpoint="http://127.0.0.1:8081/v1"
        )
        api_ids = ["kev-4b-mlx-8bit", "qwen36-27b-q6k"]
        classifiers = pi_bootstrap.resolve_classifiers(api_ids, sidecars)
        plan = pi_bootstrap.build_plan(
            "lm-based",
            None,
            state,
            pi_bootstrap.resolve_sidecars(state, api_ids, sidecars),
            {"kev-4b-mlx-8bit": "ready", "qwen36-27b-q6k": "ready"},
            classifiers=classifiers,
        )
        (kev,) = plan.classifiers
        self.assertEqual(kev["type"], "classifier")
        self.assertEqual(kev["api"], "typesafe-system-one")
        self.assertEqual(kev["baseUrl"], "http://127.0.0.1:8081/upstream/kev-4b-mlx-8bit/v1")
        # models.json cannot carry classifiers: they go to the decide extension via the environment.
        self.assertNotIn("kev-4b-mlx-8bit", [m["id"] for m in pi_bootstrap.provider_config(plan)["models"]])
        env = pi_bootstrap.pi_environment(Path("/tmp/agent"), {}, plan)
        self.assertEqual(json.loads(env["LM_BASED_CLASSIFIERS"])[0]["id"], "kev-4b-mlx-8bit")

    def test_pi_flags_are_not_abbreviated_into_bootstrap_options(self) -> None:
        args, rest = pi_bootstrap.build_parser().parse_known_args(["--mode", "json", "-p", "hi"])
        self.assertIsNone(args.model)
        self.assertEqual(rest, ["--mode", "json", "-p", "hi"])


if __name__ == "__main__":
    unittest.main()
