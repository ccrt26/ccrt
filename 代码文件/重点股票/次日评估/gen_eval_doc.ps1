# 生成：重点股票次日后评估白皮书 v1.3 DOCX
# 遵循白皮书：重点股票次日后评估白皮书 v1.4（§评估维度、§评分标准、§数据源标注）
# 注意：此脚本为遗留硬编码版本，后续修改请使用 build_docx.ps1 从 .md 生成
# 核心：复盘的是"分析逻辑本身"，不是"股票涨跌对错"
[System.Reflection.Assembly]::LoadWithPartialName("System.IO.Compression.FileSystem") | Out-Null
[System.Reflection.Assembly]::LoadWithPartialName("System.IO.Compression") | Out-Null

$mdPath = "Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))\重点股票\次日评估\重点股票次日后评估白皮书_v1.3.md"
$docxPath = "Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))\重点股票\次日评估\重点股票次日后评估白皮书_v1.3.docx"
$timestamp = "2026-05-22"

# --- XML 模板 ---
$contentTypeXml = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
  <Override PartName="/word/fontTable.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.fontTable+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
'@

$relsXml = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
'@

$wordRelsXml = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/fontTable" Target="fontTable.xml"/>
</Relationships>
'@

$settingsXml = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:zoom w:percent="100"/>
  <w:defaultTabStop w:val="720"/>
</w:settings>
'@

$fontTableXml = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:fonts xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:font w:name="Microsoft YaHei"><w:altName w:val="微软雅黑"/></w:font>
  <w:font w:name="Calibri"><w:altName w:val="Calibri"/></w:font>
</w:fonts>
'@

$coreXml = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
  xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/">
  <dc:title>重点股票次日后评估白皮书 v1.3</dc:title>
  <dc:subject>股票分析逻辑后评估</dc:subject>
  <dc:creator>Claude</dc:creator>
  <dcterms:created>$timestamp</dcterms:created>
</cp:coreProperties>
"@

$appXml = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">
  <Application>Claude Code</Application>
  <DocSecurity>0</DocSecurity>
  <Lines>1</Lines>
  <Paragraphs>1</Paragraphs>
  <Template>Normal</Template>
  <TotalTime>0</TotalTime>
  <Scale>Crop</Scale>
</Properties>
"@

# --- 样式 XML ---
$stylesXml = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <w:docDefaults>
    <w:rPrDefault>
      <w:rPr><w:rFonts w:ascii="Microsoft YaHei" w:eastAsia="Microsoft YaHei" w:hAnsi="Microsoft YaHei"/><w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr>
    </w:rPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:styleId="a"><w:name w:val="Normal"/><w:pPr><w:spacing w:line="360" w:after="120"/></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="1"><w:name w:val="heading 1"/><w:basedOn w:val="a"/><w:pPr><w:spacing w:before="360" w:after="200"/></w:pPr><w:rPr><w:b/><w:sz w:val="36"/><w:szCs w:val="36"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="2"><w:name w:val="heading 2"/><w:basedOn w:val="a"/><w:pPr><w:spacing w:before="240" w:after="120"/></w:pPr><w:rPr><w:b/><w:sz w:val="28"/><w:szCs w:val="28"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="3"><w:name w:val="heading 3"/><w:basedOn w:val="a"/><w:pPr><w:spacing w:before="200" w:after="100"/></w:pPr><w:rPr><w:b/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="4"><w:name w:val="heading 4"/><w:basedOn w:val="a"/><w:pPr><w:spacing w:before="160" w:after="80"/></w:pPr><w:rPr><w:b/><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr></w:style>
</w:styles>
'@

# --- Document XML builder ---
$sb = [System.Text.StringBuilder]::new()
[void]$sb.Append('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>')
[void]$sb.Append('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">')
[void]$sb.Append('<w:body>')

