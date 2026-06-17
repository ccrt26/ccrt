已调用 skill: ccrt-standard-flow
流程阶段: G0/G1/G2/G3
本输出性质: 执行命令包

# G3_EXEC_重点股票分析池重构第1步_精准执行包_v0.1

> 日期：2026-06-17
> 适用对象：阿黑团队转派执行；DeepSeek/执行模型只执行 G3 与生成 G4 自检候选
> 上位方案：
> - `00_项目地基/06_后评估闭环/PLAN_重点股票产品化分析闭环总框架_v0.1.md`
> - `00_项目地基/06_后评估闭环/PLAN_重点股票分析池治理与产品化驱动方案_v0.1.md`
> 当前边界：只做股票池重构第 1 步，不进入第 2 步消费者切换，不修改正式生产入口。

---

## 0. 身份边界与阶段边界

1. 阿黑团队仅负责路由、转派、排期、汇总和回传，不签署 G5/G6，不代替旧影/腰子作结论。
2. DeepSeek/执行模型只允许执行本包授权的 G3 实施，并输出 G4 自检候选。
3. 本包不授权进入 G5 独立复查，也不授权进入 G6 放行、归档、GitHub 同步或生产切换。
4. 本包只授权“股票池重构第 1 步”：建立权威池契约、schema、checker、adapter、服务读取适配、shadow/兼容导出和验收证据。
5. 本包不授权“股票池重构第 2 步”：不切换日报生产 pipeline、深度分析 pipeline、launchd、正式报告生成入口或历史目录扫描策略。

---

## 1. 前置检查结论

读取上位方案后确认：

1. 重点股票产品化闭环要求从“多个脚本各自猜股票池”升级为“一个权威分析池驱动生产线、后评估、产品 API 和页面”。
2. 当前 active 股票池只保留：

```text
600114 东睦股份
```

3. 旧 `代码文件/信鸽信息采集/pigeon_config.json` 仍保留多只消息采集 target，但不得作为当前重点股票 active 分析池来源。
4. `00_项目地基/02_权威注册表/daily_report_targets.json` 当前 active target 已只包含 `600114 东睦股份`，但后续应降级为 `keystock_analysis_pool.json` 的镜像/兼容文件。
5. `代码文件/重点股票/product_eval/stock_pool.py` 当前仍存在代码内池成员定义，第 1 步应改为读取注册表并保留兼容输出。
6. 历史报告、历史深度分析、历史 baseline 不能删除，也不能反向决定当前 active 池。

---

## 2. 流程编号与阶段门

流程编号：

```text
F-ANALYSIS / F-GATE 混合路径
```

阶段门：

```text
G0: 需求识别与路由 - 已完成
G1: 业务/金融口径确认 - 已完成候选：当前 active 只保留 600114，允许后续用户特例/暂停/出池
G2: 技术方案确认 - 已完成候选：注册表/schema/checker/adapter 先行
G3: 本包授权范围内实施 - 待阿黑团队转派执行
G4: 执行方自检候选 - G3 完成后输出
G5: 旧影独立复查 - 本包不执行
G6: 腰子放行归档 - 本包不执行
```

用户可见状态：

```text
AUTO_REPAIRING
```

含义：进入第 1 步实施与自检准备，但不得越界触碰生产入口、正式报告、baseline registry 或规则资产。

---

## 3. 第 1 步目标

用最小可回滚方式建立 `KeystockAnalysisPool` 权威契约，让后续系统能稳定回答：

```text
当前正式重点分析池有哪些股票？
哪些股票可做正式日报/深度分析？
哪些股票只是用户特例、候选、暂停或已出池？
旧消息采集池和历史报告是否被误当成当前 active？
```

第 1 步完成后必须满足：

