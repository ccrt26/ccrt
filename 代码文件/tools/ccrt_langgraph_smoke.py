#!/usr/bin/env python3
"""CCRT LangGraph local wiring smoke test.

This script verifies local configuration without running real model tasks by
default. It checks:
- LangGraph imports and can execute a minimal graph.
- CCRT rule/config files are readable.
- Codex and Claude Code CLI entrypoints exist and report versions/help.
- Existing stage-gate scripts pass their self-tests.
"""

import argparse
import importlib.metadata
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "代码文件" / "tools" / "ccrt_langgraph_config.json"


def load_json(path):
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def run_cmd(cmd, timeout=60):
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def relpath(path):
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def check_path(path, must_be_file=True):
    p = Path(path)
    if not p.is_absolute():
        p = ROOT / p
    ok = p.is_file() if must_be_file else p.exists()
    return {
        "path": relpath(p),
        "exists": ok,
    }


def langgraph_smoke():
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(dict)
    graph.add_node("requirement_precision", lambda state: {
        **state,
        "precise_requirement": {
            "goal": "调通 CCRT LangGraph 本地配置",
            "scope": "配置、入口、阶段门自检",
            "no_business_changes": True,
        },
    })
    graph.add_node("g0_route_ahei_codex", lambda state: {
        **state,
        "g0_route": {
            "flow_code": "F-ARCH",
            "reason": "LangGraph 自动化底座属于架构/流程编排能力",
        },
    })
    graph.add_node("role_modes", lambda state: {
        **state,
        "role_modes": ["需求精准描述@Codex", "阿黑@Codex", "情墨@Codex", "红结@DeepSeek"],
    })
    graph.add_node("finalize", lambda state: {
        **state,
        "user_visible_status": "COMPLETE",
    })

    graph.add_edge(START, "requirement_precision")
    graph.add_edge("requirement_precision", "g0_route_ahei_codex")
    graph.add_edge("g0_route_ahei_codex", "role_modes")
    graph.add_edge("role_modes", "finalize")
    graph.add_edge("finalize", END)
    app = graph.compile()
    return app.invoke({"raw_requirement": "先把 LangGraph 配置调通"})


def collect_versions(config):
    packages = ["langgraph", "langchain-core", "langgraph-checkpoint", "langgraph-sdk", "langsmith"]
    versions = {}
    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None

    python_path = config["runtime"]["python"]
    return {
        "python": run_cmd([python_path, "--version"]),
        "packages": versions,
    }


def check_config_files(config):
    checks = {}
    for key, path in config.get("ccrt_rules", {}).items():
        checks[key] = check_path(path)
        if checks[key]["exists"]:
            try:
                load_json(ROOT / path)
                checks[key]["json_parse"] = "PASS"
            except json.JSONDecodeError as exc:
                checks[key]["json_parse"] = f"BLOCK: {exc}"
    return checks


def check_model_entrypoints(config):
    codex = config["model_runtimes"]["codex"]
    claude = config["model_runtimes"]["deepseek_via_claude_code"]
    return {
        "codex": {
            "path": check_path(codex["bin"]),
            "version": run_cmd([codex["bin"], "--version"], timeout=30),
        },
        "claude_code": {
            "path": check_path(claude["bin"]),
            "version": run_cmd([claude["bin"], "--version"], timeout=30),
        },
    }


def check_stage_gate_self_tests(config):
    python_path = config["runtime"]["python"]
    results = {}
    for key, script in config.get("stage_gate_tools", {}).items():
        path_check = check_path(script)
        item = {"path": path_check}
        if path_check["exists"]:
            item["self_test"] = run_cmd([python_path, script, "--self-test"], timeout=120)
        results[key] = item
    return results


def summarize_status(report):
    failures = []

    graph_status = report.get("langgraph_graph", {}).get("user_visible_status")
    if graph_status != "COMPLETE":
        failures.append("langgraph_graph")

    for name, data in report.get("config_files", {}).items():
        if not data.get("exists") or data.get("json_parse") != "PASS":
            failures.append(f"config:{name}")

    for name, data in report.get("model_entrypoints", {}).items():
        if not data.get("path", {}).get("exists"):
            failures.append(f"model_path:{name}")
        version = data.get("version", {})
        if version.get("returncode") != 0:
            failures.append(f"model_version:{name}")

    for name, data in report.get("stage_gate_self_tests", {}).items():
        if not data.get("path", {}).get("exists"):
            failures.append(f"stage_tool_path:{name}")
        result = data.get("self_test", {})
        if result.get("returncode") != 0:
            failures.append(f"stage_tool_self_test:{name}")

    return "COMPLETE" if not failures else "BLOCK", failures


def main():
    parser = argparse.ArgumentParser(description="CCRT LangGraph local wiring smoke test")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to config JSON")
    parser.add_argument("--skip-stage-self-tests", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print full JSON report")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = ROOT / config_path

    config = load_json(config_path)
    report = {
        "task": "ccrt_langgraph_local_wiring_smoke",
        "config": relpath(config_path),
        "versions": collect_versions(config),
        "langgraph_graph": langgraph_smoke(),
        "config_files": check_config_files(config),
        "model_entrypoints": check_model_entrypoints(config),
        "stage_gate_self_tests": {} if args.skip_stage_self_tests else check_stage_gate_self_tests(config),
    }
    status, failures = summarize_status(report)
    report["user_visible_status"] = status
    report["failures"] = failures

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({
            "user_visible_status": status,
            "config": report["config"],
            "langgraph": report["langgraph_graph"].get("user_visible_status"),
            "failures": failures,
        }, ensure_ascii=False, indent=2))

    return 0 if status == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
