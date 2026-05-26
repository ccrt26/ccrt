# L1 — 五层噪音过滤引擎
# 设计文档: 审计报告/架构设计/design_pigeon_info_collection_v1.0.md §三.2.3
# 闸门1a优化建议: S1(首次覆盖保留) + S2(去重阈值70%)

function Invoke-PigeonFilter {
    <#
    .SYNOPSIS
      对原始消息执行五层过滤漏斗，每只股票最多保留5条高价值信号
    .PARAMETER RawMessages
      原始消息数组，每条包含: title, source, publish_time, sec_code, sec_name
    .PARAMETER StockCode
      当前处理的股票代码
    .PARAMETER StockName
      当前处理的股票名称
    .PARAMETER ExistingEvents
      近3日已入库事件（用于去重）
    #>
    param(
        [Parameter(Mandatory=$false)][array]$RawMessages,
        [Parameter(Mandatory=$true)][string]$StockCode,
        [Parameter(Mandatory=$true)][string]$StockName,
        [array]$ExistingEvents = @()
    )

    $config = Get-PigeonConfig
    $stats = @{ L1_in=0; L1_out=0; L2_in=0; L2_out=0; L3_in=0; L3_out=0; L4_in=0; L4_out=0 }

    if ($RawMessages.Count -eq 0) {
        Write-Host "[filter] $StockCode : 0 raw messages, skipping all layers"
        return @{ events = @(); stats = $stats }
    }

    $stats.L1_in = $RawMessages.Count

    # ============================================================
    # L1: 黑名单关键词 + 黑名单域名 → 直接丢弃
    # ============================================================
    $afterL1 = @()
    foreach ($msg in $RawMessages) {
        $title = $msg.title
        $shouldDrop = $false

        # L1a: 关键词匹配
        foreach ($kw in $config.blacklist_keywords) {
            if ($title -match [regex]::Escape($kw)) {
                $shouldDrop = $true
                break
            }
        }

        # L1b: 域名匹配
        if (-not $shouldDrop -and $msg.source) {
            foreach ($domain in $config.blacklist_domains) {
                if ($msg.source -match [regex]::Escape($domain)) {
                    $shouldDrop = $true
                    break
                }
            }
        }

        if (-not $shouldDrop) {
            $afterL1 += $msg
        }
    }
    $stats.L1_out = $afterL1.Count
    $stats.L2_in = $afterL1.Count

    # ============================================================
    # L2: 腰子五问法 — Q1-Q5至少YES一个
    # ============================================================
    $afterL2 = @()
    foreach ($msg in $afterL1) {
        $title = $msg.title
        $hasQuantifiable = $false

        if ($title -match $config.q1_q5_rules.Q1_financial)   { $hasQuantifiable = $true }
        if ($title -match $config.q1_q5_rules.Q2_ownership)   { $hasQuantifiable = $true }
        if ($title -match $config.q1_q5_rules.Q3_regulatory)  { $hasQuantifiable = $true }
        if ($title -match $config.q1_q5_rules.Q4_capacity)    { $hasQuantifiable = $true }
        if ($title -match $config.q1_q5_rules.Q5_competitive) { $hasQuantifiable = $true }

        if ($hasQuantifiable) {
            $msg | Add-Member -NotePropertyName "quantifiable" -NotePropertyValue $true -Force
            $afterL2 += $msg
        }
    }
    $stats.L2_out = $afterL2.Count
    $stats.L3_in = $afterL2.Count

    # ============================================================
    # L3: 山猫增量性检查 — 去重 + 重复口径过滤 + 无效研报丢弃
    # 闸门1a S1: 首次覆盖研报保留
    # 闸门1a S2: 去重相似度阈值70%
    # ============================================================
    $afterL3 = @()
    foreach ($msg in $afterL2) {
        $isDuplicate = $false

        # L3a: 与近3日已入库事件去重 (简单标题相似度: 共同词数/总词数)
        foreach ($existing in $ExistingEvents) {
            $sim = Get-TitleSimilarity -Title1 $msg.title -Title2 $existing.title
            if ($sim -gt $config.dedup_similarity_threshold) {
                $isDuplicate = $true
                break
            }
        }

        # L3b: 研报类 — 无评级调整+无盈利预测修正 → 丢弃
        # S1: 首次覆盖研报即使无调整也保留
        if (-not $isDuplicate -and ($msg.title -match "研报|研究报告|深度报告")) {
            $isFirstCoverage = $msg.title -match "首次覆盖|首覆|首次|新覆盖"
            $hasRatingChange = $msg.title -match "上调|下调|调高|调低|维持.*评级"
            $hasEstimateChange = $msg.title -match "盈利预测|EPS预测|业绩预测"

            if (-not $isFirstCoverage -and -not $hasRatingChange -and -not $hasEstimateChange) {
                $isDuplicate = $true
            }
        }

        if (-not $isDuplicate) {
            $afterL3 += $msg
        }
    }
    $stats.L3_out = $afterL3.Count
    $stats.L4_in = $afterL3.Count

    # ============================================================
    # L4: 青山三层标签分类 + 流金上限控制
    # ============================================================
    $taggedEvents = @()
    foreach ($msg in $afterL3) {
        $tag = Get-EventTags -Message $msg -Config $config
        $event = [PSCustomObject]@{
            event_id     = ""
            code         = $StockCode
            name         = $StockName
            category     = $tag.Category
            subtype      = $tag.Subtype
            title        = $msg.title
            source       = $msg.source
            source_type  = if ($msg.source_type) { $msg.source_type } else { "primary" }
            reliability  = if ($msg.source_type -eq "primary") { "verified" } else { "single_source" }
            quantifiable = $msg.quantifiable
            direction    = $tag.Direction
            impact_score = $tag.ImpactScore
            probability  = $tag.Probability
            structured_fields = $tag.StructuredFields
            raw_summary  = if ($msg.title.Length -gt 200) { $msg.title.Substring(0, 200) } else { $msg.title }
            publish_time = $msg.publish_time
            pdf_url         = if ($msg.pdf_url) { $msg.pdf_url } else { $null }
            content         = if ($msg.content) { $msg.content } else { "" }
            announcement_id = if ($msg.announcement_id) { $msg.announcement_id } else { $null }
            cninfo_url      = if ($msg.cninfo_url) { $msg.cninfo_url } else { $null }
            keywords        = $tag.Keywords
            is_p0        = $tag.IsP0
        }
        $taggedEvents += $event
    }

    # L4a: 按 impact_score 排序，取前N条
    $maxPerStock = $config.max_events_per_stock
    $p0Events = $taggedEvents | Where-Object { $_.is_p0 }
    $normalEvents = $taggedEvents | Where-Object { -not $_.is_p0 } | Sort-Object -Property impact_score -Descending

    # P0事件不受上限限制，强制入库
    $finalEvents = @($p0Events)
    $remaining = $maxPerStock - $p0Events.Count
    if ($remaining -gt 0) {
        $finalEvents += $normalEvents | Select-Object -First $remaining
    }

    # L4b: 分配唯一event_id
    $fetchDate = (Get-Date).ToString("yyyyMMdd")
    for ($i = 0; $i -lt $finalEvents.Count; $i++) {
        $seq = ($i + 1).ToString("000")
        $finalEvents[$i].event_id = "PIGEON_${fetchDate}_${StockCode}_${seq}"
    }

    $stats.L4_out = $finalEvents.Count

    Write-Host "[filter] $StockCode : L1 $($stats.L1_in)→$($stats.L1_out) | L2 $($stats.L2_in)→$($stats.L2_out) | L3 $($stats.L3_in)→$($stats.L3_out) | L4 $($stats.L4_in)→$($stats.L4_out)"

    return @{
        events = $finalEvents
        stats  = $stats
    }
}

