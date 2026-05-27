# 信鸽门户 Liquid Glass 重构 — 架构设计

> pipeline_stage: complete
> 设计者: 情墨 | 日期: 2026-05-27 | 代码分级: L0 (UI层，不涉及评分/交易/风控逻辑)
> 目标文件: `代码文件/信鸽信息采集/portal_template.html`

---

## 一、现状评估

### 1.1 当前架构

```
portal_template.html (1415行)
├── <style> (845行 CSS) — 暗色玻璃态 v2.0
├── <body> 三标签页结构 (events / deep / daily)
└── <script> (420行 JS) — Tab切换 + API渲染 + 过滤
```

### 1.2 现有设计的优点（保留）

- CSS变量体系完整（颜色/圆角/阴影/间距/字号/过渡）
- 玻璃态基础已具备（backdrop-filter + 半透明背景）
- 响应式布局已覆盖 1024px / 768px 断点
- 骨架屏/空状态/降级状态 交互完整
- 入场动画（fadeInUp + stagger）已实现

### 1.3 现有设计的不足（本次重构目标）

| 问题 | 现状 | 目标 |
|:-----|:-----|:-----|
| 玻璃质感太平 | 单一 uniform blur，无深度层次 | 多层液态玻璃，有景深感 |
| 色彩单一 | 功能色为主，缺乏品牌感 | 弥散光渐变，科技蓝紫品牌色 |
| 字体档次不够 | Microsoft YaHei 为主 | SF/PingFang/Inter 系统字体栈 |
| 留白不足 | 信息密度偏高 | 极简2.0，8px网格，大留白 |
| 卡片缺"微光" | 普通半透明边框 | 虹彩边缘 + 内发光 + 悬浮辉光 |
| 导航不够精致 | 基础 tab 下划线 | 胶囊式导航 + 滚动隐藏动效 |
| Hero区缺失 | 直接进入数据 | 品牌Hero区展示核心指标 |
| 移动端体验 | 基础适配 | 手势友好 + 底部导航 |

---

## 二、设计系统（Design System）

### 2.1 色彩系统

```css
:root {
  /* === 基底（宇宙黑系）=== */
  --bg-deep-space: #08080f;        /* 最深背景 */
  --bg-cosmic: #0c0e16;            /* 主背景 */
  --bg-void: #111318;              /* 卡片底色 */

  /* === 弥散光品牌色 === */
  --accent-primary: #007AFF;       /* Apple蓝 */
  --accent-secondary: #5E5CE6;     /* 科技紫 */
  --accent-tertiary: #00C7BE;      /* 青绿（数据点缀） */

  /* === 弥散光渐变（关键！）=== */
  --gradient-hero: radial-gradient(ellipse 60% 50% at 50% -20%, rgba(0,122,255,0.15) 0%, transparent 70%),
                   radial-gradient(ellipse 40% 40% at 80% 50%, rgba(94,92,230,0.08) 0%, transparent 70%);
  --gradient-card-glow: linear-gradient(135deg, rgba(0,122,255,0.06) 0%, rgba(94,92,230,0.04) 50%, rgba(0,199,190,0.03) 100%);

  /* === 液态玻璃层级 === */
  --glass-l1: rgba(255,255,255,0.03);    /* 最透明 — 背景卡片 */
  --glass-l2: rgba(255,255,255,0.05);    /* 中等 — 主要内容卡片 */
  --glass-l3: rgba(255,255,255,0.08);    /* 最实 — 悬浮/激活态 */

  /* === 玻璃边框（虹彩）=== */
  --glass-border-1: rgba(255,255,255,0.06);   /* 静态 */
  --glass-border-2: rgba(255,255,255,0.10);   /* 悬浮 */
  --glass-border-glow: rgba(0,122,255,0.15);  /* 辉光 */

  /* === 数据色（保留原有涨跌语义）=== */
  --data-up: #e74c3c;       /* 红涨（不变） */
  --data-down: #27ae60;     /* 绿跌（不变） */
  --data-neutral: #7f8c8d;
}
```

### 2.2 字体系统

```css
--font-system: -apple-system, BlinkMacSystemFont, "SF Pro Display",
              "PingFang SC", "Inter", "Helvetica Neue",
              "Microsoft YaHei", sans-serif;
--font-mono: "SF Mono", "JetBrains Mono", "Cascadia Code", monospace;

/* 层级 */
--text-hero:    56px / 1.1 / -0.02em;   /* Hero大数字 */
--text-display: 36px / 1.2 / -0.01em;   /* 板块标题 */
--text-title:   22px / 1.3 / 0;          /* 卡片标题 */
--text-body:    15px / 1.6 / 0;          /* 正文 */
--text-caption: 12px / 1.5 / 0.02em;     /* 辅助文字 */
```

