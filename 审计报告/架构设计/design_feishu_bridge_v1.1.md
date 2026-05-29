# 飞书即时通信 → Claude Code 指令通道 — 架构设计

> 版本 v1.1 | 2026-05-29 | 情墨 | pipeline_stage: complete
> v1.0→v1.1：情墨自审 + 旧影审计，修复队列消费/错误处理/日志/调度/配置路径6项缺陷
> 关联：CLAUDE.md §六 角色协作协议 / CLAUDE.md §七 工程项目标准交付流程

---

## 一、需求概述

### 1.1 背景

用户通过 Mac 终端与 Claude Code 交互，无法离开电脑时需要持续下发指令。飞书作为日常 IM，可作为 Claude Code 的移动指令入口。

### 1.2 目标

飞书群 @机器人 发指令 → Claude Code 执行 → 结果回传飞书群。

### 1.3 核心约束

- **零入站端口**：Mac 不监听任何端口，全部网络请求为出站
- **零第三方隧道**：不使用 ngrok 等内网穿透工具
- **零新增依赖**：仅用 Python 标准库（`urllib` + `json`）
- **个人化接入**：不依赖组织管理员审批

### 1.4 范围

- **纳入**：飞书 API 轮询拉取消息、指令解析与路由、结果回传、去重机制、错误处理、日志
- **不纳入**：Claude Code 指令执行本身（已有能力）、权限体系改造、多群支持（Phase 2）

---

## 二、技术架构

### 2.1 架构模式：定时轮询拉取（Pull）+ 文件队列解耦

```
┌──────────────────────────────────────────────────────────────────┐
│                         你的 Mac                                  │
│                                                                  │
│  launchd (~/Library/LaunchAgents/com.tielv.feishu-bridge.plist)  │
│      │  每分钟触发                                                │
│      ▼                                                           │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │  feishu_bridge.py  (~280行, L0)                          │     │
│  │                                                          │     │
│  │  ① POST 获取 tenant_access_token (含过期检查+重试)        │     │
│  │  ② GET  拉取群最新消息列表 (含网络异常降级)               │     │
│  │  ③ 去重 + 提取 @机器人 文本                               │     │
│  │  ④ 写入 .claude/im_queue/pending.json                    │     │
│  │  ⑤ 读取 .claude/im_queue/done.json → 回传结果            │     │
│  │  ⑥ POST 回复飞书群                                       │     │
│  │  ⑦ 写入日志 临时报告/对话日志/feishu_bridge_YYYY-MM-DD.log│     │
│  └─────────┬───────────────────┬───────────────────────────┘     │
│            │                   │                                  │
│            ▼                   ▼                                  │
│  ┌──────────────────┐  ┌──────────────────────────┐              │
│  │ .claude/im_queue/ │  │ ~/.feishu_bot_tmp.json  │              │
│  │ pending.json      │  │ (App ID/Secret/群ID)    │              │
│  │ done.json         │  │ chmod 600               │              │
│  │ processed_ids.json│  └──────────────────────────┘              │
│  └──────────────────┘                                            │
│                                                                  │
│  零监听端口 · 零第三方隧道 · 纯标准库 · 全部出站                    │
└──────────────────────────────────────────────────────────────────┘
         │                              │
         │ HTTPS :443 (仅出站)           │ HTTPS :443 (仅出站)
         ▼                              ▼
┌──────────────────────┐    ┌──────────────────────┐
│ 飞书开放平台 API       │    │ 飞书开放平台 API       │
│ open.feishu.cn        │    │ open.feishu.cn        │
│ GET /im/v1/messages   │    │ POST /im/v1/messages  │
│     /:msg_id/reply    │    │                       │
└──────────────────────┘    └──────────────────────┘
```

### 2.2 技术选型

