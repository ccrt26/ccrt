# 会话五 G3 技术设计 — 重点股票产品页面 shadow refresh 闭环

> **设计者**: 情墨
> **日期**: 2026-06-16
> **流程**: RUN-20260616-170043-432bb6
> **G2 方案全文**: 参考会话五 G2 子方案（本对话上下文）

---

## 一、设计目标

在不切生产的前提下，建立重点股票产品页面的 shadow/dry-run 刷新闭环。

### 关键约束

| 约束 | 说明 |
|:-----|:------|
| 不切生产 | 不注册 launchd、不改 runtime registry、不改 baseline registry |
| 只读注册表 | runtime_entry_registry.json、baseline_registry.json 只校验 hash，不修改 |
| 股票池只读 | 不允许把 600114 写成脚本内的业务散落常量，仅读现有 ProductStockPoolService 结果 |
| 业务 BLOCK 允许 | 当前 DATA_DATE_DIVERGENCE 不阻断 shadow 闭环，仅阻断生产放行 |
| 工程 BLOCK 必须 | checker engineering_status=BLOCK 时脚本退出 1 |
| 角色签名禁代 | 执行模型不得冒充旧影/腰子/阿黑等角色签署 |

---

## 二、文件范围

### 新增文件

| 文件 | 用途 |
|:-----|:------|
| `scripts/run_keystock_dashboard_shadow_refresh.py` | shadow/dry-run 刷新总入口，只生成 product_api 与 docs data，只读检查 runtime registry，生成 evidence |
| `tests/keystock_product_eval/test_shadow_refresh_contract.py` | 验证 shadow refresh 不触碰生产、不调用调度注册、不接真实持仓、evidence 字段完整、run_id 一致、rollback_ref 存在 |

### 可能小幅修改文件

| 文件 | 修改类型 |
|:-----|:---------|
| `scripts/build_keystock_product_api_bundle.py` | 如需适配 shadow 脚本的参数传递（如 evidence-out, review-candidate-out 等路径） |
| `scripts/check_keystock_dashboard_productization.py` | 如需适配 shadow 脚本的 checker 汇总输出路径 |

### 产出目录（允许 shadow 刷新）

| 目录 | 用途 |
|:-----|:------|
| `docs/keystock-dashboard/data/` | shadow 产品 API 公开数据（含 11 个标准 JSON 文件 + stocks/ 子目录） |
| `运行产物/重点股票产品化后评估/evidence/` | shadow evidence 文件 |
| `运行产物/重点股票产品化后评估/product_api/` | product API bundle 产物 |
| `运行产物/重点股票产品化后评估/product_api/_staging/` | staging 区域 |

### 禁止修改文件

| 文件 | 原因 |
|:-----|:------|
| `00_项目地基/06_调度与运行/runtime_entry_registry.json` | 生产调度权威源，只读 hash 校验 |
| `00_项目地基/02_权威注册表/baseline_registry.json` | baseline 权威源，只读 hash 校验 |
| `重点股票/股票报告/` | 正式报告资产 |
| `重点股票/深度分析/` | 深度分析资产 |
| `重点股票/基线/` | 基线资产 |
| 真实持仓来源 | 禁止接入成本/数量/盈亏 |

---

## 三、代码等级

| 条目 | 等级 | 理由 |
|:-----|:-----|:------|
| `scripts/run_keystock_dashboard_shadow_refresh.py` | L1 | 调用已建 product_api_bundle 服务、只读校验 registry、生成证据文件，属于模块化编排脚本 |
| `tests/keystock_product_eval/test_shadow_refresh_contract.py` | L1 | 纯测试合约，无副作用 |

---

## 四、架构概要

```
run_keystock_dashboard_shadow_refresh.py
    │
    ├── 1. before sha256 (runtime_entry_registry.json, baseline_registry.json)
    ├── 2. 自检源码无危险调用 (generate_launchd/launchctl/crontab)
    ├── 3. call build_keystock_product_api_bundle.py
    │       └── ProductApiBundleService.build_all()
    │           └── staging → checker → atomic_publish
    ├── 4. call check_keystock_dashboard_productization.py
    ├── 5. 读取 run_manifest.json / bundle_index.json / stock_pool.json
    ├── 6. run_id 一致性校验
    ├── 7. after sha256 + 对比
    ├── 8. 写 shadow evidence
    └── 9. exit code 根据 engineering_status 决定
```

### CLI 参数

| 参数 | 默认 | 说明 |
|:-----|:-----|:------|
| `--dry-run` | true (store_true) | 允许刷新 product_api 与 docs data，禁止 runtime/launchd/生产切换 |
| `--base-dir` | `运行产物/重点股票产品化后评估` | 产品化评估基础目录 |
| `--out-dir` | `<base-dir>/product_api` | product API bundle 输出目录 |
| `--docs-data-dir` | `docs/keystock-dashboard/data` | docs 公开数据目录 |
| `--evidence-dir` | `<base-dir>/evidence` | evidence 输出目录 |
| `--docs-dir` | `docs/keystock-dashboard` | 前端静态文件目录 |
| `--fail-on-business-block` | false | 生产切换才要求业务无 BLOCK；shadow 时允许业务 BLOCK |
| `--fail-on-engineering-block` | true | checker engineering_status=BLOCK 时退出 1 |