### 2.3 间距系统（8px基准）

```
--space-0:  0
--space-1:  4px    (0.5x)
--space-2:  8px    (1x)
--space-3:  12px   (1.5x)
--space-4:  16px   (2x)
--space-5:  24px   (3x)
--space-6:  32px   (4x)
--space-7:  48px   (6x)
--space-8:  64px   (8x)
--space-9:  96px   (12x)
--page-margin: 24px (mobile) / 48px (tablet) / 80px (desktop)
```

### 2.4 圆角系统

```
--radius-sm: 8px     /* 标签/按钮 */
--radius-md: 14px    /* 卡片 */
--radius-lg: 20px    /* 大卡片/Hero */
--radius-xl: 28px    /* 模态框 */
--radius-full: 9999px /* 胶囊/药丸 */
```

### 2.5 阴影与辉光层级

```
--elevation-0: none;
--elevation-1: 0 1px 2px rgba(0,0,0,0.3);                    /* 微浮 */
--elevation-2: 0 4px 16px rgba(0,0,0,0.4);                   /* 卡片 */
--elevation-3: 0 8px 32px rgba(0,0,0,0.5);                   /* 悬浮卡片 */
--elevation-4: 0 16px 48px rgba(0,0,0,0.6);                  /* 模态 */

/* 辉光（液态玻璃的灵魂） */
--glow-subtle: 0 0 20px rgba(0,122,255,0.08);                /* 静态辉光 */
--glow-medium: 0 0 40px rgba(0,122,255,0.12);                /* 悬浮辉光 */
--glow-strong: 0 0 60px rgba(0,122,255,0.18);                /* Hero辉光 */
```

---

## 三、页面架构重设计

### 3.1 整体布局结构（从上到下）

```
┌──────────────────────────────────────────┐
│  Header (sticky, 液态玻璃, 自动隐藏)      │
├──────────────────────────────────────────┤
│  Tab Nav (胶囊式, sticky, 与Header联动)   │
├──────────────────────────────────────────┤
│                                          │
│  [Tab 1: Events]                         │
│  ┌──────────────────────────────────┐    │
│  │  Hero Section                     │    │
│  │  - 大数字（事件总数/覆盖股票）     │    │
│  │  - 弥散光背景 + 粒子/网格动画     │    │
│  ├──────────────────────────────────┤    │
│  │  Summary Bento Grid (2x2 → 1x4)  │    │
│  │  - 液态玻璃卡片 + 微光描边       │    │
│  ├──────────────────────────────────┤    │
│  │  Filter Bar (胶囊式)              │    │
│  ├──────────────────────────────────┤    │
│  │  Event Cards (可折叠列表)         │    │
│  │  - 虹彩左边框 + 悬浮辉光         │    │
│  │  - 点击展开详情（弹簧动效）      │    │
│  └──────────────────────────────────┘    │
│                                          │
│  [Tab 2/3: Reports]                      │
│  ┌──────────────────────────────────┐    │
│  │  Section Title + 弥散光装饰      │    │
│  ├──────────────────────────────────┤    │
│  │  Bento Grid 报告卡片              │    │
│  │  - 封面缩略图区域                │    │
│  │  - 元数据 + 操作按钮             │    │
│  └──────────────────────────────────┘    │
│                                          │
│  Footer (极简)                            │
└──────────────────────────────────────────┘
```

### 3.2 关键组件设计

#### 3.2.1 Header + 导航栏

- **液态玻璃Header**: `backdrop-filter: blur(24px)` + `background: rgba(12,14,22,0.75)`
- **底部渐变分割线**: `linear-gradient(90deg, transparent, #007AFF40, #5E5CE640, transparent)`
- **滚动行为**: 向下滚动时Header自动隐藏（`translateY(-100%)`），向上滚动时显示
- **Tab导航**: 胶囊式按钮，激活态有内发光，hover时辉光扩散
- **状态指示器**: 脉冲呼吸光点 + "系统在线"文字

#### 3.2.2 Hero Section（仅Events标签）

- 大面积留白（上下各64px）
- 居中展示核心KPI数字（事件总数），字号56px/weight 800
- 背景使用弥散光渐变 + 微妙的CSS网格纹理
- 数字有微弱的`text-shadow`辉光
- 副标题使用`text-caption`样式，`letter-spacing: 2px`大写

#### 3.2.3 Bento Grid 概览卡片

