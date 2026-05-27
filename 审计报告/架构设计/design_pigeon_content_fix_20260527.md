# 信鸽事件面板"加载原文"故障修复 — 架构设计

> 版本 v1.0 | 2026-05-27 | 情墨 | pipeline_stage: complete
> 关联：design_pigeon_web_v1.0.md | portal_template.html | pigeon_dashboard.html
> 需求来源：用户报告 https://ccrt26.github.io/ccrt/#events 点击事件卡片"加载原文"长时间等待后失败

---

## 一、问题诊断

### 1.1 根因

事件点击处理使用原生 `fetch()` 调用 `/api/event-content`，而非 `api()` mock 函数。静态站点（GitHub Pages）上该路径无后端服务，fetch 收到 404 HTML 后 `r.json()` 抛异常，触发 `.catch()` 显示"原文加载失败"。

### 1.2 次要问题

渲染优先级不合理：`hasPdf=true` 时一律显示"加载原文中..."并触发 fetch，即使事件已有预嵌入的 content 摘要。在静态站点下：
- 预嵌入 content 是 cninfo 截断摘要（~100字），不是完整公告
- 真正的 PDF 全文提取只能靠 `pigeon_server.py` 服务器模式
- 完整阅读只能通过 PDF 直接下载按钮

### 1.3 涉及文件

| 文件 | 问题行 | 说明 |
|:-----|:------|:-----|
| `portal_template.html` | L1134-1149 | 渲染优先级：hasPdf 优先于 hasContent |
| `portal_template.html` | L1236-1257 | fetch() 裸调用 /api/event-content |
| `pigeon_dashboard.html` | L893-907 | 同上渲染优先级 |
| `pigeon_dashboard.html` | L1001-1022 | 同上 fetch() 裸调用 |

---

## 二、修复方案

### 2.1 策略：按数据可用性渲染，零网络请求

```
事件展开
  ├─ hasPdf && hasContent → 直接展示预嵌入 content 摘要 + PDF下载按钮（不fetch）
  ├─ hasPdf && !hasContent → 直接显示"暂无摘要，请通过PDF按钮查看原文"（不fetch）
  ├─ !hasPdf && hasContent → 直接展示预嵌入 content 摘要（现有逻辑，不改）
  └─ !hasPdf && !hasContent → 显示降级提示（现有逻辑，不改）
```

### 2.2 具体改动

**改动A — portal_template.html (L1134-1149)**

```javascript
// 旧逻辑：hasPdf 优先 → 一律显示"加载原文中..."
if (hasPdf) {
  contentArea = '<div class="detail-section">...加载原文中...</div>';
} else if (hasContent) { ... }

// 新逻辑：有content优先直接展示，无content但有pdf显示指引
if (hasContent) {
  contentArea =
    '<div class="detail-section">' +
      '<div class="detail-section-title">' + (hasPdf ? '公告摘要' : '公告全文') + '</div>' +
      '<div class="detail-content">' + esc(e.content) + '</div>' +
    '</div>';
} else if (hasPdf) {
  contentArea =
    '<div class="detail-section">' +
      '<div class="detail-section-title">公告全文</div>' +
      '<div class="detail-content detail-no-content">暂无摘要，请通过下方PDF按钮查看原文</div>' +
    '</div>';
}
```

**改动B — portal_template.html (L1236-1257)**

删除整个 `if (!wasExpanded)` 块中的 fetch 逻辑（含 `.loading-content` 查找和 fetch 调用）。展开时不再发起任何网络请求。

**改动C — pigeon_dashboard.html**

同样两处改动（L893-907 渲染优先级 + L1001-1022 删除 fetch）。

### 2.3 CSS

新增一条 `.detail-no-content` 样式（灰色提示文本），替换已无用的 `.loading-content` 和 `.loading-spinner`（保留不删，避免影响未知引用）。

---

## 三、影响评估

| 维度 | 评估 |
|:-----|:-----|
| 影响范围 | 仅事件面板展开行为，不影响其他标签页（深度分析/日报） |
| 服务器模式兼容 | 服务器模式下 fetch 本来可用，但返回的也是同一份 content 摘要。改动后两种模式体验一致，均直接展示 |
| 降级路径 | PDF 直接下载按钮始终可用（cninfo 直链），用户可下载完整公告 |
| 数据格式 | 不变，仍读取 events[].content 和 events[].pdf_url |
| 回归风险 | 低。仅修改事件卡片展开渲染逻辑，不涉及数据管线 |

---

## 四、代码分级

| 文件 | 等级 | 理由 |
|:-----|:----:|:-----|
| portal_template.html | L1 | 策略/展示层，涉及用户可见行为变更 |
| pigeon_dashboard.html | L1 | 同上 |

---

## 五、验证计划

1. 本地浏览器打开 portal_template.html，点击事件卡片验证：有content的直接展示摘要，无content但有pdf的显示指引文字
2. 运行 `generate_portal.py` 重新生成静态站点，浏览器打开 `docs/index.html` 验证三个标签页均正常
3. PDF 下载按钮点击后正确打开 cninfo PDF 链接
4. 筛选/搜索/统计面板功能不受影响

---

## 六、需求→代码核对清单

- [ ] portal_template.html: 渲染优先级 content > pdf
- [ ] portal_template.html: 删除事件展开时的 fetch(/api/event-content) 调用
- [ ] pigeon_dashboard.html: 渲染优先级 content > pdf
- [ ] pigeon_dashboard.html: 删除事件展开时的 fetch(/api/event-content) 调用
- [ ] generate_portal.py 重新生成 docs/index.html
- [ ] 本地验证：展开卡片直接显示摘要，无加载等待
- [ ] PDF按钮功能正常

> 情墨签字：___________ | 腰子签字：___________