1. 当前 active 只返回 `600114 东睦股份`。
2. 支持后续用户特例、暂停、出池的字段、状态和 dry-run 接口设计，但本步骤不实际新增用户特例、不暂停、不出池任何股票。
3. `daily_report_targets.json` 只能作为镜像/兼容产物，不再被定义为最终权威源。
4. 产品池服务读取权威注册表，仍保持现有 product API 兼容输出。
5. 负向验收能证明 `pigeon_config.json` 中其他股票不会进入第 1 步目标范围。

---

## 4. 允许修改范围

只允许修改或新增以下文件。

### 4.1 权威注册表与 schema

```text
00_项目地基/02_权威注册表/keystock_analysis_pool.json
00_项目地基/04_一致性闸门/keystock_analysis_pool.schema.json
```

用途：

1. 建立当前分析池权威源。
2. 写入当前 active 唯一成员 `600114 东睦股份`。
3. 预留 `active/user_override/candidate/paused/archived` 状态字段。
4. 预留用户特例、暂停、出池、复核和 change_log 字段，但不执行真实用户特例变更。

### 4.2 服务与适配器

```text
代码文件/重点股票/product_eval/stock_pool.py
scripts/keystock_analysis_pool.py
scripts/check_keystock_analysis_pool.py
```

用途：

1. `stock_pool.py` 改为读取 `keystock_analysis_pool.json`，保留 `ProductStockPoolService.build_pool()` 兼容输出。
2. `scripts/keystock_analysis_pool.py` 提供 CLI/adapter：validate、active、daily-targets、deep-targets、data-warmup-targets、message-watch-targets、dry-run export。
3. `scripts/check_keystock_analysis_pool.py` 负责一致性检查和负向验收。

### 4.3 产品 API shadow/兼容检查

```text
代码文件/重点股票/product_eval/product_api_bundle.py
scripts/build_keystock_product_api_bundle.py
scripts/check_keystock_dashboard_productization.py
```

用途：

1. 仅允许让产品 API 消费新的 `ProductStockPoolService` 输出。
2. 仅允许 shadow/staging 验证 `stock_pool.json`、`dashboard.json`、`today_decisions.json` 与 pool 一致。
3. 不允许切换正式生产发布入口。

### 4.4 测试文件

```text
tests/keystock_product_eval/test_stock_pool_contract.py
tests/keystock_product_eval/test_analysis_pool_contract.py
tests/keystock_product_eval/test_analysis_pool_product_api_contract.py
```

用途：

1. 验证正向 active 范围。
2. 验证负向旧池污染。
3. 验证用户特例/暂停/出池字段存在和 dry-run 行为，但不执行真实状态变更。

### 4.5 证据产物目录

只允许写入：

```text
运行产物/重点股票分析池重构/20260617_g3_step1/
```

必须输出：

```text
pool_validate_result.json
pool_active_targets.json
pool_daily_targets.json
pool_deep_targets.json
pool_data_warmup_targets.json
pool_message_watch_targets.json
daily_report_targets_export_dry_run.json
product_api_pool_consistency_check.json
pytest_output.txt
git_diff_scope.txt
no_production_touch_evidence.json
g4_self_check_candidate.md
```

---

## 5. 禁止修改范围

以下范围一律禁止修改，触碰即 BLOCK：

```text
00_项目地基/02_权威注册表/baseline_registry.json
重点股票/股票报告/
重点股票/深度分析/深度分析报告/
重点股票/基线/
运行产物/daily_report_build/
代码文件/信鸽信息采集/pigeon_config.json
launchd / crontab / runtime production entry
正式交易、仓位、止损、规则资产
历史旧股票报告目录
历史旧 baseline
```

以下行为也禁止：

1. 删除旧股票历史报告、历史基线或历史深度分析。
2. 批量删除 `pigeon_config.json` 中旧 target。
3. 把历史报告目录扫描结果当成当前 active 池。
4. 把 `600114` 写死在日报、深度分析、前端或产品 API 逻辑中。
5. 生成正式日报或正式深度分析。
6. 进入第 2 步消费者切换。
7. 修改 launchd、定时任务、生产发布脚本或正式运行入口。
8. 输出 G5 PASS、G6 放行或任何角色签署结论。