| 决策点 | v1.0 | v1.1 修正 | 理由 |
|:------|:-----|:----------|:-----|
| 调度方式 | crontab | **launchd** | macOS crontab 感知不到，休眠会导致漏执行；launchd 可补跑 |
| 凭证存储 | `代码文件/tools/feishu_config.json` | **`~/.feishu_bot_tmp.json`** | Secret 不应在项目目录内，用户 Home 目录更安全 |
| HTTP 超时 | 未定义 | **连接 10s，读取 30s** | 防止网络异常导致脚本卡死 |
| 日志 | 未定义 | **`临时报告/对话日志/feishu_bridge_YYYY-MM-DD.log`** | 符合项目日志规范 |
| 路由表 | 代码内硬编码 | **配置文件内 `route_table` 字段** | 更新路由不需改代码 |

### 2.3 API 端点

| 端点 | 方法 | 用途 | 频率 | 超时 |
|:-----|:-----|:-----|:-----|:-----|
| `/open-apis/auth/v3/tenant_access_token/internal` | POST | 获取 access_token (7200s) | Token 过期前刷新 | 10s |
| `/open-apis/im/v1/messages` | GET | 拉取群消息列表 (page_size=10) | 每分钟 1 次 | 30s |
| `/open-apis/im/v1/messages/:msg_id/reply` | POST | 回复消息 | 每指令 1 次 | 10s |

> 频率 ~1440次/天，飞书免费额度 5000次/天，充足。

---

## 三、模块设计

### 3.1 代码分级

| 组件 | 路径 | 级别 | 说明 |
|:---|:---|:---|:---|
| 桥接脚本 | `代码文件/tools/feishu_bridge.py` | **L0** | 工具/数据类，纯桥接无业务逻辑 |
| 凭证文件 | `~/.feishu_bot_tmp.json` | — | 敏感信息，用户 Home 目录，600 权限 |
| 指令队列 | `.claude/im_queue/pending.json` | 数据 | 指令入队 |
| 结果队列 | `.claude/im_queue/done.json` | 数据 | 结果出队 |
| 去重记录 | `.claude/im_queue/processed_ids.json` | 数据 | 已处理 msg_id 列表 |
| 日志文件 | `临时报告/对话日志/feishu_bridge_YYYY-MM-DD.log` | 日志 | 每日一个文件 |
| 知识库 | `.claude/knowledge/feishu_bridge.md` | M类 | 运维知识条目 |
| launchd plist | `~/Library/LaunchAgents/com.tielv.feishu-bridge.plist` | — | macOS 定时任务 |

> **L0 判定依据**：无评分/排序/风控/交易逻辑，无数据源变更，纯数据搬运。

### 3.2 feishu_bridge.py 结构

```
feishu_bridge.py (~280行)
├── 常量
│   ├── FEISHU_AUTH_URL / MESSAGES_URL / REPLY_URL
│   ├── CONNECT_TIMEOUT = 10 / READ_TIMEOUT = 30
│   └── DEFAULT_CONFIG_PATH = "~/.feishu_bot_tmp.json"
├── class FeishuBridge
│   ├── __init__(config_path)          # 加载配置，校验必填字段，检查文件权限
│   ├── _get_token()                   # 获取/刷新 token (缓存+过期检查，减少API调用)
│   ├── _request(url, data, method)    # 统一HTTP请求 (超时+异常处理+日志)
│   ├── fetch_messages(chat_id)        # GET 拉取群消息列表
│   ├── filter_new(messages)           # 去重 + 提取 @机器人 文本
│   ├── write_pending(指令)            # 写入 pending.json
│   ├── read_done()                    # 读取 done.json，返回已完成结果列表
│   ├── mark_done_processed(ids)       # 标记已回传的结果 (防止重复回复)
│   ├── reply_message(msg_id, text)    # POST 回复群消息
│   ├── _dedup(msg_id)                 # 检查+记录 msg_id，Redis式环状裁剪到 max_dedup
│   ├── _log(msg)                      # 统一日志输出 (文件+stdout)
│   └── run()                          # 主循环
├── main()
│   ├── arg: --init  首次联通性验证 (不写队列，不回复)
│   ├── arg: --config 自定义配置路径
│   └── arg: --once  单次执行 (默认，供 launchd 调用)
├── if __name__ == "__main__": main()
```

