#!/usr/bin/env python3
"""Verify G6 GitHub closure for CCRT.

Validates 12 conditions for a complete G6 GitHub sync closure:

  1. archive_record exists
  2. archive_record.artifact_type == archive_record
  3. archive_record.result == CLOSED
  4. archive_record.archive_completed is True
  5. github_sync_record exists
  6. github_sync_record.artifact_type == github_sync_record
  7. github_sync_record.github_sync_completed is True
  8. github_sync_record.push_completed is True
  9. github_sync_record.archive_record points to the same file as --archive-record
 10. git status --porcelain is empty
 11. ahead/behind == 0/0 (git rev-list --left-right --count HEAD...@{upstream})
 12. HEAD == upstream HEAD

Outputs JSON with:
  PASS: { "status": "PASS", ...all_fields }
  BLOCK: { "status": "BLOCK", "reason": "...", ...checks }
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_json(path):
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def run_git(args, cwd=None):
    cmd = ["git"] + args
    proc = subprocess.run(
        cmd, cwd=cwd or str(ROOT), capture_output=True, text=True, timeout=60
    )
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def verify(archive_record_path, github_sync_record_path, cwd=None):
    """Run all 12 verification checks.

    Returns a dict: {status: "PASS"|"BLOCK", check_results, ...}
    """
    result = {
        "status": "PASS",  # default, may become BLOCK
        "checks": {},
        "archive_completed": False,
        "github_sync_completed": False,
        "push_completed": False,
        "git_status_clean": False,
        "ahead_count": None,
        "behind_count": None,
        "head_equals_upstream": False,
    }
    failures = []

    archive_path = Path(archive_record_path)
    sync_path = Path(github_sync_record_path)

    # 1. archive_record exists
    if not archive_path.exists():
        result["status"] = "BLOCK"
        result["checks"]["c01_archive_exists"] = False
        failures.append(f"archive_record not found: {archive_record_path}")
    else:
        result["checks"]["c01_archive_exists"] = True

    # 2. artifact_type == archive_record
    if result["status"] == "BLOCK" and failures:
        pass  # can't proceed without archive_record
    else:
        arc_data = load_json(archive_path)
        if arc_data.get("artifact_type") != "archive_record":
            result["status"] = "BLOCK"
            result["checks"]["c02_artifact_type"] = False
            failures.append(
                f"archive_record.artifact_type must be 'archive_record', "
                f"got {arc_data.get('artifact_type')}"
            )
        else:
            result["checks"]["c02_artifact_type"] = True

        # 3. result == CLOSED
        if arc_data.get("result") != "CLOSED":
            result["status"] = "BLOCK"
            result["checks"]["c03_result_closed"] = False
            failures.append(
                f"archive_record.result must be 'CLOSED', got {arc_data.get('result')}"
            )
        else:
            result["checks"]["c03_result_closed"] = True

        # 4. archive_completed is True
        if arc_data.get("archive_completed") is not True:
            result["status"] = "BLOCK"
            result["checks"]["c04_archive_completed"] = False
            failures.append(
                f"archive_record.archive_completed must be true, "
                f"got {arc_data.get('archive_completed')}"
            )
        else:
            result["checks"]["c04_archive_completed"] = True
            result["archive_completed"] = True

    # 5. github_sync_record exists
    if not sync_path.exists():
        result["status"] = "BLOCK"
        result["checks"]["c05_sync_record_exists"] = False
        failures.append(f"github_sync_record not found: {github_sync_record_path}")
    else:
        result["checks"]["c05_sync_record_exists"] = True

    # 6-9: Validate github_sync_record content
    if not sync_path.exists():
        if result["status"] != "BLOCK":
            result["status"] = "BLOCK"
        result["checks"]["c06_artifact_type"] = False
        result["checks"]["c07_sync_completed"] = False
        result["checks"]["c08_push_completed"] = False
        result["checks"]["c09_archive_record_ref"] = False
    else:
        sync_data = load_json(sync_path)

        # 6. artifact_type == github_sync_record
        if sync_data.get("artifact_type") != "github_sync_record":
            result["status"] = "BLOCK"
            result["checks"]["c06_artifact_type"] = False
            failures.append(
                f"github_sync_record.artifact_type must be 'github_sync_record', "
                f"got {sync_data.get('artifact_type')}"
            )
        else:
            result["checks"]["c06_artifact_type"] = True

        # 7. github_sync_completed is True
        if sync_data.get("github_sync_completed") is not True:
            result["status"] = "BLOCK"
            result["checks"]["c07_sync_completed"] = False
            failures.append(
                f"github_sync_record.github_sync_completed must be true, "
                f"got {sync_data.get('github_sync_completed')}"
            )
        else:
            result["checks"]["c07_sync_completed"] = True
            result["github_sync_completed"] = True

        # 8. push_completed is True
        if sync_data.get("push_completed") is not True:
            result["status"] = "BLOCK"
            result["checks"]["c08_push_completed"] = False
            failures.append(
                f"github_sync_record.push_completed must be true, "
                f"got {sync_data.get('push_completed')}"
            )
        else:
            result["checks"]["c08_push_completed"] = True
            result["push_completed"] = True

        # 9. archive_record reference matches
        synced_arc = sync_data.get("archive_record", "")
        try:
            synced_arc_resolved = Path(synced_arc).resolve()
            given_arc_resolved = archive_path.resolve()
            ref_match = synced_arc_resolved == given_arc_resolved
        except Exception:
            ref_match = False
        if not ref_match:
            result["status"] = "BLOCK"
            result["checks"]["c09_archive_record_ref"] = False
            failures.append(
                f"github_sync_record archive_record ref mismatch: "
                f"record says '{synced_arc}', given '{archive_record_path}'"
            )
        else:
            result["checks"]["c09_archive_record_ref"] = True

    # 10. git status --porcelain is empty
    status = run_git(["-c", "core.quotepath=false", "status", "--porcelain"], cwd=cwd)
    git_status_clean = status["returncode"] == 0 and not status["stdout"].strip()
    result["git_status_clean"] = git_status_clean
    result["checks"]["c10_git_status_clean"] = git_status_clean
    if not git_status_clean:
        result["status"] = "BLOCK"
        dirty = [l for l in status["stdout"].splitlines() if l.strip()]
        failures.append(f"git workspace is not clean: {dirty}")

    # 11. ahead/behind == 0/0
    ahead_behind = run_git(
        ["rev-list", "--left-right", "--count", "HEAD...@{upstream}"], cwd=cwd
    )
    ahead_count = None
    behind_count = None
    if ahead_behind["returncode"] == 0:
        parts = ahead_behind["stdout"].split()
        if len(parts) == 2:
            # --left-right output: <left (HEAD-only) = ahead> <right (upstream-only) = behind>
            ahead_count = parts[0]
            behind_count = parts[1]
    result["ahead_count"] = ahead_count
    result["behind_count"] = behind_count
    result["checks"]["c11_ahead_behind"] = (ahead_count == "0" and behind_count == "0")
    if ahead_count != "0" or behind_count != "0":
        result["status"] = "BLOCK"
        failures.append(f"ahead/behind = {ahead_count}/{behind_count}, expected 0/0")

    # 12. HEAD == upstream HEAD
    head_sha = run_git(["rev-parse", "HEAD"], cwd=cwd)
    upstream_sha = run_git(["rev-parse", "@{upstream}"], cwd=cwd)
    head_match = (
        head_sha["returncode"] == 0 and upstream_sha["returncode"] == 0
        and head_sha["stdout"].strip() == upstream_sha["stdout"].strip()
    )
    result["head_equals_upstream"] = head_match
    result["checks"]["c12_head_equals_upstream"] = head_match
    if not head_match:
        result["status"] = "BLOCK"
        failures.append(
            f"HEAD {head_sha['stdout'][:12]} != upstream {upstream_sha['stdout'][:12]}"
        )

    # Build reason if BLOCK
    if result["status"] == "BLOCK":
        result["reason"] = "; ".join(failures)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="CCRT G6 GitHub closure verifier"
    )
    parser.add_argument("--archive-record", required=True,
                        help="Path to G6 archive_record JSON")
    parser.add_argument("--github-sync-record", required=True,
                        help="Path to github_sync_record JSON")
    args = parser.parse_args()

    result = verify(args.archive_record, args.github_sync_record)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
