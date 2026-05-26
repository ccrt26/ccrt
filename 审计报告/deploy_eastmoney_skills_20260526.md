# 灰度部署记录 — 东方财富Skills MCP数据源[15]接入

> 部署人：红枫 | 日期：2026-05-26 | 阶段⑤ | gate: PASS

---

## 一、部署范围

| 变更类型 | 文件数 | 风险等级 |
|:--------|:-----:|:------:|
| MCP配置新增 | 1 | 极低（配置级） |
| L0代码修改 | 2 | 极低（数组追加） |
| M类知识库更新 | 3 | 极低（文档） |

## 二、部署步骤

### Step 1: 用户获取API Key
- 打开东方财富App → 搜索"skills" → 进入妙想Skills官方页 → 点击【立即领取】
- 复制API Key（格式: `mkt_xxxxx`）

### Step 2: 配置环境变量
```powershell
# 方式A：用户级环境变量（推荐）
[System.Environment]::SetEnvironmentVariable('MX_APIKEY', 'mkt_xxxxx', 'User')

# 方式B：会话级（临时测试）
$env:MX_APIKEY = 'mkt_xxxxx'
```

### Step 3: 验证MCP连通性
```powershell
# 测试API端点
$body = @{ toolQuery = "贵州茅台 最新价" } | ConvertTo-Json
$headers = @{ "apikey" = $env:MX_APIKEY; "Content-Type" = "application/json" }
Invoke-RestMethod -Uri "https://mkapi2.dfcfs.com/finskillshub/api/claw/query" `
    -Method POST -Headers $headers -Body $body | ConvertTo-Json
```

### Step 4: 重启Claude Code
- 关闭并重新打开Claude Code会话
- MCP配置自动加载
- 发送测试消息验证Skills工具可用

### Step 5: 灰度验证（2周）
- 观察Skills作为备源是否被实际触发
- 验证返回数据字段与schema一致
- 监控日限额使用情况

---

## 三、回滚方案

| 回滚级别 | 触发条件 | 操作 | 影响 |
|:-------:|:--------|:----|:-----|
| L1 软回滚 | Skills调用频繁失败 | 从core.ps1 SourcePriority中移除"Skills"条目 | 降级路径回到接入前状态 |
| L2 硬回滚 | API Key泄露/MCP异常 | 删除`.claude/mcp_servers/eastmoney_skills.json` + 撤销core.ps1修改 | 完全恢复接入前状态 |
| L3 紧急回滚 | 数据错误影响分析结论 | `git revert` 本次所有提交 | 零残留 |

### 回滚验证
```
回滚后确认：
1. core.ps1 SourcePriority 不含"Skills" → 备源链路不变
2. 玉夜巡检无[15]报错
3. 评分/选股/报告输出与接入前完全一致
```

---

## 四、监控指标

| 指标 | 阈值 | 告警 |
|:----|:---:|:----:|
| Skills日调用量 | ≥40次/天 | WARN |
| Skills日调用量 | ≥50次/天 | 熔断，降级至缓存[C] |
| API响应时间 | >5秒 | WARN |
| API错误率 | >20% | 临时禁用Skills备源 |
| 返回字段缺失率 | >10% | WARN |

---

## 五、部署确认

| 步骤 | 状态 |
|:----|:---:|
| Step 1 API Key获取 | ⚠️ 待用户执行 |
| Step 2 环境变量配置 | ⚠️ 待用户执行 |
| Step 3 MCP连通性验证 | ⚠️ 待用户执行 |
| Step 4 Claude Code重启 | ⚠️ 待用户执行 |
| Step 5 灰度观察2周 | ⏳ 待启动 |

**gate: PASS** — 部署方案就绪，回滚路径明确。用户侧执行Step 1-4后即完成灰度上线。