### 3.3 指令路由表（配置文件内）

```json
{
  "route_table": {
    "腰子":   {"role": "腰子", "action": "深度分析"},
    "日报":   {"role": "千光", "action": "每日简报生成"},
    "审计":   {"role": "旧影", "action": "全量审计"},
    "山猫":   {"role": "山猫", "action": "宏观分析"},
    "流金":   {"role": "流金", "action": "风控审计"},
    "青山":   {"role": "青山", "action": "策略分析"},
    "信鸽":   {"role": "信鸽", "action": "事件采集"},
    "玉夜":   {"role": "玉夜", "action": "数据巡检"},
    "红线检查": {"role": "旧影", "action": "红线检查"},
    "情墨":   {"role": "情墨", "action": "架构分析"}
  }
}
```

> 未匹配的指令 → `{"role": "claude", "action": "original"}`，透传给 Claude Code。

---

## 四、数据流与接口契约

### 4.1 指令生命周期（4 状态）

```
[飞书消息到达] → pending.json (status: "new")
    → Claude Code 读取并设为 "processing"
    → Claude Code 执行完成，写入 done.json
    → bridge 读取并回传飞书群，标记 "replied"
```

### 4.2 pending.json

```json
{
  "queue": [
    {
      "id": "om_x100x200x300x400x500",
      "cmd": "腰子分析600519",
      "chat_id": "oc_d79295e32b9f10312315b11bf1701be8",
      "msg_id": "om_x100x200x300x400x500",
      "status": "new",
      "ts_created": "2026-05-29T14:30:00"
    }
  ]
}
```

> `status` 转换：`new`(bridge写入) → `processing`(Claude Code读取后更新) → `done`(执行完成写入 done.json)

### 4.3 done.json

```json
{
  "results": [
    {
      "id": "om_x100x200x300x400x500",
      "status": "done",
      "reply": "600519 深度分析完成\nPDF: 报告/重点股票/600519/600519_深度分析_20260529.pdf\n自检21条: 全部通过",
      "error": null,
      "ts_done": "2026-05-29T14:35:00",
      "ts_replied": null
    }
  ]
}
```

> `status` 值：`done`(成功) / `error`(执行失败)。`ts_replied` 由 bridge 回写，标记已回传。

### 4.4 配置文件格式

**~/.feishu_bot_tmp.json** (权限 600)：
```json
{
  "app_id": "cli_aa939df4f6385cbb",
  "app_secret": "********",
  "chat_id": "oc_d79295e32b9f10312315b11bf1701be8",
  "route_table": {},
  "max_dedup": 200,
  "timeout_connect": 10,
  "timeout_read": 30
}
```

### 4.5 契约入口

| 接口 | 调用方 | 被调用方 | 协议 |
|:-----|:------|:-------|:-----|
| pending.json | feishu_bridge.py | Claude Code (cron) | 文件队列 |
| done.json | Claude Code | feishu_bridge.py | 文件队列 |
| 飞书消息 API | feishu_bridge.py | open.feishu.cn | HTTPS GET |
| 飞书回复 API | feishu_bridge.py | open.feishu.cn | HTTPS POST |

---

## 五、错误处理与日志

### 5.1 错误分级

| 错误 | 分级 | 处理 |
|:-----|:-----|:-----|
| 网络超时 (connect) | WARN | 记录日志，本次跳过，下次再试 |
| 网络超时 (read) | WARN | 记录日志，本次跳过 |
| Token 过期 (HTTP 401) | INFO | 自动刷新重试一次 |
| API 限流 (HTTP 429) | WARN | 等 5s 后重试一次，仍失败则跳过 |
| 配置文件不存在 | FATAL | 输出到 stderr，退出 |
| 配置文件权限 ≠ 600 | FATAL | 输出到 stderr，退出 |
| pending.json 写入失败 | ERROR | 记录日志，本次跳过 |
| 飞书回复失败 | WARN | 记录日志，结果保留在 done.json 下次重试 |

