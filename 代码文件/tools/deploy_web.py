#!/usr/bin/env python3
"""deploy_web.py — Deploy static HTML reports to Cloudflare Pages

Thin wrapper around `npx wrangler pages publish`.
Requires: CF_API_TOKEN and CF_ACCOUNT_ID env vars.
Code level: L0

Usage:
  python3 deploy_web.py --list        列出待部署文件
  python3 deploy_web.py --dry-run      只收集文件，不部署
  python3 deploy_web.py                部署
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "deploy_web_config.json")
DEPLOY_LOG = os.path.join(ROOT, "临时报告", "deploy_web.log")


def write_deploy_log(status, file_count=0, url="", error=""):
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": status,
        "file_count": file_count,
        "url": url,
        "error": error,
    }
    os.makedirs(os.path.dirname(DEPLOY_LOG), exist_ok=True)
    with open(DEPLOY_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_config():
    if not os.path.exists(CONFIG_PATH):
        print(f"ERROR: config not found at {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def collect_files(source_dirs, root):
    """Collect files from configured source directories into a dict of {rel_path: abs_path}."""
    files = {}
    for entry in source_dirs:
        src_dir = os.path.join(root, entry["path"])
        if not os.path.isdir(src_dir):
            print(f"WARN: source dir not found, skipping: {src_dir}")
            continue
        pattern = entry.get("include", "*.html")
        recursive = entry.get("recursive", False)
        glob_fn = Path(src_dir).rglob if recursive else Path(src_dir).glob
        for f in glob_fn(pattern):
            if f.is_file():
                rel = str(f.relative_to(root))
                files[rel] = str(f)
    return files


def build_deploy_dir(files, root, config):
    """Copy collected files into a flat or mirrored deploy directory."""
    deploy_dir = tempfile.mkdtemp(prefix="deploy_web_")
    for rel_path, abs_path in files.items():
        dest = os.path.join(deploy_dir, rel_path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(abs_path, dest)

    root_index = config.get("root_index")
    if root_index and root_index in files:
        shutil.copy2(files[root_index], os.path.join(deploy_dir, "index.html"))
        print(f"Root index set: {root_index} → index.html")

    print(f"Collected {len(files)} files into {deploy_dir}")
    return deploy_dir


class DeployError(Exception):
    pass


def check_prerequisites():
    """Check env vars are set. Raise DeployError if missing."""
    missing = []
    for var in ("CF_API_TOKEN", "CF_ACCOUNT_ID"):
        if not os.environ.get(var):
            missing.append(var)
    if missing:
        msg = f"missing env vars: {', '.join(missing)}"
        print(json.dumps({"status": "error", "error": msg}, ensure_ascii=False))
        raise DeployError(msg)


def build_env():
    """Build subprocess env with Cloudflare vars mapped for wrangler."""
    env = os.environ.copy()
    env["CLOUDFLARE_API_TOKEN"] = env.get("CF_API_TOKEN", "")
    env["CLOUDFLARE_ACCOUNT_ID"] = env.get("CF_ACCOUNT_ID", "")
    env["CI"] = "1"
    return env


def deploy(config, deploy_dir, dry_run=False):
    """Run wrangler pages publish."""
    project = config["cloudflare"]["project_name"]
    cmd = [
        "npx", "-y", "wrangler", "pages", "deploy", deploy_dir,
        "--project-name", project,
    ]
    branch = config.get("deploy_branch", "main")
    cmd += ["--branch", branch]

    if dry_run:
        print(f"DRY-RUN: would run: {' '.join(cmd)}")
        return {"status": "dry_run", "url": None, "file_count": 0}

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT,
                            env=build_env())
    if result.returncode != 0:
        msg = f"wrangler deploy failed: {result.stderr[:500]}"
        print(json.dumps({"status": "error", "error": msg}, ensure_ascii=False))
        raise DeployError(msg)

    # Parse deployment URL from wrangler output
    output = result.stdout + result.stderr
    url = None
    for line in output.splitlines():
        line = line.strip()
        if "https://" in line and "pages.dev" in line:
            url = line.split()[-1].rstrip(".")
            break
    if not url:
        url = f"https://{project}.pages.dev"

    return {"status": "success", "url": url, "output": output}


def list_files(files):
    """Print deployable file list."""
    print(f"\n待部署文件 ({len(files)} 个):")
    print("-" * 40)
    for rel in sorted(files.keys()):
        size_kb = os.path.getsize(files[rel]) / 1024
        print(f"  {rel}  ({size_kb:.1f}KB)")
    print("-" * 40)


def main():
    parser = argparse.ArgumentParser(description="Deploy static HTML to Cloudflare Pages")
    parser.add_argument("--source", help="Single source directory (overrides config)")
    parser.add_argument("--dry-run", action="store_true", help="Only collect files, do not deploy")
    parser.add_argument("--list", action="store_true", help="List files that would be deployed, then exit")
    args = parser.parse_args()

    config = load_config()

    if args.source:
        source_dirs = [{"path": args.source, "include": "*.html", "recursive": False}]
    else:
        source_dirs = config.get("source_dirs", [])

    if not source_dirs:
        print(json.dumps({"status": "error", "error": "no source directories configured"}, ensure_ascii=False))
        write_deploy_log("FAIL", error="no source directories configured")
        sys.exit(1)

    files = collect_files(source_dirs, ROOT)
    if not files:
        print(json.dumps({"status": "empty", "error": "no files found", "file_count": 0}, ensure_ascii=False))
        return

    # --list mode: show files and exit
    if args.list:
        list_files(files)
        return

    # Always print file list before deploying
    list_files(files)

    deploy_dir = build_deploy_dir(files, ROOT, config)

    if args.dry_run:
        shutil.rmtree(deploy_dir)
        return

    try:
        check_prerequisites()
        result = deploy(config, deploy_dir, dry_run=args.dry_run)
    except (DeployError, Exception) as e:
        result = {"status": "error", "url": None, "error": str(e), "file_count": len(files)}
        write_deploy_log("FAIL", file_count=len(files), error=str(e))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        shutil.rmtree(deploy_dir)
        return

    result["file_count"] = len(files)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result.get("status") == "success":
        write_deploy_log("OK", file_count=len(files), url=result.get("url", ""))

    shutil.rmtree(deploy_dir)


if __name__ == "__main__":
    main()
