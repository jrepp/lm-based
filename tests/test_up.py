from __future__ import annotations

import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load_up_module() -> types.ModuleType:
    module = types.ModuleType("up_script")
    module.__file__ = str(ROOT / "up")
    sys.modules[module.__name__] = module
    code = compile((ROOT / "up").read_text(), str(ROOT / "up"), "exec")
    exec(code, module.__dict__)
    return module


class UpResolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.up = load_up_module()

    def test_dashboard_depends_on_stats_poll(self) -> None:
        registry = self.up.build_registry()
        plan = self.up.resolve_target("dashboard", registry)
        self.assertEqual([service.name for service in plan.services], ["stats-poll", "dashboard"])

    def test_model_slug_runs_only_the_worker(self) -> None:
        # Observability needs Go; it is opt-in with `./up observability --add`.
        registry = self.up.build_registry()
        slug = "qwen36-27b-mtp-ud-q5k-xl"
        plan = self.up.resolve_target(slug, registry)
        self.assertEqual([service.name for service in plan.services], [f"model:{slug}"])
        self.assertEqual(plan.services[0].env["MODEL_SLUG"], slug)
        # The binary is machine config (.env), not something ./up pins per model.
        self.assertNotIn("LLAMA_SERVER_BIN", plan.services[0].env)

    def test_mlx_slug_includes_sampler_proxy(self) -> None:
        registry = self.up.build_registry()
        slug = "ternary-bonsai-27b-mlx-2bit"
        plan = self.up.resolve_target(slug, registry)
        self.assertEqual(
            [service.name for service in plan.services],
            [f"model:{slug}", "sampler-proxy"],
        )

    def test_gguf_slug_omits_sampler_proxy(self) -> None:
        registry = self.up.build_registry()
        slug = "qwen36-27b-mtp-ud-q5k-xl"
        plan = self.up.resolve_target(slug, registry)
        self.assertNotIn("sampler-proxy", [service.name for service in plan.services])

    def test_direct_runs_model_slug_from_environment(self) -> None:
        with mock.patch.dict(self.up.os.environ, {"MODEL_SLUG": "mistral-7b-instruct-v03-q4km"}):
            registry = self.up.build_registry()
        plan = self.up.resolve_target("direct", registry)
        self.assertEqual([service.name for service in plan.services], ["model:mistral-7b-instruct-v03-q4km"])

    def test_swap_uses_policy_internal_listen_address(self) -> None:
        registry = self.up.build_registry()
        plan = self.up.resolve_target("llama-swap", registry)

        self.assertIn("--listen '127.0.0.1:8081'", plan.services[0].command)

    def test_swap_set_needs_no_go_services(self) -> None:
        registry = self.up.build_registry()
        plan = self.up.resolve_target("swap", registry)
        self.assertEqual([service.name for service in plan.services], ["llama-swap"])

    def test_default_target_is_swap(self) -> None:
        with mock.patch.object(self.up, "resolve_target", side_effect=KeyError("stop")) as resolve:
            self.up.main([])
        self.assertEqual(resolve.call_args.args[0], "swap")

    def test_foreground_execs_main_service_without_tmux(self) -> None:
        registry = self.up.build_registry()
        plan = self.up.resolve_target("ternary-bonsai-27b-mlx-2bit", registry)
        with mock.patch.object(self.up.os, "execvpe") as execvpe, mock.patch.object(self.up.os, "chdir"):
            self.up.run_foreground(plan)
        program, argv, env = execvpe.call_args.args
        self.assertEqual(program, "bash")
        self.assertIn("support/model-service", argv[-1])
        self.assertEqual(env["MODEL_SLUG"], "ternary-bonsai-27b-mlx-2bit")

    def test_setup_commands_dispatch_to_onboard(self) -> None:
        for command in ("init", "doctor", "pull"):
            with self.subTest(command=command):
                target = "init" if command == "init" else command
                with mock.patch.object(self.up.onboard, target, return_value=0) as handler:
                    self.assertEqual(self.up.main([command]), 0)
                handler.assert_called_once()

    def test_unknown_target_fails(self) -> None:
        registry = self.up.build_registry()
        with self.assertRaises(KeyError):
            self.up.resolve_target("missing-target", registry)

    def test_new_session_starts_login_shell_without_send_keys(self) -> None:
        with (
            mock.patch.object(self.up, "session_exists", return_value=False),
            mock.patch.object(self.up, "run_tmux") as run_tmux,
            mock.patch.dict(self.up.os.environ, {"SHELL": "/bin/zsh"}),
        ):
            self.up.ensure_session("test-session")

        self.assertEqual(
            run_tmux.call_args_list,
            [
                mock.call(
                    ["new-session", "-d", "-s", "test-session", "-n", "control", "/bin/zsh", "-l"]
                )
            ],
        )

    def test_running_service_is_kept_by_default(self) -> None:
        service = self.up.Service(name="demo", command="sleep 10", description="demo")
        state = self.up.WindowState(name="demo", dead=False, pid=123)
        with (
            mock.patch.object(self.up, "window_states", return_value={"demo": state}),
            mock.patch.object(self.up, "run_tmux") as run_tmux,
        ):
            action = self.up.start_service("test-session", service, restart=False)

        self.assertEqual(action, "kept")
        run_tmux.assert_called_once_with(
            ["set-window-option", "-t", "test-session:demo", "remain-on-exit", "on"]
        )

    def test_dead_service_is_respawned(self) -> None:
        service = self.up.Service(name="demo", command="sleep 10", description="demo")
        state = self.up.WindowState(name="demo", dead=True, pid=123)
        with (
            mock.patch.object(self.up, "window_states", return_value={"demo": state}),
            mock.patch.object(self.up, "run_tmux") as run_tmux,
        ):
            action = self.up.start_service("test-session", service, restart=False)

        self.assertEqual(action, "restarted")
        self.assertEqual(run_tmux.call_count, 2)
        args = run_tmux.call_args_list[1].args[0]
        self.assertEqual(args[:4], ["respawn-window", "-k", "-t", "test-session:demo"])

    def test_window_state_ignores_malformed_tmux_rows(self) -> None:
        completed = subprocess.CompletedProcess(
            [],
            0,
            stdout="demo|0|123\nmalformed\nbad-pid|0|not-a-pid\n",
            stderr="",
        )
        with mock.patch.object(self.up.subprocess, "run", return_value=completed):
            states = self.up.window_states("test-session")

        self.assertEqual(states, {"demo": self.up.WindowState("demo", False, 123)})

    def test_reconcile_removes_only_unplanned_windows(self) -> None:
        plan = self.up.Plan(
            target="demo",
            services=(self.up.Service(name="demo", command="true", description="demo"),),
        )
        states = {
            "control": self.up.WindowState("control", False, 1),
            "demo": self.up.WindowState("demo", False, 2),
            "stale": self.up.WindowState("stale", False, 3),
        }
        with (
            mock.patch.object(self.up, "window_states", return_value=states),
            mock.patch.object(self.up, "terminate_process_group") as terminate,
            mock.patch.object(self.up, "run_tmux") as run_tmux,
        ):
            self.up.reconcile_windows("test-session", plan)

        terminate.assert_called_once_with(3)
        run_tmux.assert_called_once_with(["kill-window", "-t", "test-session:stale"])

    def test_down_terminates_window_and_registered_process_groups(self) -> None:
        states = {
            "control": self.up.WindowState("control", False, 10),
            "demo": self.up.WindowState("demo", False, 20),
        }
        with (
            mock.patch.object(self.up, "window_states", return_value=states),
            mock.patch.object(self.up, "registered_service_pids", return_value={"orphan": 30}),
            mock.patch.object(self.up, "terminate_process_group") as terminate,
            mock.patch.object(self.up, "session_exists", return_value=True),
            mock.patch.object(self.up, "run_tmux") as run_tmux,
            mock.patch("builtins.print"),
        ):
            result = self.up.stop_session("test-session")

        self.assertEqual(result, 0)
        self.assertEqual(terminate.call_args_list, [mock.call(20), mock.call(30)])
        run_tmux.assert_called_once_with(["kill-session", "-t", "test-session"])

    def test_process_group_termination_rejects_unmanaged_pid(self) -> None:
        with (
            mock.patch.object(self.up.os, "getpgid", return_value=42),
            mock.patch.object(self.up, "is_managed_shim", return_value=False),
            mock.patch.object(self.up.os, "killpg") as killpg,
        ):
            self.up.terminate_process_group(42)

        killpg.assert_not_called()

    def test_serving_plan_prints_pi_affordance(self) -> None:
        registry = self.up.build_registry()
        plan = self.up.resolve_target("ternary-bonsai-27b-mlx-2bit", registry)

        self.assertEqual(self.up.plan_pi_hint(plan), "agent: ./pi-local")

    def test_non_serving_plan_has_no_pi_affordance(self) -> None:
        registry = self.up.build_registry()
        plan = self.up.resolve_target("observability", registry)

        self.assertIsNone(self.up.plan_pi_hint(plan))

if __name__ == "__main__":
    unittest.main()
