import json
import tempfile
import unittest
from pathlib import Path

from lm_launcher.serve_observability import (
    ObservabilityPorts,
    build_manifest,
    render_observability_bundle,
)


class TestServeObservability(unittest.TestCase):

    def test_render_bundle_writes_expected_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir) / "project"
            runtime_root = project_root / ".runtime" / "serve-manager"
            (project_root / "runs" / "example-run").mkdir(parents=True)

            rendered = render_observability_bundle(
                project_root=project_root,
                runtime_root=runtime_root,
            )

            self.assertTrue(rendered.prometheus_config_path.is_file())
            self.assertTrue(rendered.vector_config_path.is_file())
            self.assertTrue(rendered.manifest_path.is_file())

            prometheus_config = rendered.prometheus_config_path.read_text(encoding="utf-8")
            self.assertIn("job_name: direct-llama-server", prometheus_config)
            self.assertIn('"127.0.0.1:8001"', prometheus_config)
            self.assertIn('"127.0.0.1:8405"', prometheus_config)

            vector_config = rendered.vector_config_path.read_text(encoding="utf-8")
            self.assertIn(str(project_root / "runs" / "*" / "*.log"), vector_config)
            self.assertIn(str(runtime_root / "logs" / "*.log"), vector_config)
            self.assertIn('"127.0.0.1:9598"', vector_config)

            manifest = json.loads(rendered.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(
                manifest["current_direct_server"]["status"],
                "untouched",
            )
            self.assertEqual(
                manifest["reserved_ports"]["supervisor_metrics"],
                "127.0.0.1:9091",
            )

    def test_manifest_marks_live_and_reserved_targets(self):
        ports = ObservabilityPorts()
        manifest = build_manifest(
            Path("/repo"),
            Path("/repo/.runtime/serve-manager"),
            ports,
        )

        targets = {entry["job_name"]: entry for entry in manifest["prometheus_targets"]}
        self.assertEqual(targets["direct-llama-server"]["status"], "live")
        self.assertEqual(targets["vector"]["status"], "staged")
        self.assertEqual(targets["serve-manager"]["status"], "reserved")
        self.assertEqual(targets["haproxy"]["target"], "127.0.0.1:8405")


if __name__ == "__main__":
    unittest.main()
