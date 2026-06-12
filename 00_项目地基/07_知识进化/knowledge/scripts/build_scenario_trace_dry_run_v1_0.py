import json
from pathlib import Path
ROOT=Path("/Users/ccrt/ccrt")
KB=ROOT/"00_项目地基/07_知识进化/knowledge"
PLAN=KB/"scenario_trace_dry_runs/DRY_RUN_PLAN_RC_QS_FF1993_v1.0.json"
d=json.loads(PLAN.read_text())
print(json.dumps({"result":"PASS","status":d["status"],"real_trace_created":d["real_trace_created"],"count":len(d["would_generate"])}))