---

## 6. 文件清单与操作类型

| 文件 | 操作 | 是否必做 | 说明 |
|:--|:--|:--|:--|
| `00_项目地基/02_权威注册表/keystock_analysis_pool.json` | 新增 | 必做 | 当前分析池权威源；active 只含 600114 |
| `00_项目地基/04_一致性闸门/keystock_analysis_pool.schema.json` | 新增 | 必做 | 注册表 schema |
| `代码文件/重点股票/product_eval/stock_pool.py` | 修改 | 必做 | 读取注册表并保持兼容输出 |
| `scripts/keystock_analysis_pool.py` | 新增 | 必做 | 统一 adapter/CLI |
| `scripts/check_keystock_analysis_pool.py` | 新增 | 必做 | pool checker 与负向验收 |
| `代码文件/重点股票/product_eval/product_api_bundle.py` | 修改 | 可选 | 仅当当前 bundle 未消费服务时才改 |
| `scripts/build_keystock_product_api_bundle.py` | 修改 | 可选 | 仅允许 shadow/staging 消费新池 |
| `scripts/check_keystock_dashboard_productization.py` | 修改 | 可选 | 仅补 pool 一致性检查 |
| `tests/keystock_product_eval/test_stock_pool_contract.py` | 新增/修改 | 必做 | 产品池契约测试 |
| `tests/keystock_product_eval/test_analysis_pool_contract.py` | 新增 | 必做 | 分析池契约测试 |
| `tests/keystock_product_eval/test_analysis_pool_product_api_contract.py` | 新增 | 必做 | 产品 API scope 一致性测试 |
| `运行产物/重点股票分析池重构/20260617_g3_step1/*` | 新增 | 必做 | G4/G5 证据 |

---

## 7. AcceptanceScopeContract

本次验收必须先验收范围，再看命令结果。命令通过但范围错误，仍为 BLOCK。

```json
{
  "contract_id": "AcceptanceScopeContract.keystock_analysis_pool.g3_step1.v0.1",
  "date": "2026-06-17",
  "positive_acceptance": {
    "active_pool": [
      {
        "stock_code": "600114",
        "stock_name": "东睦股份",
        "membership_status": "active"
      }
    ],
    "required_status_support": [
      "active",
      "user_override",
      "candidate",
      "paused",
      "archived"
    ],
    "required_modes_support": [
      "daily",
      "deep",
      "product_view",
      "message_watch",
      "data_warmup"
    ],
    "required_contracts": [
      "keystock_analysis_pool.json validates against schema",
      "ProductStockPoolService reads registry instead of hardcoded mutable pool",
      "adapter returns active/daily/deep/data_warmup/message_watch targets",
      "product API shadow data is consistent with stock pool",
      "daily_report_targets export dry-run contains only pool daily targets"
    ]
  },
  "negative_acceptance": {
    "forbidden_active_codes_from_legacy_sources": [
      "603019",
      "301075",
      "601689",
      "000967",
      "601727",
      "002230",
      "603092",
      "300736",
      "300450"
    ],
    "must_not_enter": [
      "daily_analysis_targets",
      "deep_analysis_targets",
      "product dashboard active list",
      "daily_report_targets enabled=true mirror"
    ],
    "forbidden_sources_as_authority": [
      "代码文件/信鸽信息采集/pigeon_config.json",
      "历史报告目录扫描",
      "历史 baseline 目录扫描"
    ],
    "forbidden_changes": [
      "baseline_registry.json",
      "正式日报正文或 sidecar",
      "正式深度分析报告",
      "launchd/runtime production entry",
      "正式规则资产",
      "历史旧股票资产删除"
    ]
  },
  "out_of_scope_but_schema_ready": [
    "add user_override",
    "pause member",
    "archive member",
    "exit_pending recommendation",
    "production pipeline switch"
  ]
}
```

验收结论规则：

