# Baseline 权威契约

> 版本: 1.0 | 生效日期: 2026-06-02 | 维护人: 腰子+玉夜+阿黑

---

## 一、Baseline 权威源定义

所有日报、sidecar、统一解读、后评估引用 baseline 时，**唯一权威源**为：

```
00_项目地基/02_权威注册表/baseline_registry.json
```

任何其他位置（深度分析正文标题、深度分析附录旧 ID、历史日报、文件名中的 `deep_*`、人工输入的 baseline_id、模板示例）均**不得**作为 baseline_id 的引用源。

---

## 二、Baseline_id 命名规则

```
{股票6位代码}_W{年份4位}W{ISO周数2位}
```

示例：`600114_W2026W22` 表示 600114 在 2026年第22周的周度基线。

**禁止格式**（不完全列表）：

| 禁用格式 | 示例 |
|:---------|:-----|
| deep_ 前缀 | `600114_deep_20260529_v1.4` |
| 深度分析版本号 | `600114_deep_20260529` |
| 省略 ticker | `W2026W22` |
| 只有周数 | `W22` |
| 自定义命名 | `深度分析_v1.4` |

---

## 三、有效期规则

当前有效 baseline 的判定条件：

```
baseline_date <= trade_date <= valid_until
status != deprecated
```

匹配结果处理：

| 匹配数 | 处理 | 含义 |
|:------:|:-----|:------|
| **0 条** | ⛔ BLOCK | 无有效基线，日报生成不得提交 |
| **1 条** | ✅ PASS | 唯一有效基线，可使用 |
| **多条** | ⛔ BLOCK | 多基线冲突，需人工裁定 |

---

## 四、多基线冲突规则

如果 registry 对某个股票某个交易日返回多条有效基线，不得选择其中一条使用。必须：

1. BLOCK 日报生成
2. 输出冲突的 baseline_id 列表
3. 由腰子+阿黑人工裁定，裁定后更新 registry 或标记废弃

---

## 五、日报引用规则

日报生成前必须执行：

```bash
python3 scripts/resolve_current_baseline.py --code <代码> --name <名称> --date <日期> --json
```

日报引用的 baseline_id 必须与该命令返回的 `baseline_id` 完全一致。

日报 body 中的 `baseline_id` 和 sidecar JSON 中的 `baseline_id` 必须一致。

---

## 六、Sidecar 引用规则

sidecar JSON 中 `baseline_id` 字段的值必须与 registry 完全一致。

sidecar 内 machine_fields、eval_hooks、role_interpretations 中引用的 baseline_id 也必须与 registry 一致。

---

## 七、深度分析与日报的关系

深度分析是 baseline 的知识来源，但不是 baseline_id 的权威源。

- 深度分析报告正文可以写自己的版本号
- 但日报引用的 baseline_id 必须走 registry
- registry 中的 `source_report_path` 字段记录了深度分析报告的对应关系

---

## 八、日报生成前必须执行的命令

```bash
# 1. 解析当前有效 baseline
python3 scripts/resolve_current_baseline.py --code <代码> --name <名称> --date <日期> --json

# 2. 全池 baseline 权威检查
python3 scripts/check_baseline_authority.py --all --date <日期>
```

两者均返回 PASS 后，日报生成才可提交。

---

## 九、允许的旧口径处理方式

历史日报中出现的旧格式 baseline_id（如 `600114_deep_20260529_v1.4`）保持原地不动，不追溯修改。但：

- 新生成的日报必须使用规范格式
- 旧格式不得在新文档、schema、字段字典中作为示例出现
- 本契约生效后产生的所有日报必须合规

---

## 十、违规处理

| 违规类型 | 检测方式 | 处理 |
|:---------|:---------|:-----|
| baseline_id 不匹配 registry | `check_baseline_authority.py` | BLOCK，日报不得发布 |
| 无有效 baseline | `resolve_current_baseline.py` | BLOCK，需先确认基线 |
| 多有效 baseline | `resolve_current_baseline.py` | BLOCK，需人工裁定 |
| schema/文档含禁用示例 | 人工审查 | 需修改为规范示例 |