function Add-Para {
    param($sb, $text, [string]$style="a", [string]$bold=$null, [string]$color=$null, [string]$sz=$null, [string]$justification=$null)
    [void]$sb.Append('<w:p><w:pPr>')
    if ($style -ne "a") { [void]$sb.Append("<w:pStyle w:val=`"$style`"/>") }
    if ($justification) { [void]$sb.Append("<w:jc w:val=`"$justification`"/>") }
    [void]$sb.Append('</w:pPr><w:r><w:rPr>')
    if ($bold) { [void]$sb.Append("<w:b/>") }
    if ($color) { [void]$sb.Append("<w:color w:val=`"$color`"/>") }
    if ($sz) { [void]$sb.Append("<w:sz w:val=`"$sz`"/><w:szCs w:val=`"$sz`"/>") }
    [void]$sb.Append('</w:rPr><w:t xml:space="preserve">' + [System.Security.SecurityElement]::Escape($text) + '</w:t></w:r></w:p>')
}

function Add-TableRow {
    param($sb, $cells, [string]$shading=$null, [string]$bold=$null, [string]$color=$null, [string]$sz=$null)
    [void]$sb.Append('<w:tr>')
    foreach ($cell in $cells) {
        [void]$sb.Append('<w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/><w:shd w:val="clear" w:color="auto" w:fill="')
        if ($shading) { [void]$sb.Append($shading) } else { [void]$sb.Append("FFFFFF") }
        [void]$sb.Append('"/></w:tcPr><w:p><w:r><w:rPr>')
        if ($bold) { [void]$sb.Append("<w:b/>") }
        if ($color) { [void]$sb.Append("<w:color w:val=`"$color`"/>") }
        if ($sz) { [void]$sb.Append("<w:sz w:val=`"$sz`"/><w:szCs w:val=`"$sz`"/>") }
        [void]$sb.Append('</w:rPr><w:t xml:space="preserve">' + [System.Security.SecurityElement]::Escape($cell) + '</w:t></w:r></w:p></w:tc>')
    }
    [void]$sb.Append('</w:tr>')
}

function Add-Table {
    param($sb, $headers, $rows, $headerBg)
    [void]$sb.Append('<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="dxa"/><w:tblBorders><w:top w:val="single" w:sz="4" w:color="CCCCCC"/><w:bottom w:val="single" w:sz="4" w:color="CCCCCC"/><w:insideH w:val="single" w:sz="4" w:color="CCCCCC"/></w:tblBorders></w:tblPr>')
    Add-TableRow $sb $headers $headerBg "FFFFFF" "21"
    foreach ($r in $rows) { Add-TableRow $sb $r }
    [void]$sb.Append('</w:tbl>')
}

# ===== Build Document Content =====

# 标题页
Add-Para $sb "重点股票次日后评估白皮书" "1" $true "#1a1a2e" "44"
Add-Para $sb "版本 v1.3 | 2026-05-22" "a" $null "666666" "21"
Add-Para $sb "核心原则：复盘的是"分析逻辑本身"，不是"股票涨跌对错"" "a" $true "c0392b" "21"

# 分隔线
[void]$sb.Append('<w:p><w:pPr><w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1" w:color="CCCCCC"/></w:pBdr></w:pPr></w:p>')

Add-Para $sb "生效范围：所有重点股票分析逻辑的后评估" "a" $null "333333"
Add-Para $sb "前置要求：每次盘后复盘必须先读取本文档，严格按照本文档的评估逻辑执行" "a" $null "333333"
Add-Para $sb "存储路径：重点股票\次日评估\" "a" $null "333333"

# ===== 第一章：评估体系概述 =====
Add-Para $sb "一、评估体系概述" "2" $true

Add-Para $sb "1.1 目的与范围" "3" $true
Add-Para $sb "目的：对重点股票分析框架进行系统性复盘，评估六维评分模型、各子指标信号、阈值设定的有效性，持续改进分析逻辑。核心问题不是"这只股票预测对了吗"，而是"我们的分析方法有效吗"。" "a"
Add-Para $sb "核心问题：" "a" $true
Add-Para $sb "1. 六维评分框架是否有效？哪些维度有真正的预测能力？"
Add-Para $sb "2. 每个子指标（MA排列、MACD、RSI、ROE等）的信号准确率如何？"
Add-Para $sb "3. 评分阈值（优秀/良好/一般/差）是否合理？能否区分好坏？"
Add-Para $sb "4. 分析框架是否自洽？评分与结论是否一致？"
Add-Para $sb "5. 随着时间推移，我们的分析是否在进步？"
Add-Para $sb "评估频率：每个交易日盘后执行（累积数据）| 评估数量：全部在库重点股票每次分析的数据点"

Add-Para $sb "1.2 评估流程" "3" $true
Add-Para $sb "采集当日行情 → 读取历史评估数据 → 各维度相关性分析 → 各指标信号胜率计算 → 阈值有效性检验 → 趋势分析 → 生成逻辑诊断报告 → 更新知识积累 → 产出优化建议"

# ===== 第二章：评估维度 =====
Add-Para $sb "二、评估维度" "2" $true

# 2.1 维度有效性
Add-Para $sb "2.1 维度有效性（30分）" "3" $true
Add-Para $sb "核心问题：六维评分框架的每个维度是否真的有预测能力？" "a" $null "666666"

Add-Para $sb "相关性分析（15分）：" "4" $true
Add-Para $sb "对每个维度，计算评分与次日涨跌幅的Pearson相关系数r：r≥0.3（强相关→15分），0.15≤r<0.3（弱相关→8分），0≤r<0.15（不相关→3分），r<0（反向→0分）"

Add-Para $sb "区分度分析（15分）：" "4" $true
Add-Para $sb "按评分分为高分组(≥60)和低分组(<40)，比较次日平均收益差异：差异≥1%（有效→15分），0.5%~1%（部分→8分），<0.5%（无效→3分），反向→0分"

$dimRows = @(
    @("技术面", "r值", "有效/参考/无效"),
    @("基本面", "r值", "有效/参考/无效"),
    @("消息面", "r值", "有效/参考/无效"),
    @("板块面", "r值", "有效/参考/无效"),
    @("资金面", "r值", "有效/参考/无效"),
    @("宏观面", "r值", "有效/参考/无效")
)
Add-Table $sb @("维度", "相关系数r", "有效性评级") $dimRows "1a1a2e"

# 2.2 指标有效性
Add-Para $sb "2.2 指标有效性（30分）" "3" $true
Add-Para $sb "核心问题：每个具体指标发出的信号准确率如何？采用胜率评估：≥65%（强有效），50-65%（参考），40-50%（随机），<40%（反向信号）"

$sigRows = @(
    @("S01", "MA多头排列", "技术面"),
    @("S02", "MA空头排列", "技术面"),
    @("S03", "MACD零轴上金叉", "技术面"),
    @("S04", "MACD死叉", "技术面"),
    @("S05", "RSI超买(≥70)", "技术面"),
    @("S06", "RSI超卖(<30)", "技术面"),
    @("S07", "RSI中性偏强(50-70)", "技术面"),
    @("S08", "布林触及上轨", "技术面"),
    @("S09", "布林触及下轨", "技术面"),
    @("S10", "放量上涨", "技术面"),
    @("S11", "缩量下跌", "技术面"),
    @("S12", "ROE≥15%", "基本面"),
    @("S13", "PE百分位<20%", "基本面"),
    @("S14", "PE百分位>80%", "基本面"),
    @("S15", "主力持续流入", "资金面"),
    @("S16", "主力持续流出", "资金面"),
    @("S17", "北向持股>3%", "资金面"),
    @("S18", "有研报覆盖", "消息面")
)
Add-Table $sb @("编号", "信号名称", "来源维度") $sigRows "1a1a2e"

# 2.3 阈值有效性
Add-Para $sb "2.3 阈值有效性（20分）" "3" $true
Add-Para $sb "核心问题：评分分段（优秀≥80 / 良好60-79 / 一般40-59 / 差<40）是否合理？理想状态：评分越高，次日平均收益和正收益比例越高。优秀段收益>差段收益≥2%（20分）、≥1%（12分）、≥0%（5分）、反向（0分）。"

$threshRows = @(
    @("≥80（优秀）", "N", "X%", "Y%"),
    @("60-79（良好）", "N", "X%", "Y%"),
    @("40-59（一般）", "N", "X%", "Y%"),
    @("<40（差）", "N", "X%", "Y%")
)
Add-Table $sb @("评分段", "样本数", "平均收益%", "正收益%") $threshRows "1a1a2e"

# 2.4 框架一致性
Add-Para $sb "2.4 框架一致性（20分）" "3" $true
Add-Para $sb "核心问题：分析框架内部是否自洽、稳定？" "a" $null "666666"
Add-Para $sb "评分-结论一致性（8分）：高分(≥70)应搭配看多，低分(<40)应搭配看空，统计不一致比例"
Add-Para $sb "置信度校准（6分）：高置信度预判实际准确率≥70%，中置信度≥50%"
Add-Para $sb "多期稳定性（6分）：各维度评分标准差、准确率的逐期波动、极端值出现频率"

# ===== 第三章：知识积累 =====
Add-Para $sb "三、知识积累" "2" $true

Add-Para $sb "3.1 指标有效性跟踪表" "3" $true
Add-Para $sb "存储位置：逻辑积累\指标有效性跟踪.csv，逐日累积各信号的出现次数和胜率"

Add-Para $sb "3.2 改进日志" "3" $true
Add-Para $sb "存储位置：逻辑积累\改进日志.md，每条记录包含：发现、证据、建议、状态"

Add-Para $sb "3.3 优化建议" "3" $true
Add-Para $sb "存储位置：逻辑积累\优化建议.json，结构化输出建议目标和修改方案"

# ===== 第四章：自优化 =====
Add-Para $sb "四、自优化机制" "2" $true

Add-Para $sb "触发条件与建议动作：" "3" $true
$triggerRows = @(
    @("某信号胜率<45%且样本≥10", "调整该信号评分权重"),
    @("某维度r<0.1且样本≥15", "审视该维度评分逻辑"),
    @("优秀段收益≤差段收益", "全面审视阈值设定"),
    @("准确率连续3期下降", "方法论整体审视"),
    @("累积评估≥5次", "触发首次全面优化分析")
)
Add-Table $sb @("条件", "建议动作") $triggerRows "1a1a2e"

Add-Para $sb "优化执行流程：触发条件→读取逻辑积累数据→生成优化建议→人工确认→更新白皮书→记录改进日志→效果跟踪"

Add-Para $sb "设计权衡说明：" "3" $true
Add-Para $sb "自优化机制需平衡三个内在矛盾：" "a" $null "666666"
Add-Para $sb "快速反应 vs 避免过拟合：单日涨跌噪音大，不同触发条件设不同样本门槛。信号胜率<45%需样本≥10（约两周数据），维度r<0.1需样本≥15（约三周），框架级问题不设门槛立即触发。门槛高低对应动作的严重程度——P0提个醒，P1才建议改权重。"
Add-Para $sb "自动化 vs 人工把控：优化流程设计为建议→确认→执行三段式，不让系统自行修改分析逻辑。原因：后评估是质检员不是厂长，它发现问题但不做决策；某些维度失效可能是市场风格切换而非权重问题，需要人的判断。"
Add-Para $sb "短期波动 vs 长期趋势：不关注单日胜率，关注累积胜率的变化趋势。单日数据意义有限，累积胜率匀速下降才是真警报。准确率连续3期下降才触发最高优先级，约一周时间窗，能看出方向性变化但不至于等太久。"

Add-Para $sb "已知局限：" "3" $true
Add-Para $sb "当前系统计算维度有效性时不分市场环境。牛市里技术面可能很准，熊市里资金面可能更有效。计划在积累2-3个月数据后引入市场状态分类（上涨/震荡/下跌），分场景计算维度有效性。另外Pearson相关系数只衡量线性关系，长期可引入分位数回归等方法。"

# ===== 第五章：报告结构 =====
Add-Para $sb "五、逻辑诊断报告结构" "2" $true
Add-Para $sb "1. 报告头—报告名称、评估时间范围、累积数据量"
Add-Para $sb "2. 逻辑诊断摘要—核心发现一句话总结"
Add-Para $sb "3. 维度有效性—各维度评分-收益相关系数排名、区分度"
Add-Para $sb "4. 指标有效性—各信号胜率排名（最佳/最差信号）"
Add-Para $sb "5. 阈值有效性—评分分段收益对比、阈值调整建议"
Add-Para $sb "6. 趋势分析—准确率随时间变化、进步/退步判断"
Add-Para $sb "7. 优化建议—具体可执行的逻辑改进建议"
Add-Para $sb "8. 知识积累更新—新增/更新的积累记录"

# ===== 第七章：自我进化机制 =====
Add-Para $sb "七、自我进化机制" "2" $true
Add-Para $sb "后评估体系自身也需要持续进化。设计了三条进化回路，分别在不同时间尺度上运行。" "a" $null "666666"

Add-Para $sb "7.1 三条进化回路" "3" $true
$loopRows = @(
@("微循环", "每个评估日", "信号发现 + 元评估数据采集", "发现新信号候选、记录评估系统表现"),
@("中循环", "每5次评估", "评估系统自检", "权重优化建议、信号列表增删建议"),
@("大循环", "每月1次", "外部知识融合", "新方法引入、评估框架升级")
)
Add-Table $sb @("回路", "周期", "机制", "产出") $loopRows "1a1a2e"

Add-Para $sb "边界约定：元评估不自循环（不评估'元评估做得好不好'）——那会无限嵌套。系统只采集数据和提建议，不做自动修改。修改与否由人判断。" "a" $null "666666"

Add-Para $sb "7.2 微循环：每日元评估与信号发现" "3" $true
Add-Para $sb "每日评估时自动执行两项工作："
Add-Para $sb "1. 元评估数据采集：记录本次评估各维度得分、样本量、综合评分、建议数、置信度标记。写入 逻辑积累\元评估\评估系统有效性跟踪.csv"
Add-Para $sb "2. 自动信号发现：遍历累积数据中Signals字段的所有值（如Bollinger_Position的"中轨上方"、"中轨下方"等）。对每个值计算胜率（出现次数≥3的）。与当前跟踪列表对比：胜率≥60%且不在跟踪列表中→候选信号；跟踪列表中胜率持续<40%且样本≥10→已淘汰信号。写入 逻辑积累\信号发现\候选信号.json 和 已淘汰信号.json"

Add-Para $sb "7.3 中循环：评估系统自检" "3" $true
Add-Para $sb "每累积5次评估后触发（或手动运行 run_meta_evaluation.ps1），执行三项分析："
Add-Para $sb "维度权重合理性分析：检查每个评估维度的得分方差。方差太小（<1）说明该维度没有区分度、阈值可能过于宽松；方差合理则说明有区分度。输出权重调整建议。"
Add-Para $sb "信号列表管理：从候选信号中选取胜率≥60%且样本≥10的加入跟踪列表；跟踪信号中累积胜率长期在40-60%区间徘徊且样本≥20的建议淘汰。"
Add-Para $sb "评估阈值校验：需累积样本≥50才有意义。分析评分分段（优秀/良好/一般/差）的收益区分度是否合理。"
Add-Para $sb "输出报告：复盘报告\评估系统自检报告_YYYYMMDD.md"

Add-Para $sb "7.4 大循环：月度外部知识融合" "3" $true
Add-Para $sb "每月1次，通过WebSearch搜索量化交易、信号评估、多因子模型等领域的最新方法。搜索关键词包括：量化交易因子有效性评估方法、quantitative analysis signal evaluation methodology、A股多因子模型因子衰减研究、技术指标统计显著性检验。"
Add-Para $sb "输出格式：逻辑积累\元评估\外部知识调研日志.md，记录来源、核心发现、与当前系统的差异、采纳建议。"

Add-Para $sb "7.5 自我进化记录" "3" $true
Add-Para $sb "评估系统有效性跟踪：逻辑积累\元评估\评估系统有效性跟踪.csv"
Add-Para $sb "评估系统变更日志：逻辑积累\元评估\评估系统变更日志.md"
Add-Para $sb "外部知识调研日志：逻辑积累\元评估\外部知识调研日志.md"
Add-Para $sb "候选信号：逻辑积累\信号发现\候选信号.json"
Add-Para $sb "已淘汰信号：逻辑积累\信号发现\已淘汰信号.json"
Add-Para $sb "评估系统自检报告：复盘报告\评估系统自检报告_YYYYMMDD.md"

# ===== 第六章：数据来源 =====
Add-Para $sb "八、数据来源" "2" $true
Add-Para $sb "各维度评分：分析报告中JSON保存 | 指标信号状态：JSON.Signals字段 | 次日涨跌幅：腾讯行情API[1] | 历史评估数据：所有历史评估JSON | 知识积累文件：逻辑积累\*.*"

# ===== 第七章：文件信息 =====
Add-Para $sb "九、文件信息" "2" $true
Add-Para $sb "根目录：Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))\重点股票\次日评估"
Add-Para $sb "逻辑诊断报告：复盘报告\逻辑诊断报告_YYYYMMDD.pdf"
Add-Para $sb "评估数据：评估数据_YYYYMMDD.json"
Add-Para $sb "评估结果：评估结果\评估结果_YYYYMMDD.json"
Add-Para $sb "指标有效性跟踪：逻辑积累\指标有效性跟踪.csv"
Add-Para $sb "改进日志：逻辑积累\改进日志.md"
Add-Para $sb "优化建议：逻辑积累\优化建议.json"
Add-Para $sb "评估系统有效性跟踪：逻辑积累\元评估\评估系统有效性跟踪.csv"
Add-Para $sb "评估系统变更日志：逻辑积累\元评估\评估系统变更日志.md"
Add-Para $sb "外部知识调研日志：逻辑积累\元评估\外部知识调研日志.md"
Add-Para $sb "候选信号：逻辑积累\信号发现\候选信号.json"
Add-Para $sb "已淘汰信号：逻辑积累\信号发现\已淘汰信号.json"
Add-Para $sb "评估系统自检报告：复盘报告\评估系统自检报告_YYYYMMDD.md"
Add-Para $sb "关联白皮书：重点股票跟踪分析逻辑白皮书（需同步更新）"

# ===== 第十章：版本管理 - 通用红线规则 =====
Add-Para $sb "十、版本管理 — 通用红线规则" "2" $true
Add-Para $sb "红线：所有分析白皮书（重点股票次日后评估、重点股票跟踪分析逻辑、每日荐股分析逻辑、次日后评估）只要有内容更新，必须执行本版本管理流程。不允许无版本号的直接修改。" "a" $null "c0392b"

Add-Para $sb "10.1 适用范围" "3" $true
$scopeRows = @(
@("重点股票次日后评估白皮书", "重点股票\\次日评估\\"),
@("重点股票跟踪分析逻辑白皮书", "重点股票\\分析逻辑\\"),
@("每日荐股分析逻辑白皮书", "每日荐股\\分析逻辑\\"),
@("次日后评估白皮书", "每日荐股\\事后评估\\")
)
Add-Table $sb @("白皮书", "存储路径") $scopeRows "1a1a2e"

Add-Para $sb "10.2 版本号规则" "3" $true
Add-Para $sb "格式 v<主版本>.<次版本>：主版本变更（评估维度重构、核心方法论变化），次版本变更（新增/删除章节、调整阈值权重、信号列表管理）。不设patch级别。"
Add-Para $sb "示例：v1→v2（从逐股预测准确率重构为分析逻辑有效性），v1.2→v1.3（新增版本管理章节）"

Add-Para $sb "10.3 版本载体" "3" $true
$verCarrierRows = @(
@("文档头", "> 当前版本: vX.Y | 最后更新", "一眼看到当前版本"),
@("版本历史表", "文档开头版本历史表格", "快速回顾，保留最近10条"),
@("CHANGELOG.md", "同目录独立文件", "完整永久记录，每条含文件变更清单")
)
Add-Table $sb @("载体", "位置", "用途") $verCarrierRows "1a1a2e"

Add-Para $sb "10.4 变更流程" "3" $true
Add-Para $sb "AI或人发现需要改→记录到改进日志.md（含证据）→人工确认→[确认采纳]→升版本号+更新日期→修改文档正文→更新版本历史表→更新CHANGELOG.md→生成新版DOCX"

Add-Para $sb "10.5 归档策略" "3" $true
Add-Para $sb "每个版本独立文件（重点股票次日后评估白皮书_vX.Y.md+.docx），旧版本保留不删（v1.1因命名错乱已删除属特例），CHANGELOG.md是权威变更记录。"

Add-Para $sb "10.6 修改权限" "3" $true
Add-Para $sb "人：任何时候可发起、审批、执行版本变更。AI：只能提议变更（写入改进日志），经人确认后才能执行版本修改。"

# --- 结尾 ---
[void]$sb.Append('</w:body></w:document>')
$documentXml = $sb.ToString()

# --- Write ZIP (DOCX) ---
if (Test-Path $docxPath) { Remove-Item $docxPath -Force }
$stream = [System.IO.File]::Open($docxPath, [System.IO.FileMode]::CreateNew)
$zip = New-Object System.IO.Compression.ZipArchive($stream, [System.IO.Compression.ZipArchiveMode]::Create)

function Add-FileToZip($zip, $path, $content) {
    $entry = $zip.CreateEntry($path, [System.IO.Compression.CompressionLevel]::Optimal)
    $writer = New-Object System.IO.StreamWriter($entry.Open(), [System.Text.Encoding]::UTF8)
    $writer.Write($content)
    $writer.Close()
}

Add-FileToZip $zip "[Content_Types].xml" $contentTypeXml
Add-FileToZip $zip "_rels/.rels" $relsXml
Add-FileToZip $zip "word/_rels/document.xml.rels" $wordRelsXml
Add-FileToZip $zip "word/document.xml" $documentXml
Add-FileToZip $zip "word/styles.xml" $stylesXml
Add-FileToZip $zip "word/settings.xml" $settingsXml
Add-FileToZip $zip "word/fontTable.xml" $fontTableXml
Add-FileToZip $zip "docProps/core.xml" $coreXml
Add-FileToZip $zip "docProps/app.xml" $appXml

$zip.Dispose()
$stream.Close()

Write-Host "✅ DOCX v1.3 generated: $docxPath"
Write-Host "   Size: $((Get-Item $docxPath).Length) bytes"