### 5.2 日志格式

```
路径：临时报告/对话日志/feishu_bridge_YYYY-MM-DD.log
格式：[2026-05-29 14:30:02] INFO  获取token成功 (剩余 7100s)
      [2026-05-29 14:30:03] INFO  拉取消息成功 (2条新消息)
      [2026-05-29 14:30:03] INFO  入队: om_xxx → "腰子分析600519"
      [2026-05-29 14:30:03] INFO  回传: om_yyy → 已回复
      [2026-05-29 14:30:04] WARN  网络超时: GET /messages (attempt 1/2)
      [2026-05-29 14:30:05] FATAL 配置文件权限错误: /path/to/config (期望 600, 实际 644)
```

---

## 六、安全设计

| 层面 | v1.0 | v1.1 修正 | 理由 |
|:-----|:-----|:----------|:-----|
| 凭证存储位置 | `代码文件/tools/` | **`~/.feishu_bot_tmp.json`** | 项目目录不应存 Secret，Home 目录安全 |
| 凭证权限 | chmod 600 | **启动时校验 600，非600则FATAL退出** | 强制执行，防止 git 误提交 |
| HTTP 超时 | 无 | **连接 10s / 读取 30s** | 防止脚本无限挂起 |
| 去重上限 | 200 | **200 (环形裁剪)** | 超出自动删除最旧的记录 |
| 网络层 | 零入站 | 零入站 ✅ | 不变 |
| 执行层 | 不入 shell | **bridge 只写 JSON 队列，不 eval/exec/subprocess** | 不变 |

---

## 七、Token 影响评估

> §七.2 ③ 要求

| 评估项 | 影响 | 说明 |
|:---|:---|:---|
| 新增 Python 脚本 | +280 行 | L0 级别 |
| 新增 JSON 配置 | 1 文件 (Home 目录) | 不进入 git |
| 新增 plist | 1 文件 | macOS launchd 配置 |
| 新增日志 | ~10KB/天 | 文本日志，按日期轮转 |
| API 调用 | ~1440 GET/天 | 飞书免费额度内 |
| **Claude Code Token** | **零** | bridge 纯脚本，不消耗 AI Token |
| 指令执行 Token | 按正常流程消耗 | 与直接在终端发指令一致，无增量 |

**旧影审查结论**：Token 零增量，无模板膨胀，不需运行 `check_token_efficiency.py`。闸门 1b 记录即可。

---

## 八、部署方案

### 8.1 部署步骤

```
① 飞书开放平台 → 创建应用 → 添加权限 → 发布 ✅ (已完成)
② 飞书客户端 → 建群"铁律指令" → 添加机器人 ✅ (已完成)
③ 凭证：已写入 ~/.feishu_bot_tmp.json (chmod 600) ✅ (已完成)
④ 红结实现 feishu_bridge.py (约280行)
⑤ 首次验证：python3 feishu_bridge.py --init (联通但不写队列)
⑥ 安装 launchd：
   cp com.tielv.feishu-bridge.plist ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.tielv.feishu-bridge.plist
⑦ 端到端测试：群内发 @铁律量化助手 测试 → 确认收到回复
```

### 8.2 launchd plist 模板

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.tielv.feishu-bridge</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/ccrt/ccrt/代码文件/tools/feishu_bridge.py</string>
        <string>--once</string>
    </array>
    <key>StartInterval</key>
    <integer>60</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/ccrt/ccrt/临时报告/对话日志/feishu_bridge_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/ccrt/ccrt/临时报告/对话日志/feishu_bridge_stderr.log</string>
