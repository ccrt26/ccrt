<#
.SYNOPSIS
    铁律量化 · 白皮书执行监督引擎
.DESCRIPTION
    监督 AI 在执行各分析任务时遵循对应的白皮书规范。
    在 PreToolUse hook 中调用，根据命令模式自动匹配对应白皮书。
.NOTES
    版本: v1.0
    用法:
        .\task_supervisor.ps1 -Command "python scoring_engine_v2.py ..."
        .\task_supervisor.ps1 -List
        .\task_supervisor.ps1 -Quick
    退出码: 0 = 正常
#>
param(
    [string]$Command = "",
    [switch]$List,
    [switch]$Quick
)
. "$PSScriptRoot/../lib/init_encoding.ps1"

# ═════ 任务→白皮书映射表 ══════════════════════════════════════════
# 格式: Pattern(正则), TaskName, Whitepaper, Path, KeyReqs(数组)
$TASK_MAP = @()

$TASK_MAP += @{
    Pattern  = 'scoring_engine'
    Task     = '评分/选股'
    WP       = '每日荐股分析逻辑白皮书 v2.9'
    WPath    = '每日荐股\分析逻辑\每日荐股分析逻辑白皮书_v2.9.md'
    Reqs     = @(
        '一票否决条件: 硬止损-7%/C8拦截/A档强制席位',
        '评分维度: 时间(相位折扣三面扩展)+盈利+技术+资金',
        '数据源: 腾讯[1]/新浪[2]/东方财富[3][7][9]',
        'API间隔>=300ms, 每10次额外休息5s'
    )
}

$TASK_MAP += @{
    Pattern  = 'gen_daily_html'
    Task     = '每日荐股报告生成'
    WP       = '每日荐股分析逻辑白皮书 v2.9'
    WPath    = '每日荐股\分析逻辑\每日荐股分析逻辑白皮书_v2.9.md'
    Reqs     = @(
        '报告格式: Stocks + SectorData + SectorFundFlow + SectorKLine',
        '必须包含免责声明',
        '所有数字标注[1][3][7]等来源编号'
    )
}

$TASK_MAP += @{
    Pattern  = 'run_daily_eval|gen_eval_doc'
    Task     = '每日荐股后评估'
    WP       = '次日后评估白皮书 v1.6'
    WPath    = '每日荐股\事后评估\次日后评估白皮书_v1.6.md'
    Reqs     = @(
        '数据采集: 开盘/收盘/最高最低均标注来源[1][7]',
        '模拟交易: 开盘买入/收盘卖出/ATR止损/日内止损',
        '归因分析: 逐维度预期验证 vs 实际表现',
        '误判分类: 14种子类型标记与统计'
    )
}

$TASK_MAP += @{
    Pattern  = 'keystock.*gen_doc'
    Task     = '重点股票深度分析'
    WP       = '重点股票跟踪分析逻辑白皮书 v3.3'
    WPath    = '重点股票\分析逻辑\重点股票跟踪分析逻辑白皮书_v3.3.md'
    Reqs     = @(
        '多周期融合: 短期/中期/长期三维预测',
        '证据加权: 多个独立维度同向方可形成结论',
        '操作建议: 六层价格分级+三周期操作情景计划',
        '持续跟踪: 建立档案持续跟踪关键信号变化'
    )
}

$TASK_MAP += @{
    Pattern  = 'keystock.*eval'
    Task     = '重点股票后评估'
    WP       = '重点股票次日后评估白皮书 v1.4'
    WPath    = '重点股票\次日评估\重点股票次日后评估白皮书_v1.4.md'
    Reqs     = @(
        '评估维度: 预判准确率/方向正确率/操作建议可行性',
        '评分标准: 严格对照白皮书定义的评估指标',
        '数据源标注: 所有对比数据标注[1][2][3][5]等来源'
    )
}

# ═════ 匹配逻辑 ═════════════════════════════════════════════════
function Invoke-Supervisor {
    param([string]$Cmd)

    $matched = $false
    foreach ($entry in $TASK_MAP) {
        if ($Cmd -match $entry.Pattern) {
            $matched = $true
            $sep = '=' * 50
            $sep2 = '-' * 50
            Write-Host "`n$sep" -ForegroundColor Magenta
            Write-Host "  [监督] 任务类型 : $($entry.Task)" -ForegroundColor Cyan
            Write-Host "  [监督] 对应白皮书 : $($entry.WP)" -ForegroundColor Green
            Write-Host "  [监督] 文档路径  : $($entry.WPath)" -ForegroundColor White
            Write-Host "$sep2" -ForegroundColor Magenta
            Write-Host "  关键要求:" -ForegroundColor Yellow
            foreach ($req in $entry.Reqs) {
                Write-Host "    * $req" -ForegroundColor Yellow
            }
            Write-Host "$sep`n" -ForegroundColor Magenta
            break
        }
    }

    if (-not $matched -and -not $Quick -and $Cmd -ne "") {
        Write-Host "  [监督] 未匹配到已知任务模式: $Cmd" -ForegroundColor DarkGray
    }

    return $matched
}

# ═════ 列出全部映射 ══════════════════════════════════════════════
function Show-Map {
    Write-Host "`n白皮书执行监督 - 任务映射表" -ForegroundColor Cyan
    Write-Host "=" * 50 -ForegroundColor Cyan
    Write-Host ""

    $groups = $TASK_MAP | Group-Object WP
    foreach ($g in $groups) {
        Write-Host ">> $($g.Name)" -ForegroundColor Green
        foreach ($entry in $g.Group) {
            Write-Host "    任务: $($entry.Task)" -ForegroundColor White
            Write-Host "    路径: $($entry.WPath)" -ForegroundColor DarkGray
        }
        Write-Host ""
    }
}

# ═════════════════════════════════════════════════════════════════
# 入口
# ═════════════════════════════════════════════════════════════════
if ($List) {
    Show-Map
} elseif ($Quick) {
    # Quiet mode - just check if any tasks would match
    exit 0
} elseif ($Command -ne "") {
    $null = Invoke-Supervisor -Cmd $Command
    exit 0
} else {
    Write-Host "[监督] 白皮书执行监督引擎 v1.0" -ForegroundColor Cyan
    Write-Host "[监督] 已注册 $($TASK_MAP.Count) 个任务模式" -ForegroundColor Green
    Write-Host "[监督] 用法: .\task_supervisor.ps1 -Command '...'" -ForegroundColor White
    Write-Host "[监督]        .\task_supervisor.ps1 -List" -ForegroundColor White
    exit 0
}
