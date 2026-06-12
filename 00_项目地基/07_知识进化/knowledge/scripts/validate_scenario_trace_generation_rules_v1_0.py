import json,subprocess,sys
from pathlib import Path
ROOT=Path("/Users/ccrt/ccrt")
KB=ROOT/"00_项目地基/07_知识进化/knowledge"
REPORT=KB/"reports/scenario_trace_generation_rules_validation_v1.0.json"
STAGE="G3-KB-SCENARIO-TRACE-GENERATION-RULES-v1.0"
def load(p): return json.loads(p.read_text())
required=[KB/"scenario_trace_generation_rules/scenario_trace_generation_rules_v1.0.json",
    KB/"scenario_trace_dry_runs/DRY_RUN_PLAN_RC_QS_FF1993_v1.0.json",
    KB/"scripts/build_scenario_trace_dry_run_v1_0.py",
    KB/"reports/scenario_trace_templates_audit_warn_closure_v1.0.json"]
missing=[str(p) for p in required if not p.exists()]
je=[]
for p in required:
    if p.suffix==".json" and p.exists():
        try:
            load(p)
        except Exception as e:
            je.append({"path":str(p),"error":str(e)})
rules=load(required[0]) if required[0].exists() else {}
dr=load(required[1]) if required[1].exists() else {}
cl=load(required[3]) if required[3].exists() else {}
audit_ok=all(x.get("line_count",0)>=6 and x.get("has_command") and x.get("has_boundary") and x.get("has_residual_risk") and x.get("has_formal_pipeline_note") for x in cl.get("evidence_files",[]))
real_dirs=[KB/"scenario_traces",KB/"weekly_validation_summaries",KB/"validation_reviews",KB/"role_confirmations",KB/"knowledge_merge_checks"]
real_files=[]
for d in real_dirs:
    if d.exists(): real_files.extend([str(p) for p in d.rglob("*") if p.is_file()])
p1=subprocess.run([sys.executable,str(KB/"scripts/validate_rule_candidate_validation_tasks_v1_0.py")],cwd=str(ROOT),text=True,capture_output=True)
p2=subprocess.run([sys.executable,str(KB/"scripts/validate_scenario_trace_templates_v1_0.py")],cwd=str(ROOT),text=True,capture_output=True)
pv_ok=p1.returncode==0 and p2.returncode==0
checks={"required_files_ok":not missing,"json_parse_ok":not je,
    "rules_mode_dry_run_only":rules.get("mode")=="dry_run_only",
    "rules_real_trace_not_allowed":rules.get("real_trace_allowed_now") is False,
    "dry_run_not_real_trace":dr.get("status")=="dry_run_only" and dr.get("real_trace_created") is False,
    "would_generate_four":len(dr.get("would_generate",[]))==4,
    "third_audit_warn_closed":audit_ok,"no_real_trace_generated":not real_files,
    "previous_validators_ok":pv_ok}
result="PASS" if all(checks.values()) else "FAIL"
rpt={"stage":STAGE,"result":result,"checks":checks,"missing":missing,"formal_pipeline_note":"CCRT relay-package record."}
REPORT.write_text(json.dumps(rpt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(json.dumps(rpt,ensure_ascii=False,indent=2))
raise SystemExit(0 if result=="PASS" else 1)
