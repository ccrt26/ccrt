# git_autosweep 集成 web 自动部署 — 架构设计

> pipeline_stage: complete | 设计人：情墨 | 日期：2026-05-29 | 版本：v1.0
> 等级：L0（工具层，不涉及评分/交易/风控）

---

## 一、变更摘要

`git_autosweep.py` 每小时推送报告类文件变更到 GitHub，推送成功后自动触发 `deploy_web.py`，实现报告自动上线。

## 二、改动点

| 文件 | 改动 | 行数 |
|:-----|:-----|:----:|
| `代码文件/tools/git_autosweep.py` | main() 中 push 成功后调用 deploy_web.py | +12行 |
| — | 新增 `deploy_web()` 辅助函数 | +15行 |

不新增文件，不修改接口。

## 三、实现逻辑

```python
def deploy_web():
    """Run web deployment after successful push. Returns True on success."""
    script = os.path.join(TOOLS_DIR, "deploy_web.py")
    try:
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True, text=True, timeout=120, cwd=str(ROOT)
        )
        return result.returncode == 0
    except Exception as e:
        write_log(f"WEB_DEPLOY_FAIL {e}")
        return False
```

在 main() push 成功后调用：
```python
if push_ok and auto_files:
    web_deployed = deploy_web()
```

## 四、自查清单

| CH# | 审查项 | 结果 |
|:----:|:-------|:----:|
| CH1 | 模块边界 | ✅ 单一职责 |
| CH4 | 第三方依赖 | ✅ 无新增 |
| CH5 | 循环依赖 | ✅ deploy_web.py 不回引 autosweep |
| CH6 | 单点故障 | ✅ 部署失败不影响 git 同步 |
| CH7 | 反模式 | ✅ 不触发任何反模式 |
| CH12 | 红线合规 | ✅ 不触发任何红线 |
| 行数 | ≤500 | ✅ +27行，总 330 << 500 |

## 五、Token 影响

零增量。deploy_web.py 的 subprocess 输出已被捕获，不产生额外 token。

## 六、等级：L0

红结自查 + 新安常规测试即可。