---

## 五、需求→代码核对清单

### A. shadow 刷新入口

| # | 需求 | 实现位置 |
|:-:|:-----|:---------|
| A1 | Shadow refresh 总入口脚本 | `scripts/run_keystock_dashboard_shadow_refresh.py` main() |
| A2 | dry-run 模式默认开启，禁止 runtime/launchd/生产切换 | `--dry-run` 参数，主流程前检查 |
| A3 | 自检源码不含危险调度调用 | 正则扫描 `generate_launchd|launchctl|crontab|bootstrap|kickstart` |
| A4 | registry 只读 hash 校验 | `hashlib.sha256()` → before/after 比对 |

### B. 构建与调用

| # | 需求 | 实现位置 |
|:-:|:-----|:---------|
| B1 | 调用 build_keystock_product_api_bundle.py | `subprocess.run()` 传参调用 |
| B2 | 传递证据路径等参数 | 拼接 `--evidence-out --review-candidate-out --archive-out` 等 |

### C. checker 汇总

| # | 需求 | 实现位置 |
|:-:|:-----|:---------|
| C1 | 调用 checker → 解析 JSON stdout | `subprocess.run()` + `json.loads()` |
| C2 | engineering_status 分流 | engineering BLOCK → exit 1；业务 BLOCK → exit 0 |
| C3 | Checker 原始结果写入 evidence | 复制到 `keystock_dashboard_shadow_checker_{run_id}.json` |

### D. run_manifest 校验

| # | 需求 | 实现位置 |
|:-:|:-----|:---------|
| D1 | docs run_id == product_api run_id | 对比两个 run_manifest.json |
| D2 | bundle_index run_id == run_manifest run_id | 对比 bundle_index.json run_id |
| D3 | publish_status 存在且为 PUBLISHED | 读取 run_manifest.publish_status |
| D4 | rollback_ref 非空，无则 fallback | bundle_index.current_bundle_path 填充 |
| D5 | stock_pool members == ["600114"] | stock_pool.json members 校验 |

### E. evidence 生成

| # | 需求 | 实现位置 |
|:-:|:-----|:---------|
| E1 | 主证据文件 ev {run_id}.json | `keystock_dashboard_shadow_refresh_{run_id}.json` |
| E2 | 最新指针证据 | `keystock_dashboard_shadow_latest.json`（可覆盖） |
| E3 | checker 汇总文件 | `keystock_dashboard_shadow_checker_{run_id}.json` |
| E4 | no_production_touch 全部 false | evidence.no_production_touch 字段 |
| E5 | production_ready 必须 false | evidence.production_ready 字段 |

### F. 测试合约

| # | 需求 | 实现位置 |
|:-:|:-----|:---------|
| F1 | 脚本可 py_compile | `test_script_compile` |
| F2 | 源码不含危险调用 | `test_no_dangerous_calls` |
| F3 | evidence 字段完整 | `test_evidence_fields` |
| F4 | no_production_touch 全部 false | `test_no_production_touch` |
| F5 | stock_pool 只含 600114 | `test_stock_pool_scope` |
| F6 | run_id 一致性 | `test_run_id_consistency` |
| F7 | rollback_ref 存在性 | `test_rollback_ref_exists` |
| F8 | 业务 BLOCK 不导致工程失败 | `test_business_block_does_not_fail` |
| F9 | 工程 BLOCK 必须失败 | `test_engineering_block_fails` |
| F10 | 不生成正式买卖/仓位结论 | `test_no_formal_conclusion` |
| F11 | 不写真实持仓 | `test_no_real_position` |

### G. 部署闸门（G3 检查点）

| # | 需求 | 实现位置 |
|:-:|:-----|:---------|
| G1 | pipeline 创建并 active | `pipeline_engine.py --status` |
| G2 | checklist 已注册 | `pipeline_engine.py --validate` |
| G3 | git diff 无禁止修改文件 | `git diff --` 核对 |
| G4 | 禁止调度调用扫描通过 | `rg "generate_launchd|launchctl|crontab"` |

---

## 六、Token 预算

| 操作 | 预估 |
|:-----|:-----|
| 新增 shadow refresh 脚本 | ~200 行 → min token |
| 新增测试合约 | ~200 行 → min token |
| 修改 build 脚本适配 | ~20 行 → min token |
| 修改 checker 适配 | ~10 行 → min token |
| 运行 shadow refresh | ~1 分钟 |
| 运行测试 | ~30 秒 |
| **总计** | **低(~200 file operations)** |

---

## 七、设计约束验证

| 约束 | 状态 |
|:-----|:------|
| 单文件 ≤ 500 行 | ✅ shadow refresh 脚本预计 < 300 行 |
| 引擎变更后必须 Golden Master diff | ✅ 不涉及评分/排序/否决/相位变更 |
| code_level L1（模块化编排） | ✅ 仅调用已有服务，无核心逻辑新写 |
| 禁止产出正式买卖/仓位结论 | ✅ evidence 明确 production_ready=false |
| 禁止跨层直接调用 | ✅ 通过 subprocess 调用 build/checker 脚本 |
| 禁止跳过 pipeline stage | ✅ 走完整 G3 → G4 → G5 → G6 |
