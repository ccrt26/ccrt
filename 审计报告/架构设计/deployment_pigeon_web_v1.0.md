# 信鸽Web面板 — 灰度部署记录

> v1.0 | 2026-05-26 | 红枫

## 部署清单

| 文件 | 位置 | 大小 | 状态 |
|:-----|:-----|:----|:----:|
| `pigeon_server.py` | 代码文件/信鸽信息采集/ | 206行 | deployed |
| `pigeon_dashboard.html` | 代码文件/信鸽信息采集/ | 675行 | deployed |
| `launch_pigeon_dashboard.ps1` | 代码文件/信鸽信息采集/ | 96行 | deployed |
| `design_pigeon_web_v1.0.md` | 审计报告/架构设计/ | 设计文档 | deployed |
| `design_pigeon_web_v1.0.docx` | 审计报告/架构设计/ | 设计文档 | deployed |

## 环境依赖

| 依赖 | 要求 | 当前 |
|:-----|:-----|:----|
| Python | 3.6+ | 3.13 ✓ |
| 浏览器 | 任意现代浏览器 | 系统默认 ✓ |
| pip包 | 无 | stdlib only ✓ |
| 端口 | 8888(自动fallback) | 可用 ✓ |

## 部署验证

| 验证项 | 方法 | 结果 |
|:-------|:-----|:----:|
| Python语法 | py_compile | ✓ PASS |
| PowerShell语法 | Parser::ParseFile | ✓ PASS |
| API端点(5个) | curl测试 | ✓ 全部PASS |
| BOM编码兼容 | utf-8-sig修复 | ✓ PASS |
| HTML结构完整性 | grep检查 | ✓ PASS |
| 404错误处理 | curl测试 | ✓ PASS |
| docx同步 | md_to_docx.py | ✓ PASS |

## 回滚方案

若出现故障，执行以下任一步骤即可回滚：

1. **停止服务**：关闭PowerShell窗口或 `Stop-Process` 杀python进程
2. **删除文件**：删除3个新增文件（`pigeon_server.py`, `pigeon_dashboard.html`, `launch_pigeon_dashboard.ps1`）
3. **无残留影响**：无修改现有文件、无新增依赖、无注册表变更

## 启动指令

```powershell
cd 代码文件\信鸽信息采集
.\launch_pigeon_dashboard.ps1
# → 自动找空闲端口 → 启动服务器 → 打开浏览器
```

## 用户首次验证清单

- [ ] 双击或运行 `launch_pigeon_dashboard.ps1`
- [ ] 浏览器自动打开暗色主题面板
- [ ] 摘要卡片显示正确统计
- [ ] 事件卡片列表正常渲染
- [ ] 筛选股票下拉，事件列表联动
- [ ] 点击利好/利空/中性按钮，事件过滤正确
- [ ] 搜索框输入关键词，结果匹配
- [ ] 展开过滤漏斗统计面板
- [ ] 关闭PowerShell窗口，确认服务器停止

---

> 闸门3: 前置条件确认 — 闸门1a✓ 闸门1b✓ 闸门2✓ → PASS