1. 正向验收任一必选项缺失：WARN 或 BLOCK。
2. 负向验收任一旧股票进入 active/daily/deep/product active：BLOCK。
3. 修改禁止范围：BLOCK。
4. 用户特例、暂停、出池只要求 schema/adapter/dry-run 支持，不要求真实执行。

---

## 8. 实施顺序

严格按以下顺序执行。任一步失败，不得继续扩大范围。

### Step 1. 建立注册表与 schema

目标：

1. 新增 `keystock_analysis_pool.json`。
2. 新增 `keystock_analysis_pool.schema.json`。
3. 当前 members 只包含 `600114 东睦股份`，状态 `active`。
4. 预留 `user_override/candidate/paused/archived` 状态支持。

禁止：

1. 不修改 `daily_report_targets.json` 正式文件。
2. 不修改 `baseline_registry.json`。

### Step 2. 建立 checker

目标：

1. 新增 `scripts/check_keystock_analysis_pool.py`。
2. 校验 schema、唯一 active、状态合法、旧池污染、mirror dry-run 一致性。
3. 输出 JSON 证据到 `运行产物/重点股票分析池重构/20260617_g3_step1/pool_validate_result.json`。

### Step 3. 改造 ProductStockPoolService

目标：

1. `ProductStockPoolService` 从注册表读取成员。
2. `build_pool()` 保持原 product API 可消费结构。
3. 保留兼容字段 `status/display_order/source_refs`。
4. 不在代码里写死可变池成员。

### Step 4. 新增 adapter CLI

目标：

支持以下命令：

```bash
python3 scripts/keystock_analysis_pool.py --validate
python3 scripts/keystock_analysis_pool.py --active --json
python3 scripts/keystock_analysis_pool.py --daily-targets --json
python3 scripts/keystock_analysis_pool.py --deep-targets --json
python3 scripts/keystock_analysis_pool.py --data-warmup-targets --json
python3 scripts/keystock_analysis_pool.py --message-watch-targets --json
python3 scripts/keystock_analysis_pool.py --export-daily-targets --out 00_项目地基/02_权威注册表/daily_report_targets.json --dry-run
python3 scripts/keystock_analysis_pool.py --add-user-override 000001 --name 测试特例 --reason "验收dry-run" --dry-run
python3 scripts/keystock_analysis_pool.py --pause 600114 --reason "验收dry-run" --dry-run
python3 scripts/keystock_analysis_pool.py --archive 600114 --reason "验收dry-run" --dry-run
```

注意：

1. `--add-user-override/--pause/--archive` 本步骤只允许 dry-run。
2. 不允许 `--write` 真实变更用户特例、暂停或出池。

### Step 5. 产品 API shadow 一致性

目标：

1. 如需修改 product API，只允许 shadow/staging 消费新池服务。
2. 验证 `stock_pool.json`、`dashboard.json`、`today_decisions.json` 只展示当前 pool 成员。
3. 证据写入 `product_api_pool_consistency_check.json`。

禁止：

1. 不切正式 dashboard。
2. 不发布生产 bundle。

### Step 6. 测试与证据落盘

目标：

1. 运行验收命令。
2. 收集所有证据文件。
3. 输出 `g4_self_check_candidate.md`。
4. 输出 path-limited `git_diff_scope.txt`，证明未越界。

---

## 9. 验收范围

### 9.1 正向验收

必须证明：

1. `keystock_analysis_pool.json` 合法。
2. active 只包含：

```text
600114 东睦股份
```

3. daily targets 只包含 `600114 东睦股份`。
4. deep targets 在有 baseline_due 或规则要求时只从 pool 成员投影，不从旧目录扩池。
5. 产品 API shadow 中 active/dashboard/today_decisions 与 pool 一致。
6. 用户特例、暂停、出池具备 dry-run 能力和字段支持，但未真实改变成员状态。

### 9.2 负向验收

必须证明：

