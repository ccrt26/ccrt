# ROLE_砺石标准入口补齐_G0-G6记录_v0.1

> 日期：2026-06-12
> 流程：F-FIX
> 主题：砺石完整角色定义、召唤命令与名册入口一致性修复
> 执行者：Codex（执行模型，不代表项目角色签核）

---

## 1. G0 需求识别

用户指出：

1. 砺石完整角色定义落在 `统一解读/角色解释包/砺石_方法审查包.md`，与其他角色 `.claude/agents/xxxxx.md` 路径不一致。
2. 砺石召唤命令不统一。
3. 若由 Codex 修复，必须按标准流程执行。

结论：进入 F-FIX，修复范围限定为角色入口、召唤命令、协作口径与团队名册同步。

---

## 2. G1 角色与业务边界

砺石定位：

- 金融线按需唤醒角色
- 方法校准官 / 反证审查官
- 为腰子提供推理链质量参考
- 不输出投资方向
- 不替代腰子、旧影、青山、玉夜、流金

边界确认：

- 不新增 U-11
- 不把砺石加入 F-ANALYSIS 必唤醒列表
- 不把 LISHI-SEED 规则升级为 L2 或 active rule
- 不改变日报、深度分析、每日荐股、模拟交易的正式流程结构

---

## 3. G2 技术方案

新增标准入口：

1. `.claude/agents/方法校准官-砺石.md`
2. `.claude/commands/砺石.md`

同步引用：

1. `项目成员/团队名册_v1.9.md`
2. `项目成员/团队名册_v1.9.xlsx`
3. `项目成员/团队名册_v1.9.docx`
4. `.claude/commands/腰子.md`
5. `.claude/agents/金融专家-腰子.md`
6. `.claude/agents/金融团队-协作协议.md`
7. `.claude/agents/项目总监-阿黑.md`
8. `00_项目地基/05_流程与角色/role_matrix.json`

保留原有方法审查包：

- `统一解读/角色解释包/砺石_方法审查包.md`

---

## 4. G3 实施结果

已完成：

- 新增砺石完整角色定义，统一到 `.claude/agents/方法校准官-砺石.md`
- 新增召唤命令 `.claude/commands/砺石.md`
- 名册三格式同步为 `/砺石（按需）`
- 腰子命令增加砺石触发条件、采纳/驳回记录要求
- 腰子角色定义增加砺石为按需方法校准支撑
- 金融团队协作协议升级到 v1.3，补齐砺石输出标准与召唤示例
- 阿黑角色定义补齐金融线支撑角色口径
- `role_matrix.json` 保持砺石不进入 F-ANALYSIS 必唤醒数组，仅在 G1 timing 标注按需

---

## 5. G4 自检

执行命令：

```bash
test -f .claude/agents/方法校准官-砺石.md
test -f .claude/commands/砺石.md
python3 -m json.tool 00_项目地基/05_流程与角色/role_matrix.json
rg -n "<旧召唤口径与旧人数口径关键词>" 项目成员/团队名册_v1.9.md .claude/agents .claude/commands 00_项目地基/05_流程与角色/role_matrix.json
git diff --check -- .claude/agents/方法校准官-砺石.md .claude/commands/砺石.md .claude/commands/腰子.md .claude/agents/金融专家-腰子.md .claude/agents/金融团队-协作协议.md .claude/agents/项目总监-阿黑.md 项目成员/团队名册_v1.9.md 00_项目地基/05_流程与角色/role_matrix.json
```

自检结果：

- 砺石角色定义文件存在：PASS
- 砺石召唤命令文件存在：PASS
- `role_matrix.json` 合法：PASS
- Markdown / agent / command 旧口径残留：PASS
- xlsx / docx 中 `/砺石（按需）`、角色定义路径、召唤命令路径存在：PASS
- xlsx / docx 旧口径残留为 0：PASS
- `git diff --check`：PASS

---

## 6. G5 / G6 状态

Formal pipeline 未通过；RUN 仍停在当前阶段。

本记录基于用户明确授权与 F-FIX 接力流程例外继续，不等同于 formal pipeline PASS。

不得伪造 actor/HMAC sign-off，不得代签旧影、腰子、阿黑或任何项目角色结论，不得自动推进后续阶段。

Codex 自检结论：建议进入人工复查 / 旧影复查。

---

## 7. 当前可用性结论

砺石已经具备正常按需投入使用的标准入口：

- 完整人设：`.claude/agents/方法校准官-砺石.md`
- 召唤命令：`.claude/commands/砺石.md`
- 方法审查包：`统一解读/角色解释包/砺石_方法审查包.md`
- 知识库入口：`00_项目地基/07_知识进化/knowledge/roles/lishi/`

使用方式：由腰子或阿黑在触发条件满足时按需召唤 `/砺石`，输出 `method_review` / `lishi_method_review`，供腰子整合裁决。
