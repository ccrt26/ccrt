# 飞书即时通信 → Claude Code 指令通道 — 架构设计

> 版本 v1.0 | 2026-05-29 | 情墨 | ⛔ SUPERSEDED by v1.1 — 本版本有6项设计缺陷，请使用 v1.1
> 关联：CLAUDE.md §六 角色协作协议 / CLAUDE.md §七 工程项目标准交付流程

---

## 一、需求概述

### 1.1 背景

用户通过 Mac 终端与 Claude Code 交互，无法离开电脑时仍需要下发指令（日报生成、深度分析、红线检查等）。飞书作为用户日常 IM 工具，可作为 Claude Code 的移动指令入口。

### 1.2 目标

用户通过飞书群 @机器人 发送指令 → Claude Code 执行 → 结果回传飞书群。

### 1.3 核心约束

- **零入站端口**：Mac 不监听任何端口，全部网络请求为出站
- **零第三方隧道**：不使用 ngrok 等内网穿透工具
- **零新增依赖**：仅用 Python 标准库（`urllib` + `json`）
- **个人化接入**：不依赖组织管理员审批

### 1.4 范围

- **纳入**：飞书 API 轮询拉取消息、指令解析与路由、结果回传、去重机制
- **不纳入**：指令执行本身（Claude Code 原生能力）、权限体系改造、指令黑名单（Phase 2）

---

## 二、技术架构

### 2.1 架构模式：定时轮询拉取（Pull）

```
                        你的 Mac（全部出站连接）
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  Cron (每分钟触发)                                            │
│      │                                                       │
│      ▼                                                       │
│  ┌─────────────────────────────────────────────────────┐     │
│  │  feishu_bridge.py  (~250行, L0)                      │     │
│  │                                                     │     │
│  │  ① POST 获取 tenant_access_token                     │     │
│  │  ② GET  拉取群最新消息列表                            │     │
│  │  ③ 去重 → 提取指令 → 写入 pending.json               │     │
│  │  ④ 读取 done.json → 回传结果                         │     │
│  │  ⑤ POST 回复飞书群                                   │     │
│  └──────┬──────────────────────┬───────────────────────┘     │
│         │                      │                              │
│         ▼                      ▼                              │
│  ┌──────────────┐    ┌──────────────────┐                    │
│  │ im_queue/     │    │ feishu_config.json                  │
│  │ pending.json  │    │ (App ID/Secret/群ID)                │
│  │ done.json     │    │ 权限: 600                           │
│  └──────────────┘    └──────────────────┘                    │
│                                                              │
│  无监听端口 · 无第三方隧道 · 纯标准库                          │
└──────────────────────────────────────────────────────────────┘
         │                              │
         │ HTTPS (仅出站)                │ HTTPS (仅出站)
         ▼                              ▼
┌──────────────────────┐    ┌──────────────────────┐
│ 飞书开放平台 API       │    │ 飞书开放平台 API       │
│ open.feishu.cn        │    │ open.feishu.cn        │
│                       │    │                       │
│ GET /im/v1/messages   │    │ POST /im/v1/messages  │
│     /:msg_id/reply    │    │                       │
└──────────────────────┘    └──────────────────────┘
```

### 2.2 技术选型

| 决策点 | 选择 | 理由 |
|:------|:-----|:-----|
| 脚本语言 | Python 3.9+ | 与项目主力脚本一致，标准库足够 |
| HTTP 客户端 | `urllib.request` | 零依赖，标准库内置 |
| 认证方式 | tenant_access_token (OAuth2) | 飞书服务端 API 标准认证 |
| 调度方式 | macOS launchd / crontab | 轻量，项目已有 Cron 管理脚本 |
| 消息轮询 | GET /im/v1/messages (page_size=10) | 拉最新 10 条，通过 msg_id 去重 |
| 结果回传 | POST /im/v1/messages/:msg_id/reply | 飞书回复消息 API，可直接回复用户 |
| 凭证存储 | 本地 JSON (chmod 600) | 零新增依赖，安全等级匹配 |

### 2.3 API 端点

| 端点 | 方法 | 用途 | 频率 |
|:-----|:-----|:-----|:-----|
| `/open-apis/auth/v3/tenant_access_token/internal` | POST | 获取 access_token (7200s 过期) | 每次轮询前检查过期 |
| `/open-apis/im/v1/messages` | GET | 拉取群消息列表 | 每分钟 1 次 (~1440次/天) |
| `/open-apis/im/v1/messages/:msg_id/reply` | POST | 回复消息（结果回传） | 每指令 1 次 |