- 2×2 (desktop) / 1×4 (mobile) 不对称网格
- 第一个卡片（事件总数）占更大面积（span 1.5x）
- 液态玻璃三层结构:
  - 底层: `--glass-l1` + `backdrop-filter: blur(20px)`
  - 中层: 微妙的渐变叠加 (--gradient-card-glow)
  - 顶层: 0.5px 内描边 (inset box-shadow) 模拟玻璃边缘
- 悬浮态: `translateY(-4px)` + 辉光扩散 + 边框变亮
- 数字使用`font-variant-numeric: tabular-nums`保持对齐

#### 3.2.4 事件卡片（可折叠列表）

- 极简行样式（默认折叠）:
  - 左侧3px虹彩指示条（利好红/利空绿/中性灰，带辉光）
  - 股票名 + 代码 | 标签组 | 标题（单行省略）| 影响分数
- 展开态:
  - 弹簧动效（`cubic-bezier(0.34, 1.56, 0.64, 1)` — 轻微过冲回弹）
  - 详情区域淡入 + 下滑
  - 卡片背景变实（`--glass-l1` → `--glass-l2`）
- 悬浮态: 虹彩边框微光 + 2px上浮

#### 3.2.5 报告卡片（Tab 2/3）

- Bento网格不规则排列
- 每个卡片:
  - 顶部彩色渐变条（股票特征色）
  - 股票名 + 代码
  - 报告日期 + 文件大小
  - HTML/PDF 按钮（胶囊形，带图标）
- 缺失态: 半透明 + "暂缺"徽标

#### 3.2.6 过滤栏

- 胶囊形容器（`border-radius: 28px`）
- 内嵌select/button，统一圆角风格
- 方向按钮: 分段控制器样式（类似iOS Segmented Control）
- 搜索框: 透明背景 + 底部单线 + focus时辉光

#### 3.2.7 Footer

- 极简设计：一行文字居中
- 顶部渐变分割线
- 字号11px，颜色`--text-muted`

---

## 四、动画与微交互设计

### 4.1 入场动画序列

```
页面加载:
  Hero数字  (0ms)   → scale(0.95)→1 + fade in, 600ms
  概览卡片   (stagger 80ms each) → fadeInUp
  过滤栏     (400ms) → fadeInUp
  事件卡片   (stagger 40ms each) → fadeInUp + 微上浮
```

### 4.2 悬浮微交互

| 元素 | 动效 |
|:-----|:-----|
| 概览卡片 | `translateY(-4px)` + `box-shadow`扩散 + border变亮, 300ms |
| 事件卡片 | `translateY(-2px)` + 左边框辉光 + `scale(1.005)`, 250ms |
| 标签按钮 | 背景色过渡 + 微缩放, 150ms |
| 报告卡片 | `translateY(-3px)` + 渐变条辉光, 300ms |
| 按钮 | `translateY(-1px)` + shadow lift, 200ms |

### 4.3 点击/展开

- 事件卡片展开: 弹簧曲线 `cubic-bezier(0.34, 1.56, 0.64, 1)` + max-height过渡
- Tab切换: 内容区 crossfade + 微下滑
- 方向按钮: `scale(0.96)` on active

### 4.4 滚动驱动（可选增强）

- Header背景: 随滚动从透明 → 实色
- Hero区: 视差慢速滚动
- 卡片: `@scroll-timeline` 驱动的渐入

---

## 五、响应式策略

### 5.1 断点设计

| 断点 | 宽度 | 布局变化 |
|:-----|:-----|:-----|
| Mobile | < 640px | 单列，Hero缩小，底部Tab导航 |
| Tablet | 640-1024px | 双列网格，侧边距增大 |
| Desktop | > 1024px | 完整布局，大留白，多列Bento |
| Wide | > 1440px | 最大宽度1440px居中，两侧超大留白 |

### 5.2 移动端特殊处理

- Tab导航固定在底部（`position: fixed; bottom: 0`）替代顶部
- 过滤栏折叠为"筛选"按钮 + 弹出面板
- 事件卡片全宽，分数移到右上角
- 触控目标最小44×44px（符合iOS HIG）
- 下拉刷新手势支持

---

## 六、技术实现策略

### 6.1 文件结构

```
portal_template.html          → 重构后的门户主页（单文件，<700行）
  ├── <style>   (~400行)      → CSS变量 + 全局样式 + 组件样式 + 响应式
  ├── <body>    (~100行)      → 语义化HTML结构
  └── <script>  (~200行)      → 保持现有API逻辑，仅修改渲染模板
```

### 6.2 兼容性降级

