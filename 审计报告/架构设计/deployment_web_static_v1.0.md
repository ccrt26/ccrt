# Web静态托管部署记录 — v1.0

> 部署角色：红枫 | 日期：2026-05-29 | 关联设计：design_web_static_deploy_v1.0.md

---

## 一、部署状态

| 项 | 状态 |
|:---|:----:|
| Node.js (v24.16.0) | ✅ 已就绪 |
| npm / npx | ✅ 已就绪 |
| wrangler (via npx) | ✅ 可用 (v4.95.0) |
| CF_API_TOKEN | ❌ 待用户配置 |
| CF_ACCOUNT_ID | ❌ 待用户配置 |
| Cloudflare Pages 项目 | ❌ 待创建 |

---

## 二、用户待完成步骤（一次性）

### 2.1 创建 Cloudflare 账户
访问 https://dash.cloudflare.com/sign-up 注册（免费）。

### 2.2 创建 Pages 项目
```bash
npx wrangler pages project create tl-quant-reports --production-branch main
```

### 2.3 创建 API Token
1. 登录 Cloudflare Dashboard → 右上角头像 → **My Profile**
2. 左侧菜单 → **API Tokens** → **Create Token**
3. 选择 **Custom Token**，权限设置：
   - `Account` — `Cloudflare Pages` — `Edit`
   - Account Resources: 选择你的账户
4. 创建后复制 Token

### 2.4 设置环境变量
在 `~/.zshrc` 或 `~/.bashrc` 中添加：
```bash
export CF_API_TOKEN="your-token-here"
export CF_ACCOUNT_ID="your-account-id-here"
```
Account ID 在 Cloudflare Dashboard 首页右侧 Overview 中可找到。

### 2.5 验证部署
```bash
source ~/.zshrc
python3 代码文件/tools/deploy_web.py --dry-run   # 先预览
python3 代码文件/tools/deploy_web.py              # 正式发布
```

---

## 三、已就绪的自动化

deploy_web.py 脚本功能已验证（dry-run 收集90个文件成功）。用户完成 §二 配置后，立即可用：

```bash
# 手动部署
python3 代码文件/tools/deploy_web.py

# 部署指定目录
python3 代码文件/tools/deploy_web.py --source docs

# 预览将要部署的文件
python3 代码文件/tools/deploy_web.py --dry-run
```

---

## 四、回滚方案

Cloudflare Pages 每次部署自动保留历史版本：
1. 登录 Cloudflare Dashboard → Pages → tl-quant-reports
2. 在 Deployments 列表中找到上一个正常版本
3. 点击 `...` → **Rollback to this deployment**
4. 即时生效（<1分钟）

本地回退：删除 deploy_web.py 和 deploy_web_config.json 即可完全回退，不影响任何现有功能。

---

## 五、监控建议（后续）

- wrangler 部署命令本身成功/失败即可判断状态
- 可选：在日终调度中加入 `deploy_web.py`，将最新报告自动推送
- 部署 URL: `https://tl-quant-reports.pages.dev`（创建项目后生效）