> 飞书免费额度 5000次/天，1440 次 GET + 少量 POST 远在配额内。

---

## 三、模块设计

### 3.1 代码分级

| 组件 | 路径 | 级别 | 说明 |
|:---|:---|:---|:---|
| 桥接脚本 | `代码文件/tools/feishu_bridge.py` | **L0** | 工具/数据类，纯桥接无业务逻辑 |
| 配置文件 | `代码文件/tools/feishu_config.json` | L0 | App ID/Secret/群ID |
| 指令队列 | `.claude/im_queue/pending.json` | 数据 | 指令队列 |
| 结果队列 | `.claude/im_queue/done.json` | 数据 | 执行结果 |
| 知识库 | `.claude/knowledge/feishu_bridge.md` | M类 | 运维知识条目 |

> **L0 判定依据**：无评分/排序/风控/交易逻辑，无数据源变更，纯数据搬运。红结自查 + 新安常规审查即可。

### 3.2 feishu_bridge.py 结构

```
feishu_bridge.py (~250行)
├── class FeishuBridge
│   ├── __init__(config_path)          # 加载配置，初始化
│   ├── _get_token()                   # 获取/刷新 access_token (含过期检查)
│   ├── fetch_messages(chat_id)        # GET 拉取群消息列表
│   ├── filter_new(messages)           # 去重 + 提取 @机器人 文本
│   ├── write_pending(指令列表)         # 写入 pending.json
│   ├── read_done()                    # 读取 done.json 待回传结果
│   ├── reply_message(msg_id, text)    # POST 回复群消息
│   ├── _dedup()                       # msg_id 去重（内存 + 文件记录）
│   └── run()                          # 主循环：拉取 → 入队 → 读结果 → 回传
├── if __name__ == "__main__": run()
└── argparse: --init (首次验证) / --config (配置路径)
```

### 3.3 指令路由表

```python
ROUTE_TABLE = {
    "腰子":   {"role": "腰子", "action": "深度分析"},
    "日报":   {"role": "千光", "action": "每日简报生成"},
    "审计":   {"role": "旧影", "action": "全量审计"},
    "山猫":   {"role": "山猫", "action": "宏观分析"},
    "流金":   {"role": "流金", "action": "风控审计"},
    "青山":   {"role": "青山", "action": "策略分析"},
    "信鸽":   {"role": "信鸽", "action": "事件采集"},
    "玉夜":   {"role": "玉夜", "action": "数据巡检"},
    "红线检查": {"role": "旧影", "action": "红线检查"},
    "情墨":   {"role": "情墨", "action": "架构分析"},
}
# 未匹配的指令 → 原样转发给 Claude Code CLI
```

---

## 四、数据流与接口契约

### 4.1 指令队列格式

**pending.json**：
```json
{
  "queue": [
    {
      "id": "msg_om_x100x200x300x400x500",
      "cmd": "腰子分析600519",
      "chat_id": "oc_d79295e32b9f10312315b11bf1701be8",
      "msg_id": "om_x100x200x300x400x500",
      "ts": "2026-05-29T14:30:00"
    }
  ]
}
```

**done.json**：
```json
{
  "results": [
    {
      "id": "msg_om_x100x200x300x400x500",
      "status": "done",
      "reply": "600519 深度分析完成, PDF: 报告/重点股票/600519/...",
      "ts_done": "2026-05-29T14:32:00"
    }
  ]
}
```

### 4.2 配置文件格式

**feishu_config.json** (权限 600)：
```json
{
  "app_id": "cli_aa939df4f6385cbb",
  "app_secret": "********",
  "chat_id": "oc_d79295e32b9f10312315b11bf1701be8",
  "route_table": {},
  "dedup_file": ".claude/im_queue/processed_ids.json",
  "max_dedup": 200
}
```

### 4.3 接口契约

| 输入 | 来源 | 格式 |
|:-----|:-----|:-----|
| 飞书消息 | GET /im/v1/messages | 飞书标准 JSON |
| 指令文本 | 消息 `content` 字段 | `"@铁律量化助手 腰子分析600519"` |

| 输出 | 目标 | 格式 |
|:-----|:-----|:-----|
| pending.json | Claude Code 轮询消费 | JSON 队列 |
| done.json | feishu_bridge 读取回传 | JSON 队列 |
| 群回复 | 飞书群 | 飞书消息 API (文本格式) |

---

## 五、安全设计

