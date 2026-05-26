# 架构设计: 代码安全防护三层体系 + 角色中文昵称重组 + Sector API修复
> 设计人: 情墨 | 日期: 2026-05-25 (事后补) | 对应 commit: `b627916`

## 一、模块划分

### 1.1 代码安全防护三层体系
```
Layer 1 — PreToolUse Hook (.claude/hooks/PreToolUse_hook.ps1)
  └─ 拦截写操作，检查操作分类 (M/L/E)
Layer 2 — 写保护 Hook (代码文件/监督机制/write_protection_hook.ps1)
  └─ E类变更令牌验证，无令牌拒绝写入代码文件/
Layer 3 — Pre-commit Check (.claude/hooks/pre-commit-check.ps1)
  └─ 提交前红线检查 + 越界扫描
```

### 1.2 角色中文昵称重组
- 英文名 → 中文昵称: Alpha→青山, Vega→流金, Pulse→玉夜, Sentinel→山猫, Gauge→旧影, Arch→情墨, Forge→千光, Proof→新安, Dock→红枫, Craft→红结
- 影响范围: `.claude/agents/` (10个agent定义), `.claude/commands/` (12个command文件)
- 新增角色: 红结 (代码工匠), 审计统一入口, 红线检查

### 1.3 Sector API修复
- `_patch_sector_trend.py`: 东财板块API兼容修复
- `test_sector_api.ps1`: 板块API回归测试
- 数据流: 东财板块API[7] → sector_trend patch → engine/sector.py

## 二、接口契约

| 模块 | 输入 | 输出 | 消费者 |
|:-----|:-----|:-----|:-----|
| PreToolUse Hook | Tool call parameters | 放行/拦截 + 分类标签 | Claude harness |
| Write Protection Hook | 文件路径 + 操作类型 | 放行/拒绝 (E类无令牌=拒绝) | 文件系统写操作 |
| Pre-commit Check | Staged changes diff | PASS/FAIL + 违规清单 | Git commit |
| Sector API Patch | 东财原始JSON | 标准化sector_trend | engine/sector.py |
| Pipeline Token | -Start/-Advance/-Complete | pipeline_active.json | 全流程 |

## 三、数据流
```
Claude tool call → PreToolUse_hook(分类M/L/E)
  → Write_protection_hook(E类→验证令牌)
    → pre-commit-check(红线+越界扫描)
      → Git commit
```

## 四、风险点
- Hook链任一环节失败可能导致正常操作被拦截 (已加白名单机制)
- 角色名称变更后旧脚本引用需同步更新 (已全局替换)

## 五、需求→代码核对清单
- [x] 写操作分类拦截 → PreToolUse_hook.ps1 + write_protection_hook.ps1
- [x] 提交前扫描 → pre-commit-check.ps1
- [x] 角色全量重命名 → 10 agents + 12 commands
- [x] Sector API修复 → _patch_sector_trend.py + test_sector_api.ps1
- [x] 流程令牌管理 → pipeline_token.ps1
- [x] Boundary Scan自动化 → gauge_boundary_scan.ps1

> 情墨签字: 情墨 ✅ | 腰子确认: 不涉及金融逻辑 ✅