```css
/* 不支持 backdrop-filter 的浏览器 */
@supports not (backdrop-filter: blur(1px)) {
  .glass-card { background: rgba(17,19,24,0.95); }
}
/* 减少动画偏好 */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; }
}
```

### 6.3 性能约束

- 动画仅使用 `transform` + `opacity`（避免触发layout/paint）
- `backdrop-filter` 总数 ≤ 15个元素（避免GPU过载）
- 滚动事件使用 `passive: true` + `requestAnimationFrame` 节流
- 字体使用 `font-display: swap` 避免FOIT

### 6.4 代码等级

| 模块 | 等级 | 理由 |
|:-----|:----:|:-----|
| CSS设计系统 | L0 | 纯视觉，不涉及业务逻辑 |
| HTML结构 | L0 | 静态模板，数据由JS注入 |
| JS数据渲染 | L0 | 仅修改模板字符串，API逻辑不變 |
| **全文件** | **L0** | UI层重构，零业务逻辑变更 |

---

## 七、与现有系统的兼容

### 7.1 不变项（保证）

- ✅ API端点路径（`/api/summary`, `/api/events`, `/api/stocks`, `/api/daily_stats`）
- ✅ 数据格式（JSON字段名、结构完全不变）
- ✅ 过滤逻辑（股票/日期/类别/方向/搜索）
- ✅ 报告卡片数据源（`window.__PORTAL_DATA__`）
- ✅ 品牌色变量名（`--accent-up`, `--accent-down` 等保留，值可微调）
- ✅ PDF链接、cninfo链接功能
- ✅ 过滤漏斗统计面板

### 7.2 变更项

- 🔄 CSS变量值全面升级（新增玻璃层级/辉光/弥散光渐变）
- 🔄 HTML结构重新组织（新增Hero区、重构卡片DOM）
- 🔄 JS渲染模板字符串更新（保持数据绑定，改HTML结构）
- 🔄 动画曲线和时长调整
- 🔄 移动端断点和导航策略

---

## 八、实施计划

### Phase 1: CSS设计系统重写（核心）
- 重写 `:root` 变量
- 全局reset + body背景
- 字体系统 + 排版层级
- 液态玻璃mixin类

### Phase 2: 组件逐个重写
- Header + Tab导航（胶囊式）
- Hero区（仅Events标签）
- Bento概览卡片
- 过滤栏
- 事件卡片（含展开态）
- 报告卡片
- Footer

### Phase 3: 响应式 + 动画
- 移动端断点
- 入场动画
- 悬浮微交互
- 滚动行为

### Phase 4: 验证
- 桌面端Chrome/Edge/Firefox
- 移动端Safari/Chrome
- 暗色模式一致性
- API数据正确渲染
- 所有交互功能正常

---

## 九、风险评估

| 风险 | 概率 | 影响 | 缓解 |
|:-----|:----:|:----:|:-----|
| backdrop-filter性能 | 低 | 中 | 限制使用数量，移动端降级 |
| 移动端Safari兼容 | 中 | 中 | -webkit-前缀，测试真机 |
| HTML行数超500红线 | 高 | 低 | 单文件合理性申明（前端单文件部署需求） |
| 用户对风格不满意 | 低 | 高 | 保留CSS变量体系，方便微调 |

---

## 十、需求→代码核对清单

| 编号 | 检查项 | 用户需求 | 情墨勾 |
|:----:|:------|:------|:-----:|
| R1 | 液态玻璃拟态卡片 | "Liquid Glass"效果 | ☐ |
| R2 | 深色宇宙黑背景 | 深邃科技感 | ☐ |
| R3 | 弥散光品牌渐变 | #007AFF → 科技蓝紫 | ☐ |
| R4 | SF/PingFang/Inter字体 | Apple风格字体 | ☐ |
| R5 | 8px网格系统 | 视觉节奏一致 | ☐ |
| R6 | 极简2.0大留白 | Hero区+页边距 | ☐ |
| R7 | Bento网格布局 | 卡片式分类 | ☐ |
| R8 | 可折叠卡片列表 | 点击展开详情 | ☐ |
| R9 | 顶部导航 | 胶囊式Tab | ☐ |
| R10 | 移动端适配 | 响应式+底部导航 | ☐ |
| R11 | 核心数据完整保留 | API/数据不变 | ☐ |
| R12 | 悬浮微动效 | 辉光+上浮+虹彩边框 | ☐ |
| R13 | 品牌色冻结 | 涨跌色保持不变 | ☐ |

---

> 下一步: 腰子确认设计方向 → 新安+旧影审查 → 红结编码实现