| 层面 | 措施 | 实现 |
|:-----|:-----|:-----|
| 网络层 | **零入站端口** | 全部 HTTPS 出站，飞书 API 标准 TLS |
| 认证 | tenant_access_token | App ID + Secret 换取，7200s 过期自动刷新 |
| 凭证 | 本地文件 600 权限 | `chmod 600 feishu_config.json` |
| 消息 | 去重保护 | processed_ids.json，最多 200 条 |
| 执行 | 不直接执行 shell | bridge 只写入队列文件，不 eval/exec |
| 发送人 | 可选白名单 | 配置 `allowed_open_ids`，仅响应特定用户 |
| 审计 | 所有指令写入对话日志 | `临时报告/对话日志/` 按日期归档 |

---

## 六、Token 影响评估

> §七.2 ③ 要求，情墨设计文档必含此节。

| 评估项 | 影响 | 说明 |
|:---|:---|:---|
| 新增 Python 脚本 | +250 行 | L0 级别，红结自查 |
| 新增 JSON 配置 | +15 行 | 凭证 + 路由表 |
| 新增 Cron 调度 | +1 条目 | macOS crontab |
| API 调用频率 | 1440 次/天 GET | 飞书免费额度内 |
| **Claude Code Token 开销** | **极低** | bridge 本身不消耗 AI Token；仅在用户主动通过 IM 触发指令时按正常流程消耗 |
| 模板体积 | 0 | 无模板，纯脚本 |
| 输出模式 | 文本格式 | 群消息回复 ≤ 500 字摘要，文件路径引用 |

**结论**：bridge 是纯工程脚本，不涉及 AI 推理，Token 影响可忽略。旧影在闸门 1b 审查时确认即可。

---

## 七、部署方案

### 7.1 部署步骤

```
① 飞书开放平台 → 创建应用 → 添加权限 → 发布（已完成）
② 飞书客户端 → 建群"铁律指令" → 添加机器人（已完成）
③ 凭证：App ID / Secret / 群ID 已写入 feishu_config.json
④ 验证：python3 feishu_bridge.py --init（联通性检查）
⑤ 注册 Cron：每分钟执行 feishu_bridge.py
⑥ 端到端测试：群内发 @铁律量化助手 测试 → 收到回复
```

### 7.2 Cron 注册

```bash
# 每分钟检查一次（crontab -e）
* * * * * python3 /Users/ccrt/ccrt/代码文件/tools/feishu_bridge.py --config /Users/ccrt/ccrt/代码文件/tools/feishu_config.json
```

建议用项目已有的 `代码文件/tools/install_crontab.sh` 追加，或创建独立 launchd plist。

### 7.3 回滚方案

- 删除 crontab 条目即刻停用
- bridge 脚本不修改任何现有文件，删除即完全回滚
- 影响面仅限于 `.claude/im_queue/` 目录

---

## 八、需求 → 代码核对清单

> 情墨 + 腰子共同勾签后放行（§七.2）

| 序号 | 需求项 | 代码对应 | 勾签 |
|:----:|:------|:---------|:----:|
| 1 | 飞书 API 获取 access_token | `FeishuBridge._get_token()` | ☐ |
| 2 | 拉取群消息列表 | `FeishuBridge.fetch_messages()` | ☐ |
| 3 | 消息去重 | `FeishuBridge._dedup()` | ☐ |
| 4 | 提取 @机器人 指令文本 | `FeishuBridge.filter_new()` | ☐ |
| 5 | 写入指令队列 | `FeishuBridge.write_pending()` | ☐ |
| 6 | 读取执行结果 | `FeishuBridge.read_done()` | ☐ |
| 7 | 回复飞书群 | `FeishuBridge.reply_message()` | ☐ |
| 8 | Token 自动刷新 (7200s) | `_get_token()` 过期检查 | ☐ |
| 9 | 配置文件 600 权限 | `__init__` 加载时检查 | ☐ |
| 10 | --init 联通性验证 | `argparse --init` | ☐ |
| 11 | 指令路由表 | `ROUTE_TABLE` 字典 | ☐ |
| 12 | 已处理 msg_id 上限 (200) | `_dedup()` 自动修剪 | ☐ |

---

## 九、前置条件（已完成）

| 条件 | 状态 |
|:-----|:----:|
| 飞书应用创建 + 权限 + 发布 | ✅ |
| 个人群建群 + 机器人添加 | ✅ |
| App ID 获取 | ✅ |
| App Secret 获取 | ✅ |
| 群 ID 获取 | ✅ |