# ============================================================
# 辅助函数
# ============================================================

function Get-EventTags {
    <#
    .SYNOPSIS
      对单条消息执行三层标签分类 + impact_score计算
      闸门1a S4: impact_score = category_weight × probability × freshness
    #>
    param(
        [Parameter(Mandatory=$true)]$Message,
        [Parameter(Mandatory=$true)]$Config
    )

    $title = $Message.title

    # Layer1+Layer2: 事件大类+子类
    $category = "经营事件"
    $subtype = "其他"
    $catWeight = $Config.impact_score_weights."经营事件"

    if ($title -match "业绩|预告|快报|年报|季报|中报|净利润|营收增长|EPS|ROE|扣非") {
        $category = "业绩"
        $subtype = if ($title -match "预告|预增|预减|预亏") { "业绩预告" }
                   elseif ($title -match "快报") { "业绩快报" }
                   else { "正式财报" }
        $catWeight = $Config.impact_score_weights."业绩"
    }
    elseif ($title -match "收购|并购|重组|合并|借壳|注入|出售.*资产|购买.*(股权|资产)|发行.*股份|注册批复|核准.*发行") {
        $category = "并购重组"
        $subtype = if ($title -match "注册批复|核准|通过") { "注册批复" }
                   elseif ($title -match "预案|草案|筹划") { "重组预案" }
                   else { "并购进展" }
        $catWeight = $Config.impact_score_weights."并购重组"
    }
    elseif ($title -match "增持|减持|回购|质押|解禁|股权激励|定向增发|控制权.*变更|要约") {
        $category = "股东行为"
        $subtype = if ($title -match "增持") { "增持" }
                   elseif ($title -match "减持") { "减持" }
                   elseif ($title -match "回购") { "回购" }
                   elseif ($title -match "质押") { "质押" }
                   elseif ($title -match "解禁") { "解禁" }
                   else { "其他股东行为" }
        $catWeight = $Config.impact_score_weights."股东行为"
    }
    elseif ($title -match "立案|调查|处罚|警示函|监管函|问询函|ST|\*ST|退市|暂停上市|责令|罚款|违法") {
        $category = "监管合规"
        $subtype = if ($title -match "立案|调查") { "立案调查" }
                   elseif ($title -match "问询函") { "问询函" }
                   elseif ($title -match "处罚|罚款|警示函") { "处罚决定" }
                   elseif ($title -match "ST|\*ST|退市|暂停上市") { "ST/退市风险" }
                   else { "其他监管" }
        $catWeight = $Config.impact_score_weights."监管合规"
    }
    elseif ($title -match "补贴|政策|关税|准入|标准|扶持|限制|淘汰|产能.*调控|环保.*限产|碳达峰|碳中和|新能源.*政策|算力.*政策|机器人.*政策") {
        $category = "行业政策"
        $subtype = if ($title -match "补贴|扶持") { "扶持政策" }
                   elseif ($title -match "限制|淘汰|调控") { "限制政策" }
                   else { "政策动态" }
        $catWeight = $Config.impact_score_weights."行业政策"
    }
    elseif ($title -match "中标|合同|订单|投产|量产|定点|获批|新产品|新线|产能|供货|客户") {
        $category = "经营事件"
        $subtype = if ($title -match "中标|合同|订单") { "重大合同" }
                   elseif ($title -match "投产|量产|产能|新线") { "产能投产" }
                   elseif ($title -match "定点|获批|新产品") { "产品/客户" }
                   else { "其他经营" }
        $catWeight = $Config.impact_score_weights."经营事件"
    }

    # Layer3: 方向 + 确定性 + 时效性
    $direction = 0
    if ($title -match "增持|回购|预增|增长|超预期|获批|中标|突破|利好|注册批复|通过|核准|上调|实施") { $direction = 1 }
    elseif ($title -match "减持|预亏|预减|下降|不及预期|立案|处罚|问询|警示|退市|ST|\*ST|调查|失败|亏损|暴跌") { $direction = -1 }

    $probability = 1.0
    if ($title -match "传闻|消息|据悉|或|或将|可能|拟|计划|筹划") { $probability = 0.5 }
    elseif ($title -match "预告|预计|预测") { $probability = 0.7 }

    # freshness: 基于发布日期
    $freshness = $Config.freshness_weights."today"
    if ($Message.publish_time) {
        try {
            $pubDate = [datetime]::Parse($Message.publish_time)
            $daysAgo = ([datetime]::Now - $pubDate).Days
            if ($daysAgo -le 0) { $freshness = $Config.freshness_weights."today" }
            elseif ($daysAgo -le 1) { $freshness = $Config.freshness_weights."yesterday" }
            elseif ($daysAgo -le 3) { $freshness = $Config.freshness_weights."3days" }
            else { $freshness = $Config.freshness_weights."week" }
        } catch { }
    }

    # S4: impact_score = category_weight × probability × freshness, capped at 10
    $impactScore = [Math]::Round($catWeight * $probability * $freshness, 1)
    if ($impactScore -gt 10) { $impactScore = 10.0 }

    # P0判定
    $isP0 = $false
    foreach ($p0kw in $Config.p0_keywords) {
        if ($title -match [regex]::Escape($p0kw)) {
            $isP0 = $true
            break
        }
    }

    # 提取匹配的关键词
    $matchedKeywords = @()
    foreach ($kw in ($Config.q1_q5_rules.PSObject.Properties | Where-Object { $title -match $_.Value })) {
        $matchedKeywords += $kw.Name
    }

    return [PSCustomObject]@{
        Category         = $category
        Subtype          = $subtype
        Direction        = $direction
        ImpactScore      = $impactScore
        Probability      = $probability
        Keywords         = $matchedKeywords -join ","
        IsP0             = $isP0
        StructuredFields = @{
            event_type = $subtype
            status     = if ($title -match "完成|通过|批复|实施|投产|量产") { "confirmed" }
                         elseif ($title -match "筹划|拟|计划|预案") { "planned" }
                         else { "announced" }
        }
    }
}

function Get-TitleSimilarity {
    <#
    .SYNOPSIS
      计算两个标题的简单Jaccard相似度（共同词/总词数）
      闸门1a S2: 阈值70%
    #>
    param([string]$Title1, [string]$Title2)

    if ([string]::IsNullOrEmpty($Title1) -or [string]::IsNullOrEmpty($Title2)) {
        return 0.0
    }

    # 分词: 按常见分隔符+中文字符边界
    $words1 = ($Title1 -replace '[^\p{L}\p{N}]', ' ' -split '\s+').Where({ $_.Length -ge 2 }) | Select-Object -Unique
    $words2 = ($Title2 -replace '[^\p{L}\p{N}]', ' ' -split '\s+').Where({ $_.Length -ge 2 }) | Select-Object -Unique

    if ($words1.Count -eq 0 -or $words2.Count -eq 0) {
        return 0.0
    }

    $common = 0
    foreach ($w in $words1) {
        if ($w -in $words2) { $common++ }
    }

    $union = ($words1 + $words2 | Select-Object -Unique).Count
    if ($union -eq 0) { return 0.0 }
    return [Math]::Round($common / $union, 2)
}
