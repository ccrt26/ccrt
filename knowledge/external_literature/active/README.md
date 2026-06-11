# 生效知识目录

## 用途

此目录存放已通过全部流程确认生效的外部文献知识。

## 子目录

| 子目录 | 用途 |
|:-------|:-----|
| `parameters/` | 已验证的参数规则 |
| `counterexamples/` | 已验证的反例规则 |
| `role_knowledge/` | 已验证的角色级核心知识 |

## 进入条件

进入 ACTIVE 前必须同时满足：

1. ✅ `finance_aligned = true`（腰子统一口径）
2. ✅ `validated = true`（项目验证完成）
3. ✅ `confirmed_roles` 非空（角色确认）
4. ✅ 适用条件已记载
5. ✅ 不适用条件已记载
6. ✅ `valid_until` 存在且未过期
7. ✅ `review_date` 存在
8. ✅ lint 检查无 ERROR 违规
9. ✅ transition → ACTIVE 检查通过
10. ✅ G5 旧影复查通过
11. ✅ G6 腰子/用户放行

## 使用规则

- active 内容是角色启动上下文唯一允许读取的知识
- active_index.json 控制哪些内容被加载
- 过期内容自动从 active_index.json 移除
- 进入 DEPRECATED 后从 active 目录移至 deprecated 目录
