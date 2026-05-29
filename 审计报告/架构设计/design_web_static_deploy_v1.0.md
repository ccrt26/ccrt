# Web静态托管免费部署方案 — 架构设计

> pipeline_stage: complete | 设计人：情墨 | 日期：2026-05-29 | 版本：v1.0

---

## 一、需求摘要

用户希望将项目生成的静态 HTML 报告（深度分析报告、模拟交易统一视图、健康报告等）部署到免费托管平台，不走 GitHub Pages。须同时满足：
- 免费（零成本）
- 不从 GitHub 仓库拉取代码（直接上传本地构建产物）
- 可脚本化，集成到现有管线

---

## 二、平台选型

### 2.1 候选对比

| 维度 | Cloudflare Pages | Netlify | Vercel | surge.sh |
|:-----|:---------------:|:-------:|:------:|:--------:|
| 免费额度 | 无限带宽/无限请求 | 100GB/月 | 100GB/月 | 免费 |
| 全球CDN | 330+节点 | 中等 | 中等 | 无 |
| 本地直传 | wrangler CLI | netlify-cli | vercel CLI | surge CLI |
| CLI依赖 | Node.js (npx可用) | Node.js | Node.js | Node.js |
| 自定义域名 | 免费 | 免费 | 免费 | 收费 |
| 同时上传文件数 | 20,000+ | 1,000 | 5,000 | — |
| HTTPS | 自动 | 自动 | 自动 | 自动 |

### 2.2 选型结论

**主方案：Cloudflare Pages**

理由：
1. 免费层最慷慨 — 无限带宽，无请求数限制，不担心流量
2. wrangler CLI 支持 `wrangler pages publish <目录>` 一键上传本地目录，零 Git 依赖
3. 330+ 全球 CDN 节点，国内访问速度可接受
4. 支持自定义域名（未来可选）
5. `npx wrangler` 零安装使用，不污染项目依赖

**备选：Netlify** — 如 Cloudflare 不可用，功能对等，但带宽有限额

---

## 三、部署架构

### 3.1 数据流

```
┌──────────────────────┐
│  报告产出目录          │
│  临时报告/*.html      │
│  docs/*.html          │
│  模拟交易/展示/*.html  │
└──────┬───────────────┘
       │ deploy_web.py 读取
       ▼
┌──────────────────────┐
│  deploy_web.py       │  ← L0 工具
│  - 收集HTML文件       │
│  - 构造部署目录       │
│  - 调用 wrangler     │
└──────┬───────────────┘
       │ subprocess
       ▼
┌──────────────────────┐
│  npx wrangler         │
│  pages publish <dir>  │
└──────┬───────────────┘
       │ HTTPS
       ▼
┌──────────────────────┐
│  Cloudflare Pages     │
│  <project>.pages.dev  │
└──────────────────────┘
```

### 3.2 模块等级：L0（工具/数据/缓存）

不涉及评分/交易/风控/红线逻辑，红结自查 + 新安常规测试即可。

---

## 四、文件变更计划

### 4.1 新增文件

| 文件 | 用途 | 预估行数 |
|:-----|:-----|:--------|
| `代码文件/tools/deploy_web.py` | 部署脚本：收集文件→构造目录→调用wrangler→输出URL | ~120行 |
| `代码文件/tools/deploy_web_config.json` | 配置文件：Cloudflare项目名、部署目录映射 | ~20行 |

### 4.2 不修改现有文件

本次设计不修改任何现有代码文件。仅在管线集成阶段（阶段⑥红枫）可选注入调度链。

---

## 五、接口契约（I9：Web部署）

### 5.1 命令行接口

```
python3 代码文件/tools/deploy_web.py [--source <dir>] [--dry-run]
```

| 参数 | 必填 | 默认值 | 说明 |
|:-----|:----:|:------|:-----|
| `--source` | 否 | 配置文件中的全部目录 | 指定单个部署目录 |
| `--dry-run` | 否 | false | 仅收集文件列表，不上传 |

### 5.2 config.json 格式

```json
{
  "cloudflare": {
    "project_name": "tl-quant-reports",
    "account_id": "从环境变量 CF_ACCOUNT_ID 读取"
  },
  "source_dirs": [
    {"path": "临时报告", "include": "*.html", "recursive": false},
    {"path": "docs", "include": "*", "recursive": true},
    {"path": "模拟交易/展示", "include": "*.html", "recursive": false}
  ],
  "index_file": "index.html",
  "deploy_branch": "main"
}
```

### 5.3 环境变量（敏感信息不进文件）

| 变量 | 说明 | 获取方式 |
|:-----|:-----|:---------|
| `CF_API_TOKEN` | Cloudflare API Token | Cloudflare Dashboard → API Tokens |
| `CF_ACCOUNT_ID` | Cloudflare Account ID | Cloudflare Dashboard → Overview |

### 5.4 输出契约

