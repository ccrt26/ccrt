# PDF删除防护 — 情墨架构设计

> **pipeline_stage: complete**
> **设计日期**: 2026-05-27
> **设计者**: 情墨（系统架构师）
> **任务ID**: design_pdf_deletion_protection_v1.0
> **代码等级**: L1（策略/安全防护，触及红线§1.7）

---

## 一、问题定义

### 1.1 事件

2026-05-27 19:00，`git_sweep.ps1` (engineering daily sweep) 提交了12个PDF文件的删除，涉及7只重点股票的日报/深度分析日报。

### 1.2 直接致死链

```
某流程删除PDF → git_sweep.ps1 (git add -- .) 盲扫入暂存区 →
预提交钩子无PDF删除检测 → git commit 入库 → 12个PDF永久消失
```

### 1.3 三个根因

| # | 根因 | 位置 | 性质 |
|:--|:-----|:-----|:-----|
| R1 | ConvertTo-Pdf 先删后建的破坏性覆盖 | `代码文件/监督机制/ConvertTo-Pdf.ps1:54-61` | 设计缺陷 |
| R2 | 预提交钩子无PDF删除检测 | `.claude/hooks/pre-commit-check.py` (Check A-F完备但缺G) | 防护缺口 |
| R3 | git add -- . 盲扫所有变更（含删除） | `代码文件/tools/git_autocommit.py:129`, `git_sweep.ps1:42` | 盲区 |

---

## 二、设计方案

### 2.1 三道防线（纵深防御）

```
防线一（写入层）: ConvertTo-Pdf 安全覆盖 → 单文件不会因生成失败而消失
防线二（提交层）: pre-commit Check G  → 任何commit含PDF删除即BLOCK
防线三（脚本层）: autocommit/sweep 检测 → 提交前自检，拒绝含PDF删除的暂存区
```

### 2.2 防线一：ConvertTo-Pdf 安全覆盖写入

**文件**: `代码文件/监督机制/ConvertTo-Pdf.ps1`
**等级**: L1
**改动**: 第54-61行重构

**当前逻辑**（破坏性）:
```powershell
if (Test-Path $PdfFile) {
    Remove-Item $PdfFile -Force    # 先删
}
# ... 调用Edge生成 ...
# Edge失败 → 旧文件已删，永久丢失
```

**新逻辑**（安全覆盖）:
```powershell
# 写到临时文件，成功后再替换
$tmpFile = "$PdfFile.tmp"
# ... Edge输出到$tmpFile ...
if (Edge成功 且 写入验证通过) {
    Move-Item $tmpFile $PdfFile -Force    # 原子替换
} else {
    Remove-Item $tmpFile -Force           # 清理临时文件
    # 旧PDF完好无损
}
```

**Edge headless的--print-to-pdf支持写入任何路径**，用临时文件路径即可。

### 2.3 防线二：pre-commit Check G — PDF删除阻断

**文件**: `.claude/hooks/pre-commit-check.py`
**等级**: L1
**改动**: 在Check F后新增Check G

**检查逻辑**:
```powershell
# Check G: PDF Deletion Protection (红线§1.7)
# 从暂存区检测所有被删除的.pdf文件
$DeletedPdfs = git diff --cached --diff-filter=D --name-only | Where-Object { $_ -match '\.pdf$' }
if ($DeletedPdfs.Count -gt 0) {
    foreach ($pdf in $DeletedPdfs) {
        Write-Log "BLOCK" "G BLOCK: PDF删除禁止 (红线§1.7): $pdf"
    }
    $script:HasError = $true
}
```

**豁免**：无。红线§1.7是绝对禁止，无例外。

### 2.4 防线三：git_autocommit 提交前PDF删除自检

**文件**: `代码文件/tools/git_autocommit.py`
**等级**: L1
**改动**: 在 `git add` 之后、`git commit` 之前插入PDF删除检测

**检查逻辑**:
```powershell
# PDF deletion guard (红线§1.7)
$deletedPdfs = git diff --cached --diff-filter=D --name-only 2>$null | Where-Object { $_ -match '\.pdf$' }
if ($deletedPdfs) {
    # 自动unstage被删除的PDF
    foreach ($pdf in $deletedPdfs) {
        git reset HEAD -- $pdf 2>$null
    }
    Write-AutocommitLog -Status "BLOCKED" -CommitHash "" -FileCount $deletedPdfs.Count -ErrorMsg "PDF删除拦截(红线§1.7): $($deletedPdfs -join ', ')"
    # 不阻断整个commit，只unstage PDF删除，其余文件照常提交
}
```

**设计要点**：unstage PDF删除而不是拒绝整个commit。这确保其他正常变更不受影响。

---

## 三、影响评估

### 3.1 变更范围

| 文件 | 等级 | 变更行数 | 风险 |
|:-----|:----:|:------:|:----:|
| `代码文件/监督机制/ConvertTo-Pdf.ps1` | L1 | ~20行 | 中：所有PDF生成依赖此函数 |
| `.claude/hooks/pre-commit-check.py` | L1 | ~15行 | 低：新增Check，不影响现有A-F |
| `代码文件/tools/git_autocommit.py` | L1 | ~10行 | 低：新增检测，不影响正常提交流程 |
| `代码文件/tools/git_autosweep.py` | L1 | ~10行 | 低：新增检测，`--no-verify`绕过钩子需独立防护 |

### 3.2 下游影响

- **ConvertTo-Pdf 调用者**（全部脚本）：行为不变，接口不变。仅内部实现改为安全覆盖。
- **pre-commit hook**：新增Check G，仅在检测到PDF删除时触发BLOCK。
- **git_autocommit**：仅在检测到PDF删除时触发unstage，其余行为不变。

### 3.3 不影响的模块

- 评分引擎、回测引擎、交易引擎：零相关
- 数据采集管线：零相关
- 报告生成逻辑（HTML/MD）：零相关（ConvertTo-Pdf接口不变）

---

## 四、需求→代码核对清单

> 情墨+腰子共同勾签后放行

| # | 需求 | 代码实现 | 情墨✓ | 腰子✓ |
|:--|:-----|:-----|:----:|:----:|
| 1 | ConvertTo-Pdf改为临时文件+原子替换 | `ConvertTo-Pdf.ps1` L54-61重写 | ☐ | ☐ |
| 2 | Edge输出到.tmp文件 | `--print-to-pdf=$PdfFile.tmp` | ☐ | ☐ |
| 3 | .tmp写入验证通过后Move-Item替换 | 新增Move-Item逻辑 | ☐ | ☐ |
| 4 | Edge失败时清理.tmp，保留旧PDF | try/catch + Remove-Item .tmp | ☐ | ☐ |
| 5 | pre-commit Check G检测暂存区PDF删除 | `git diff --cached --diff-filter=D` | ☐ | ☐ |
| 6 | PDF删除触发BLOCK（$HasError=true） | Write-Log "BLOCK" + HasError | ☐ | ☐ |
| 7 | git_autocommit PDF删除检测 | git diff --cached --diff-filter=D | ☐ | ☐ |
| 8 | git_autocommit unstage PDF删除（不阻断其余变更） | git reset HEAD -- $pdf | ☐ | ☐ |
| 9 | 红线§1.7引用在日志中明确标注 | "红线§1.7" 出现在BLOCK消息中 | ☐ | ☐ |

---

## 五、Rollback方案

如防线一（ConvertTo-Pdf临时文件）引入Edge兼容性问题：
1. `git revert` 回滚变更
2. 回退到当前破坏性模式（仅依赖防线二+三保护）
3. 单独调查Edge兼容性后重新上线