1. `pigeon_config.json` 中除 `600114` 外的旧股票没有进入 active/daily/deep/product active。
2. 历史报告目录不会反向扩池。
3. `daily_report_targets.json` dry-run export 不多出 pool 外 enabled target。
4. user_override 缺 baseline 时不会生成正式日报结论。
5. paused/archived 不进入当前 active dashboard。
6. baseline registry、正式报告、正式深度分析、生产入口未被修改。

---

## 10. 验收命令

在仓库根目录执行：

```bash
python3 -m json.tool 00_项目地基/02_权威注册表/keystock_analysis_pool.json
python3 -m json.tool 00_项目地基/04_一致性闸门/keystock_analysis_pool.schema.json
python3 scripts/keystock_analysis_pool.py --validate
python3 scripts/keystock_analysis_pool.py --active --json
python3 scripts/keystock_analysis_pool.py --daily-targets --json
python3 scripts/keystock_analysis_pool.py --deep-targets --json
python3 scripts/keystock_analysis_pool.py --data-warmup-targets --json
python3 scripts/keystock_analysis_pool.py --message-watch-targets --json
python3 scripts/keystock_analysis_pool.py --export-daily-targets --out 00_项目地基/02_权威注册表/daily_report_targets.json --dry-run
python3 scripts/keystock_analysis_pool.py --add-user-override 000001 --name 测试特例 --reason "验收dry-run" --dry-run
python3 scripts/keystock_analysis_pool.py --pause 600114 --reason "验收dry-run" --dry-run
python3 scripts/keystock_analysis_pool.py --archive 600114 --reason "验收dry-run" --dry-run
python3 scripts/check_keystock_analysis_pool.py --json
python3 -m pytest tests/keystock_product_eval/test_stock_pool_contract.py
python3 -m pytest tests/keystock_product_eval/test_analysis_pool_contract.py
python3 -m pytest tests/keystock_product_eval/test_analysis_pool_product_api_contract.py
git diff -- 00_项目地基/02_权威注册表/keystock_analysis_pool.json 00_项目地基/04_一致性闸门/keystock_analysis_pool.schema.json 代码文件/重点股票/product_eval/stock_pool.py 代码文件/重点股票/product_eval/product_api_bundle.py scripts/keystock_analysis_pool.py scripts/check_keystock_analysis_pool.py scripts/build_keystock_product_api_bundle.py scripts/check_keystock_dashboard_productization.py tests/keystock_product_eval/test_stock_pool_contract.py tests/keystock_product_eval/test_analysis_pool_contract.py tests/keystock_product_eval/test_analysis_pool_product_api_contract.py
git status --short
```

验收命令不得运行：

```bash
scripts/run_daily_production_pipeline.py
scripts/run_daily_report_one_by_one.py
launchctl
crontab
任何正式日报生成命令
任何正式深度分析生成命令
```

---

## 11. 证据路径

执行完成后必须落盘：

```text
运行产物/重点股票分析池重构/20260617_g3_step1/pool_validate_result.json
运行产物/重点股票分析池重构/20260617_g3_step1/pool_active_targets.json
运行产物/重点股票分析池重构/20260617_g3_step1/pool_daily_targets.json
运行产物/重点股票分析池重构/20260617_g3_step1/pool_deep_targets.json
运行产物/重点股票分析池重构/20260617_g3_step1/pool_data_warmup_targets.json
运行产物/重点股票分析池重构/20260617_g3_step1/pool_message_watch_targets.json
运行产物/重点股票分析池重构/20260617_g3_step1/daily_report_targets_export_dry_run.json
运行产物/重点股票分析池重构/20260617_g3_step1/product_api_pool_consistency_check.json
运行产物/重点股票分析池重构/20260617_g3_step1/pytest_output.txt
运行产物/重点股票分析池重构/20260617_g3_step1/git_diff_scope.txt
运行产物/重点股票分析池重构/20260617_g3_step1/no_production_touch_evidence.json
运行产物/重点股票分析池重构/20260617_g3_step1/g4_self_check_candidate.md
```

`no_production_touch_evidence.json` 至少包含：

