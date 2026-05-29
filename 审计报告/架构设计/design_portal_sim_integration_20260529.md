# 模拟交易统一视图 · 门户集成 — 架构设计

> **pipeline_stage**: complete | **日期**: 2026-05-29 | **设计者**: 情墨

---

## 一、变更概述

将模拟交易统一视图整合入"铁律量化 · 重点股票门户"（`docs/index.html`），作为第 4 个 Tab。同时将相关文件按门户标准归档至 `docs/` 目录。

## 二、集成方案

**方案选择：iframe 嵌入。** 理由：
- 统一视图有独立 CSS/JS（Canvas 图表 + 筛选逻辑），iframe 天然隔离样式冲突
- 可独立打开、独立刷新，不依赖门户 JS 状态
- 与其他 Tab 的"嵌入子页面"模式一致

## 三、文件变更

| 文件 | 操作 | 说明 |
|:-----|:-----|:-----|
| `docs/index.html` | 修改 | 新增第 4 个 Tab "模拟交易"，iframe 嵌入 `sim_trading/模拟交易统一视图.html` |
| `docs/sim_trading/模拟交易统一视图.html` | 新增 | 由 generate_unified_view.py 生成到该路径 |
| `模拟交易/分析/generate_unified_view.py` | 修改 | 默认输出路径改为 `docs/sim_trading/` |
| `模拟交易/分析/strategy_annotations.json` | 保持不变 | 已是正式项目文件 |

## 四、门户 Tab 结构

```
┌─ 事件面板 ──┬── 深度分析报告 ──┬── 分析日报 ──┬── 模拟交易(NEW) ──┐
│  信鸽数据   │   深度分析报告    │   日报文件    │   iframe 嵌入       │
└─────────────┴─────────────────┴──────────────┴───────────────────┘
```

## 五、iframe 规格

- src: `sim_trading/模拟交易统一视图.html`（相对路径）
- 全宽，高度自适应（通过 postMessage 或固定 `min-height: 100vh`）
- 无边框，背景色与门户统一（`#1a1a2e`）
- 懒加载：Tab 切换至"模拟交易"时才加载 iframe

## 六、生成脚本变更

`generate_unified_view.py` 输出路径：
- 默认：`docs/sim_trading/模拟交易统一视图.html`
- 可通过 `--output` 参数覆盖

## 七、品牌一致性

统一视图 HTML 使用门户 CSS 变量体系（`--bg-primary: #1a1a2e` 等），确保嵌入后视觉统一。

## 八、模块分级

| 文件 | 等级 | 行数估算 |
|:-----|:----:|:-------:|
| docs/index.html | L1 | +30行（新增Tab+iframe） |
| generate_unified_view.py | L0 | -5行（改默认路径） |

## 九、Token 影响

无新增模板/Agent/API 调用。仅修改 HTML Tab 结构和 Python 默认路径。

## 十、需求→代码核对清单

- [ ] docs/index.html 新增第 4 个 Tab "模拟交易"
- [ ] Tab 内容为 iframe 嵌入 `sim_trading/模拟交易统一视图.html`
- [ ] iframe 懒加载（切换 Tab 时触发）
- [ ] generate_unified_view.py 默认输出改为 `docs/sim_trading/`
- [ ] 统一视图 HTML 使用门户 CSS 变量体系
- [ ] docs/sim_trading/ 目录加入 git