```json
{
  "status": "success",
  "url": "https://tl-quant-reports.pages.dev",
  "deployment_id": "abc123",
  "file_count": 15,
  "timestamp": "2026-05-29T22:00:00+08:00"
}
```

### 5.5 错误处理

| 场景 | 处理 |
|:-----|:-----|
| wrangler未安装 | 提示 `npm install -g wrangler` 或使用 `npx wrangler` |
| API Token未设置 | 提示设置 `CF_API_TOKEN` 环境变量 |
| 部署失败 | 返回非0退出码 + stderr日志 |
| 源目录无文件 | WARN，跳过空目录 |

---

## 六、影响评估

### 6.1 上游影响：无
现有报告生成流程不变，deploy_web.py 只读取已生成文件。

### 6.2 下游影响：无
deploy_web.py 是叶子节点，没有下游模块消费其输出。

### 6.3 技术债务
- Node.js 环境：wrangler 需要 Node.js 运行时，但可通过 `npx` 按需下载，不锁定项目级依赖
- 不在 ADR 黑名单冲突范围内（黑名单禁止的是"用 Node.js 替代 PowerShell"，此为部署工具，性质不同）

### 6.4 需要通知的角色
- 红枫（环境配置：确认 Node.js/npm 可用）
- 千光（可选：将部署集成到日终调度）

---

## 七、回退方案

1. 不使用 deploy_web.py → 不影响任何现有功能（完全隔离的新模块）
2. Cloudflare Pages 不可用 → 切换到 Netlify（修改 config.json 的 provider 字段，接口不变）
3. 完全不用 web 托管 → 报告仍在本地文件系统可用，不影响日常工作

---

## 八、第三方依赖评估

| 依赖 | 类型 | 是否新增 | 评审 |
|:-----|:-----|:--------|:-----|
| `wrangler` (Cloudflare CLI) | Node.js CLI工具 | 是 | 部署工具，非项目代码依赖。通过 `npx` 按需使用，不写入 requirements.txt |
| Python `subprocess` | 标准库 | 否 | 已存在 |
| Python `json` | 标准库 | 否 | 已存在 |

wrangler 满足第三方库引入条件：
- 必要性：有（实现本地直传Cloudflare Pages的唯一官方工具）
- 不改变项目语言选型
- 通过 npx 零安装使用，不污染项目依赖树
- 许可证：MIT（Cloudflare官方维护）

---

## 九、Token影响评估

| 维度 | 评估 |
|:-----|:-----|
| 新增代码量 | ~140行（120行Python + 20行JSON） |
| API调用模式 | subprocess单次调用，无增量API |
| 输出模式 | 单JSON行输出，无大段文本 |
| 模板体积 | 无模板，不生成报告 |
| 对现有模块影响 | 零（独立模块，不被其他模块import） |
| 预估Token增量 | <5%（仅当手动调用时产生输出） |

---

## 十、需求→代码核对清单

| 编号 | 检查项 | 白皮书/红线条款 | 情墨勾 | 腰子勾 |
|:----:|:------|:-------------|:-----:|:-----:|
| R1 | 免费方案，无付费依赖 | 用户需求 | ☐ | ☐ |
| R2 | 不从GitHub拉取代码 | 用户需求 | ☐ | ☐ |
| R3 | 可脚本化集成管线 | 用户需求 | ☐ | ☐ |
| R4 | 不修改现有模块 | 红线§七 | ☐ | ☐ |
| R5 | 不引入不应引入的技术 | ADR§3.1黑名单 | ☐ | ☐ |
| R6 | 敏感信息不进代码文件 | 安全基线 | ☐ | ☐ |
| R7 | 文件不超过500行 | 红线§9.2 | ☐ | ☐ |

---

## 十一、自查清单（13项）

| 编号 | 审查项 | 通过 | 备注 |
|:----:|:-------|:----:|:-----|
| CH1 | 模块边界 | ✅ | 单文件，职责唯一：收集→部署 |
| CH2 | 接口完整 | ✅ | CLI参数+config+环境变量+输出JSON |
| CH3 | 1+2架构 | N/A | 不涉及数据获取 |
| CH4 | 第三方依赖 | ✅ | wrangler通过npx按需使用 |
| CH5 | 循环依赖 | ✅ | 叶子节点，无被依赖 |
| CH6 | 单点故障 | ✅ | 部署失败不影响本地报告 |
| CH7 | 反模式 | ✅ | 未触发AP-01至AP-07 |
| CH8 | 影响范围 | ✅ | 零影响（独立模块） |
| CH9 | API超时 | N/A | 不调用API，wrangler自带重试 |
| CH10 | 回退方案 | ✅ | 独立模块，删除即可回退 |
| CH11 | 通知关联 | ✅ | 仅通知红枫 |
| CH12 | 红线合规 | ✅ | 不触发任何红线 |
| CH13 | 数据加载阻塞 | N/A | 不涉及数据加载 |

---

> 审批流：情墨 → 腰子（闸门1a）→ 新安+旧影（闸门1b）→ 红结 → 新安 → 红枫 → 后评估
