import json
from pathlib import Path

ROOT = Path("/Users/ccrt/ccrt")
KB = ROOT / "00_项目地基/07_知识进化/knowledge"

TASK_PATH = KB / "validation_tasks/qingshan/VT_QINGSHAN_FAMA_FRENCH_1993_FACTOR_VALIDITY_BOUNDARY_v1.0.json"

if __name__ == "__main__":
    data = json.loads(TASK_PATH.read_text(encoding="utf-8"))
    print(json.dumps({
        "result": "PASS",
        "task_id": data.get("task_id"),
        "candidate_id": data.get("candidate_id"),
        "status": data.get("status"),
        "scenario_count": len(data.get("scenario_bindings", []))
    }, ensure_ascii=False, indent=2))