</dict>
</plist>
```

### 8.3 卸载/回滚

```bash
launchctl unload ~/Library/LaunchAgents/com.tielv.feishu-bridge.plist
rm ~/Library/LaunchAgents/com.tielv.feishu-bridge.plist
rm /Users/ccrt/ccrt/代码文件/tools/feishu_bridge.py
rm -rf /Users/ccrt/ccrt/.claude/im_queue/
```

影响面：仅自身文件，零波及现有系统。

---

## 九、需求 → 交付核对清单

> 情墨 + 腰子共同勾签后放行（§七.2）
> v1.1 新增"部署验证"列，确保设计→实装完全一致

### 9.1 代码层

| 序号 | 需求项 | 代码对应 | 部署验证方法 | 设计☐ | 实装☐ |
|:----:|:------|:---------|:------------|:------|:------|
| 1 | 飞书 API 获取 access_token | `_get_token()` | `--init` 模式打印 token 前4位 | ☐ | ☐ |
| 2 | 拉取群消息列表 | `fetch_messages()` | `--init` 模式打印消息数量 | ☐ | ☐ |
| 3 | 消息去重 (msg_id) | `_dedup()` | 同指令发两次，仅执行一次 | ☐ | ☐ |
| 4 | 提取 @机器人 指令文本 | `filter_new()` | 发"腰子分析600519"，队列中 cmd 字段正确 | ☐ | ☐ |
| 5 | 写入指令队列 (pending.json) | `write_pending()` | 检查 pending.json 文件存在+格式 | ☐ | ☐ |
| 6 | 读取执行结果 (done.json) | `read_done()` | Claude Code 写入 done.json 后 bridge 读走 | ☐ | ☐ |
| 7 | 回复飞书群 | `reply_message()` | 群内收到机器人回复消息 | ☐ | ☐ |
| 8 | Token 自动刷新 (7200s) | `_get_token()` 过期检查 | 修改系统时间或等2小时后验证 | ☐ | ☐ |
| 9 | 配置文件路径 (Home目录) | `DEFAULT_CONFIG_PATH` | 检查代码中无 `代码文件/tools/` 硬编码路径 | ☐ | ☐ |
| 10 | 配置文件 600 权限检查 | `__init__` 权限校验 | `chmod 644 ~/.feishu_bot_tmp.json` 后运行，应 FATAL | ☐ | ☐ |
| 11 | --init 联通性验证 | `argparse --init` | 运行 `--init` 看是否输出连通成功 | ☐ | ☐ |
| 12 | --once 单次执行 | `argparse --once` | launchd 下正常单次执行不循环 | ☐ | ☐ |
| 13 | 指令路由表 (配置内) | `config["route_table"]` | 检查代码中无 ROUTE_TABLE 硬编码 | ☐ | ☐ |
| 14 | 已处理 msg_id 上限 (200) | `_dedup()` 环状裁剪 | processed_ids.json 条目数 ≤ 200 | ☐ | ☐ |
| 15 | HTTP 连接超时 (10s) | `_request()` timeout | 断网后运行，10s 内超时不卡死 | ☐ | ☐ |
| 16 | HTTP 读取超时 (30s) | `_request()` timeout | 模拟慢速网络，30s 内超时 | ☐ | ☐ |
| 17 | 日志输出到文件 | `_log()` | 检查 `临时报告/对话日志/feishu_bridge_*.log` | ☐ | ☐ |
| 18 | 零新增 Python 依赖 | `import` 语句 | `grep import feishu_bridge.py` 仅标准库 | ☐ | ☐ |
| 19 | 不执行 shell | 无 subprocess/os.system | `grep -E "subprocess|os\.system|eval|exec" feishu_bridge.py` 无结果 | ☐ | ☐ |
| 20 | 飞书 API 错误处理 (401/429/超时) | `_request()` 异常分支 | 手动修改 token 触发 401 → 检查重试日志 | ☐ | ☐ |

### 9.2 部署层

| 序号 | 部署项 | 对应文件/操作 | 验证方法 | 设计☐ | 实装☐ |
|:----:|:------|:------------|:--------|:------|:------|
| D1 | launchd plist 安装 | `~/Library/LaunchAgents/com.tielv.feishu-bridge.plist` | `launchctl list \| grep feishu` 有进程 | ☐ | ☐ |
| D2 | 每分钟触发 | plist `StartInterval=60` | 日志文件中两次执行间隔=60s±5s | ☐ | ☐ |
| D3 | 凭证文件存在 | `~/.feishu_bot_tmp.json` | `ls -la ~/.feishu_bot_tmp.json` 存在+权限600 | ☐ | ☐ |
| D4 | 凭证不进入 git | `~/.feishu_bot_tmp.json` 路径 | `git status` 无此文件 | ☐ | ☐ |
| D5 | 队列目录存在 | `.claude/im_queue/` | 首次运行后自动创建目录 | ☐ | ☐ |
| D6 | 端到端测试 | 飞书群发指令 | 发出"测试"→60s内收到回复"桥接服务运行正常" | ☐ | ☐ |
| D7 | 回滚验证 | 执行 `launchctl unload` + rm 文件 | 飞书群不再有回复，无残留进程 | ☐ | ☐ |

### 9.3 红线合规

| 序号 | 红线规则 | 合规状态 | 验证 |
|:----:|:--------|:--------|:-----|
| R1 | 不编造数据 (§1.3) | ✅ bridge 不涉及数据 | — |
| R2 | 不删除 PDF (§1.7) | ✅ bridge 不操作文件删除 | — |
| R3 | 1+2 主备架构 (§1.1) | N/A 非数据管线 | — |
| R4 | 文件版本一致 (§5.4) | ✅ 设计文档版本 v1.1 | `version_supervisor.py --cross-check` |
| R5 | Token 纪律 (§2) | ✅ 零 AI Token 消耗 | 旧影确认 |
| R6 | 不引入新数据源 | ✅ 无数据源变更 | — |
| R7 | 代码 ≤500 行 (§9.2) | ✅ ~280 行 | `wc -l feishu_bridge.py` |

---

## 十、前置条件

| 条件 | 状态 | 备注 |
|:-----|:----:|:-----|
| 飞书应用创建 + 权限 + 发布 | ✅ | 2026-05-29 完成 |
| 个人群"铁律指令"建群 + 机器人添加 | ✅ | 2026-05-29 完成 |
| App ID: `cli_aa939df4f6385cbb` | ✅ | |
| App Secret | ✅ | 已写入 `~/.feishu_bot_tmp.json` |
| 群 ID: `oc_d79295e32b9f10312315b11bf1701be8` | ✅ | |
| 设计文档自审 (情墨) | ✅ | v1.1，修复 v1.0 的 6 项缺陷 |
| 设计文档审计 (旧影) | ✅ | 本文档 |

---

## 十一、v1.0 → v1.1 修复记录

| 编号 | 缺陷 | 发现者 | 修复 |
|:----:|:-----|:------|:-----|
| F01 | 调度选型错误 (crontab → launchd) | 情墨 | macOS crontab 休眠感知不到，改用 launchd |
| F02 | 凭证文件路径不当 (项目目录 → Home) | 旧影 | Secret 不应在 git 仓库内，移至 `~/.feishu_bot_tmp.json` |
| F03 | pending.json 缺少 processing 状态 | 情墨 | 新增 3 状态流转：new → processing → done |
| F04 | 无错误处理设计 | 旧影 | 新增 §五，含 5 级错误 + 重试策略 |
| F05 | 无日志设计 | 旧影 | 新增 §5.2，日志格式+路径规范 |
| F06 | 路由表硬编码在代码中 | 情墨 | 移至配置文件 `route_table` 字段 |
| F07 | HTTP 无超时设置 | 旧影 | 新增 connect=10s / read=30s |
| F08 | 核对清单仅含"需求→代码"，缺部署验证 | 旧影 | 新增 §9.2 部署层（7项）+ §9.3 红线合规（7项） |