```json
{
  "baseline_registry_modified": false,
  "formal_daily_reports_modified": false,
  "formal_deep_reports_modified": false,
  "launchd_modified": false,
  "production_entry_modified": false,
  "pigeon_config_modified": false,
  "historical_assets_deleted": false,
  "step2_consumers_switched": false
}
```

---

## 12. WARN/BLOCK 口径

### 12.1 PASS 条件

全部满足才可作为 G4 自检候选 PASS：

1. active/daily/product active 均只含 `600114 东睦股份`。
2. schema/checker/adapter/服务/测试全部通过。
3. 负向旧池污染检查通过。
4. 所有证据落盘。
5. 未触碰禁止范围。

### 12.2 WARN 条件

以下情况可 WARN，但不得伪装 PASS：

1. product API shadow 有非关键展示字段缺失，但 active scope 正确。
2. message_watch/data_warmup dry-run 字段不完整，但未进入正式日报。
3. 用户特例 dry-run 缺少后续数据预热实现，但已明确本步骤不实现。
4. 历史 archived 股票仍有旧报告，但未进入当前 active/product active。

### 12.3 BLOCK 条件

出现任一项即 BLOCK：

1. 任一非池股票进入 daily/deep/product active 范围。
2. `daily_report_targets.json` dry-run enabled=true 多出 pool 外股票。
3. `--all` 或 checker 仍通过历史报告目录扩池。
4. user_override 缺 baseline 却可生成正式日报结论。
5. 修改 `baseline_registry.json`。
6. 修改正式日报、正式深度分析、生产入口、launchd 或正式规则资产。
7. 删除历史报告、历史 baseline 或历史深度分析。
8. 未落盘关键证据却声称 PASS。
9. DeepSeek/执行模型签署 G5/G6 或冒充项目角色。

---

## 13. 回滚/不切生产证明

### 13.1 回滚原则

第 1 步必须可回滚：

1. 新增注册表/schema/checker/adapter 可以整体撤回。
2. `stock_pool.py` 如适配失败，可回退到旧服务实现，但必须在 G4 风险中标记“旧逻辑存在旧池污染风险”。
3. product API 只允许 shadow/staging 验证，不能因失败影响正式页面。
4. 不触碰 baseline registry、正式报告、正式深度分析、生产入口，因此无需生产回滚。

### 13.2 不切生产证明

G4 自检必须明确证明：

```text
未运行正式日报生成
未运行正式深度分析生成
未修改 launchd/crontab/runtime production entry
未修改 baseline_registry.json
未修改正式日报正文/sidecar
未修改正式深度分析报告
未删除历史资产
未把 daily pipeline 切换到新 adapter
```

---

## 14. 给阿黑团队的转派文本

请阿黑团队按以下边界转派执行：

```text
本次只执行 G3：重点股票分析池重构第 1 步。

目标：
建立 keystock_analysis_pool.json 权威池、schema、checker、adapter，并让 ProductStockPoolService 读取权威池。当前 active 只保留 600114 东睦股份。支持后续用户特例、暂停、出池的字段和 dry-run，但本次不真实新增特例、不暂停、不出池。

禁止：
不进入第 2 步；不切日报/深度分析生产入口；不改 baseline_registry；不改正式日报/深度分析；不改 launchd；不删历史资产；不改 pigeon_config；不签 G5/G6。

执行完成后：
输出 G4 自检候选和证据目录：
运行产物/重点股票分析池重构/20260617_g3_step1/

验收必须包含 AcceptanceScopeContract 的正向验收和负向验收。任一旧股票从 pigeon_config 或历史目录进入 active/daily/deep/product active，直接 BLOCK。
```

---

## 15. 当前结论

本文件为 G3 精准执行包，可交阿黑团队转派执行。

当前状态：

```text
AUTO_REPAIRING
```

未进入：

```text
第 2 步消费者切换
G4 最终自检
G5 旧影复查
G6 腰子放行
生产发布
```
