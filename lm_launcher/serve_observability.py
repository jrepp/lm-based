from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME_ROOT = PROJECT_ROOT / ".runtime" / "serve-manager"


@dataclass(frozen=True)
class ObservabilityPorts:
    direct_server_metrics: str = "127.0.0.1:8001"
    staged_haproxy_public: str = "127.0.0.1:8080"
    staged_llama_swap_internal: str = "127.0.0.1:8081"
    supervisor_metrics: str = "127.0.0.1:9091"
    prometheus_listen: str = "127.0.0.1:9090"
    vector_api: str = "127.0.0.1:8686"
    vector_prometheus_exporter: str = "127.0.0.1:9598"
    haproxy_metrics: str = "127.0.0.1:8405"


@dataclass(frozen=True)
class RenderedObservability:
    runtime_root: Path
    observability_root: Path
    prometheus_config_path: Path
    vector_config_path: Path
    manifest_path: Path


def _yaml_string(value: str | Path) -> str:
    return json.dumps(str(value))


def _vector_component_log_path(runtime_root: Path) -> Path:
    return runtime_root / "observability" / "vector" / "component-logs.jsonl"


def _vector_data_dir(runtime_root: Path) -> Path:
    return runtime_root / "observability" / "vector" / "data"


def _log_globs(project_root: Path, runtime_root: Path) -> dict[str, str]:
    return {
        "direct_worker_logs": str(project_root / "runs" / "*" / "*.log"),
        "serve_manager_logs": str(runtime_root / "logs" / "*.log"),
    }


def render_prometheus_config(ports: ObservabilityPorts) -> str:
    return f"""global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: direct-llama-server
    metrics_path: /metrics
    static_configs:
      - targets:
          - {_yaml_string(ports.direct_server_metrics)}
        labels:
          plane: direct
          component: worker
          role: fallback

  - job_name: vector
    static_configs:
      - targets:
          - {_yaml_string(ports.vector_prometheus_exporter)}
        labels:
          plane: staging
          component: vector

  - job_name: serve-manager
    static_configs:
      - targets:
          - {_yaml_string(ports.supervisor_metrics)}
        labels:
          plane: staging
          component: supervisor

  - job_name: haproxy
    metrics_path: /metrics
    static_configs:
      - targets:
          - {_yaml_string(ports.haproxy_metrics)}
        labels:
          plane: staging
          component: haproxy
"""


def render_vector_config(project_root: Path, runtime_root: Path, ports: ObservabilityPorts) -> str:
    globs = _log_globs(project_root, runtime_root)
    return f"""data_dir: {_yaml_string(_vector_data_dir(runtime_root))}

api:
  enabled: true
  address: {_yaml_string(ports.vector_api)}

sources:
  direct_worker_logs:
    type: file
    include:
      - {_yaml_string(globs["direct_worker_logs"])}
    read_from: end

  serve_manager_component_logs:
    type: file
    include:
      - {_yaml_string(globs["serve_manager_logs"])}
    read_from: end

  vector_internal_logs:
    type: internal_logs

  vector_internal_metrics:
    type: internal_metrics

sinks:
  component_logs_file:
    type: file
    inputs:
      - direct_worker_logs
      - serve_manager_component_logs
      - vector_internal_logs
    path: {_yaml_string(_vector_component_log_path(runtime_root))}
    encoding:
      codec: json

  internal_metrics_exporter:
    type: prometheus_exporter
    inputs:
      - vector_internal_metrics
    address: {_yaml_string(ports.vector_prometheus_exporter)}
"""


def build_manifest(project_root: Path, runtime_root: Path, ports: ObservabilityPorts) -> dict[str, object]:
    globs = _log_globs(project_root, runtime_root)
    return {
        "schema_version": 1,
        "milestone": "Milestone 1: Observability Foundation",
        "runtime_root": str(runtime_root),
        "current_direct_server": {
            "listen": ports.direct_server_metrics,
            "status": "untouched",
            "purpose": "fallback direct path",
        },
        "reserved_ports": asdict(ports),
        "prometheus_targets": [
            {
                "job_name": "direct-llama-server",
                "target": ports.direct_server_metrics,
                "status": "live",
            },
            {
                "job_name": "vector",
                "target": ports.vector_prometheus_exporter,
                "status": "staged",
            },
            {
                "job_name": "serve-manager",
                "target": ports.supervisor_metrics,
                "status": "reserved",
            },
            {
                "job_name": "haproxy",
                "target": ports.haproxy_metrics,
                "status": "reserved",
            },
        ],
        "log_ownership": [
            {
                "component": "direct-worker",
                "owner": "run-server.py capture path",
                "source_glob": globs["direct_worker_logs"],
                "status": "live",
            },
            {
                "component": "serve-manager",
                "owner": "future Go control plane",
                "source_glob": globs["serve_manager_logs"],
                "status": "reserved",
            },
            {
                "component": "haproxy",
                "owner": "future Go control plane",
                "source_glob": str(runtime_root / "logs" / "haproxy.log"),
                "status": "reserved",
            },
            {
                "component": "llama-swap",
                "owner": "future Go control plane",
                "source_glob": str(runtime_root / "logs" / "llama-swap.log"),
                "status": "reserved",
            },
        ],
        "generated_files": {
            "prometheus": str(runtime_root / "observability" / "prometheus.yml"),
            "vector": str(runtime_root / "observability" / "vector.yaml"),
            "manifest": str(runtime_root / "observability" / "manifest.json"),
        },
    }


def render_observability_bundle(
    project_root: Path = PROJECT_ROOT,
    runtime_root: Path = DEFAULT_RUNTIME_ROOT,
    ports: ObservabilityPorts = ObservabilityPorts(),
) -> RenderedObservability:
    observability_root = runtime_root / "observability"
    vector_root = observability_root / "vector"
    logs_root = runtime_root / "logs"
    pids_root = runtime_root / "pids"
    generations_root = runtime_root / "generations"
    workers_root = runtime_root / "workers"

    for path in (
        observability_root,
        vector_root,
        logs_root,
        pids_root,
        generations_root,
        workers_root,
        _vector_data_dir(runtime_root),
    ):
        path.mkdir(parents=True, exist_ok=True)

    prometheus_config_path = observability_root / "prometheus.yml"
    vector_config_path = observability_root / "vector.yaml"
    manifest_path = observability_root / "manifest.json"

    prometheus_config_path.write_text(
        render_prometheus_config(ports),
        encoding="utf-8",
    )
    vector_config_path.write_text(
        render_vector_config(project_root, runtime_root, ports),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(build_manifest(project_root, runtime_root, ports), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return RenderedObservability(
        runtime_root=runtime_root,
        observability_root=observability_root,
        prometheus_config_path=prometheus_config_path,
        vector_config_path=vector_config_path,
        manifest_path=manifest_path,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="serve-observability",
        description="Render additive observability config for the staged serving stack.",
    )
    parser.add_argument(
        "--runtime-root",
        type=Path,
        default=DEFAULT_RUNTIME_ROOT,
        help="Runtime root for generated serve-manager state.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("render", help="Write Prometheus, Vector, and manifest files.")
    subparsers.add_parser("show", help="Print the manifest JSON without writing files.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    runtime_root = args.runtime_root.resolve()

    if args.command == "render":
        rendered = render_observability_bundle(runtime_root=runtime_root)
        print(f"wrote {rendered.prometheus_config_path}")
        print(f"wrote {rendered.vector_config_path}")
        print(f"wrote {rendered.manifest_path}")
        return 0

    if args.command == "show":
        manifest = build_manifest(PROJECT_ROOT, runtime_root, ObservabilityPorts())
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2
