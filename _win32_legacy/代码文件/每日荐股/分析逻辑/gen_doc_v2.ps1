. "$PSScriptRoot/../../lib/init_encoding.ps1"
# Generate 每日荐股分析逻辑白皮书 v2.0.docx
Add-Type -AssemblyName System.IO.Compression

function New-OoxmlDoc {
    $bodySb = New-Object System.Text.StringBuilder

    # Helper: add heading
    function AddHeading($sb, $text, $level) {
        if ($sb -is [array] -and $sb.Count -eq 3 -and $null -eq $text) { $text = $sb[1]; $level = $sb[2]; $sb = $sb[0] }
        $styleId = if ($level -eq 1) { "Heading1" } elseif ($level -eq 2) { "Heading2" } else { "Heading3" }
        [void]$sb.Append('<w:p><w:pPr><w:pStyle w:val="' + $styleId + '"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="' + @{1="36";2="28";3="24"}[$level] + '"/><w:b/><w:color w:val="' + @{1="1A1A2E";2="16213E";3="333333"}[$level] + '"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape($text) + '</w:t></w:r></w:p>')
    }

    # Helper: add normal paragraph
    function AddParagraph($sb, $text) {
        if ($sb -is [array] -and $sb.Count -eq 2 -and $null -eq $text) { $text = $sb[1]; $sb = $sb[0] }
        [void]$sb.Append('<w:p><w:pPr><w:spacing w:line="360" w:lineRule="auto"/><w:jc w:val="both"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="22"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape($text) + '</w:t></w:r></w:p>')
    }

    # Helper: add empty line
    function AddEmptyLine($sb) {
        [void]$sb.Append('<w:p><w:pPr><w:spacing w:line="360" w:lineRule="auto"/></w:pPr></w:p>')
    }

    # Helper: add bold paragraph
    function AddBoldParagraph($sb, $text) {
        if ($sb -is [array] -and $sb.Count -eq 2 -and $null -eq $text) { $text = $sb[1]; $sb = $sb[0] }
        [void]$sb.Append('<w:p><w:pPr><w:spacing w:line="360" w:lineRule="auto"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="22"/><w:b/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape($text) + '</w:t></w:r></w:p>')
    }

    # Helper: add colored paragraph
    function AddColorParagraph($sb, $text, $color) {
        if ($sb -is [array] -and $sb.Count -eq 3 -and $null -eq $text) { $text = $sb[1]; $color = $sb[2]; $sb = $sb[0] }
        [void]$sb.Append('<w:p><w:pPr><w:spacing w:line="360" w:lineRule="auto"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="22"/><w:color w:val="' + $color + '"/><w:b/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape($text) + '</w:t></w:r></w:p>')
    }

    # Helper: add table
    function AddTable($sb, $headers, $rows) {
        if ($sb -is [array] -and $sb.Count -eq 3 -and $null -eq $headers) { $headers = $sb[1]; $rows = $sb[2]; $sb = $sb[0] }
        [void]$sb.Append('<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="9500" w:type="dxa"/><w:jc w:val="center"/></w:tblPr>')
        # Header row
        [void]$sb.Append('<w:tr><w:trPr><w:jc w:val="center"/></w:trPr>')
        foreach ($h in $headers) {
            [void]$sb.Append('<w:tc><w:tcPr><w:shd w:val="clear" w:color="auto" w:fill="1A1A2E"/><w:tcW w:w="' + [math]::Round(9500/$headers.Count) + '" w:type="dxa"/></w:tcPr><w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="18"/><w:b/><w:color w:val="FFFFFF"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape($h) + '</w:t></w:r></w:p></w:tc>')
        }
        [void]$sb.Append('</w:tr>')
        # Data rows
        foreach ($row in $rows) {
            [void]$sb.Append('<w:tr><w:trPr><w:jc w:val="center"/></w:trPr>')
            foreach ($cell in $row) {
                [void]$sb.Append('<w:tc><w:tcPr><w:tcW w:w="' + [math]::Round(9500/$headers.Count) + '" w:type="dxa"/></w:tcPr><w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="18"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape($cell) + '</w:t></w:r></w:p></w:tc>')
            }
            [void]$sb.Append('</w:tr>')
        }
        [void]$sb.Append('</w:tbl>')
    }

    # Helper: add bullet paragraph
    function AddBullet($sb, $text) {
        if ($sb -is [array] -and $sb.Count -eq 2 -and $null -eq $text) { $text = $sb[1]; $sb = $sb[0] }
        [void]$sb.Append('<w:p><w:pPr><w:spacing w:line="360" w:lineRule="auto"/><w:ind w:left="720" w:hanging="360"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="22"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape($text) + '</w:t></w:r></w:p>')
    }

    # Helper: add number paragraph
    function AddNumber($sb, $text) {
        if ($sb -is [array] -and $sb.Count -eq 2 -and $null -eq $text) { $text = $sb[1]; $sb = $sb[0] }
        [void]$sb.Append('<w:p><w:pPr><w:spacing w:line="360" w:lineRule="auto"/><w:ind w:left="720" w:hanging="360"/><w:numPr><w:ilvl w:val="0"/><w:numId w:val="2"/></w:numPr></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="22"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape($text) + '</w:t></w:r></w:p>')
    }

    # ========== BUILD DOCUMENT ==========

    # ---- Title ----
    AddEmptyLine($bodySb)
    AddEmptyLine($bodySb)
    AddEmptyLine($bodySb)
    [void]$bodySb.Append('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="48"/><w:b/><w:color w:val="1A1A2E"/></w:rPr><w:t>每日荐股分析逻辑白皮书</w:t></w:r></w:p>')
    AddEmptyLine($bodySb)
    [void]$bodySb.Append('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="36"/><w:b/><w:color w:val="16213E"/></w:rPr><w:t>v2.2</w:t></w:r></w:p>')
    AddEmptyLine($bodySb)
    [void]$bodySb.Append('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="22"/><w:color w:val="666666"/></w:rPr><w:t>铁律量化 · 核心分析引擎</w:t></w:r></w:p>')
    [void]$bodySb.Append('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="20"/><w:color w:val="666666"/></w:rPr><w:t>版本：v2.2 | 2026-05-22</w:t></w:r></w:p>')

    # ---- Prerequisite ----
    AddEmptyLine($bodySb)
    AddEmptyLine($bodySb)
    [void]$bodySb.Append('<w:p><w:pPr><w:pBdr><w:top w:val="single" w:sz="12" w:space="4" w:color="CC0000"/><w:bottom w:val="single" w:sz="12" w:space="4" w:color="CC0000"/><w:left w:val="single" w:sz="12" w:space="8" w:color="CC0000"/><w:right w:val="single" w:sz="12" w:space="8" w:color="CC0000"/></w:pBdr><w:shd w:val="clear" w:color="auto" w:fill="FFF5F5"/><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="24"/><w:b/><w:color w:val="CC0000"/></w:rPr><w:t>⚠️ 前置声明：本分析逻辑受《分析的规则红线--Claude》(v1.0)约束</w:t></w:r></w:p>')
    [void]$bodySb.Append('<w:p><w:pPr><w:pBdr><w:left w:val="single" w:sz="12" w:space="8" w:color="CC0000"/></w:pBdr><w:shd w:val="clear" w:color="auto" w:fill="FFF5F5"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="20"/><w:color w:val="CC0000"/></w:rPr><w:t>AI必须先读取规则红线文档，再执行本分析逻辑。</w:t></w:r></w:p>')

    # ---- Version History Table ----
    AddEmptyLine($bodySb)
    AddHeading($bodySb, "版本历史", 1)
    AddTable($bodySb, @("版本", "日期", "作者", "变更内容"), @(
        ,@("v2.2","2026-05-22","Claude","修复技术分析死代码：恢复K线日采集；新增趋势动量/突破确认评分；均线收敛扣分。评分引擎全面优化(8项子评分)"),
        ,@("v2.1","2026-05-22","Claude","板块动量改用东方财富真实市场数据。新增SectorData采集+相位分类+动量加分"),
        ,@("v2.0","2026-05-22","Claude","全面重构。动态池替代固定42只池；否决制替代评分优先；推荐上限25只"),
        ,@("v1.0","2026-05-21","Claude","初始版本。六维度评分体系、固定42只池")
    ))

    AddEmptyLine($bodySb)
    [void]$bodySb.Append('<w:p><w:pPr><w:pBdr><w:top w:val="single" w:sz="6" w:space="4" w:color="CC0000"/><w:bottom w:val="single" w:sz="6" w:space="4" w:color="CC0000"/></w:pBdr><w:shd w:val="clear" w:color="auto" w:fill="FFF8E1"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="20"/><w:b/><w:color w:val="CC0000"/></w:rPr><w:t>AI必须遵守 — 任何AI在执行分析任务前必须先读取本文档</w:t></w:r></w:p>')

    # ==================== CHAPTER 1 ====================
    AddEmptyLine($bodySb)
    AddHeading($bodySb, "第一章 股票池管理体系", 1)

    AddHeading($bodySb, "1.1 概述", 2)
    AddParagraph($bodySb, "股票池是量化选股的基础。通过分级管理，将全市场5000+只股票逐步缩小到可跟踪、可分析的范畴，确保覆盖效率和分析深度。")

    AddHeading($bodySb, "1.2 五级池架构", 2)
    AddParagraph($bodySb, "全市场池(~5100只) → 剔除ST/*ST/退市/停牌>30日/上市<60日/净资产为负 → 基础池(~800只) → 筛选市值>50亿/日均成交额>5000万/非金融基础覆盖 → 核心观察池(80-120只) → 每日过筛 → 精选推荐池(30-50只) → 触发否决条件 → 剔除/冻结池")

    AddHeading($bodySb, "1.2.1 全市场池→基础池(刚性剔除)", 3)
    AddBullet($bodySb, "ST / *ST / 退市整理期 → 剔除")
    AddBullet($bodySb, "连续停牌超过30个交易日 → 剔除")
    AddBullet($bodySb, "上市不足60个交易日(次新股) → 剔除")
    AddBullet($bodySb, "最近一期净资产为负 → 剔除")
    AddBullet($bodySb, "最近一期营收低于1亿元(非金融) → 剔除")
    AddBullet($bodySb, "流通市值<30亿 → 剔除")

    AddHeading($bodySb, "1.2.2 基础池→核心观察池(柔性筛选)", 3)
    AddBullet($bodySb, "基本面达标：最近一季度净利润为正、营收同比正增长、毛利率>15%")
    AddBullet($bodySb, "行业覆盖：每个申万一级行业至少有2只代表标的")
    AddBullet($bodySb, "量化评分>50分")
    AddBullet($bodySb, "流动性充足：近20日日均成交额>5000万")
    AddBullet($bodySb, "机构覆盖：至少有3家券商研报覆盖(辅助条件)")

    AddHeading($bodySb, "1.2.3 核心观察池→精选推荐池", 3)
    AddParagraph($bodySb, "每日收盘后，执行：六维评分计算 → 一票否决检查 → 行业分布平衡 → 组合层规则校验。评分≥70分且未触发否决的标的进入推荐候选。")

    AddHeading($bodySb, "1.2.4 剔除/冻结池", 3)
    AddBullet($bodySb, "连续30个交易日评分<50分 → 移入剔除池")
    AddBullet($bodySb, "触发绝对否决条件且无法修复 → 移入剔除池")
    AddBullet($bodySb, "行业景气度明确下行 → 移入剔除池")
    AddBullet($bodySb, "剔除池每季度复审一次，条件修复后回归")

    AddHeading($bodySb, "1.3 当前核心观察池(42只)", 2)
    AddParagraph($bodySb, "以下为核心池标的，覆盖算力/AI/半导体/网安/制造/新能源/消费等行业：")

    AddHeading($bodySb, "算力/AI(12只)", 3)
    AddTable($bodySb, @("代码","名称","行业","状态"), @(
        ,@("603019","中科曙光","算力基础设施","积极跟踪"),
        ,@("300502","新易盛","算力/光模块","积极跟踪"),
        ,@("300308","中际旭创","算力/光模块","积极跟踪"),
        ,@("688041","海光信息","算力/芯片","积极跟踪"),
        ,@("300394","天孚通信","算力/光器件","积极跟踪"),
        ,@("688188","柏楚电子","AI/工业软件","积极跟踪"),
        ,@("688111","金山办公","AI/办公软件","积极跟踪"),
        ,@("300624","万兴科技","AI/应用","积极跟踪"),
        ,@("300418","昆仑万维","AI/应用","积极跟踪"),
        ,@("002230","科大讯飞","AI/语音","积极跟踪"),
        ,@("603986","兆易创新","算力/存储","积极跟踪"),
        ,@("688008","澜起科技","算力/接口芯片","积极跟踪")
    ))

    AddEmptyLine($bodySb)
    AddHeading($bodySb, "半导体(8只)", 3)
    AddTable($bodySb, @("代码","名称","行业","状态"), @(
        ,@("603501","韦尔股份","半导体/设计","积极跟踪"),
        ,@("002371","北方华创","半导体/设备","积极跟踪"),
        ,@("688012","中微公司","半导体/设备","积极跟踪"),
        ,@("300661","圣邦股份","半导体/模拟","积极跟踪"),
        ,@("300782","卓胜微","半导体/射频","积极跟踪"),
        ,@("688981","中芯国际","半导体/制造","积极跟踪"),
        ,@("300604","长川科技","半导体/测试","积极跟踪"),
        ,@("000977","浪潮信息","半导体/服务器","积极跟踪")
    ))

    AddEmptyLine($bodySb)
    AddHeading($bodySb, "网安/数字(5只)", 3)
    AddTable($bodySb, @("代码","名称","行业","状态"), @(
        ,@("600845","宝信软件","工业互联网","积极跟踪"),
        ,@("688561","奇安信","网安","积极跟踪"),
        ,@("300454","深信服","网安","积极跟踪"),
        ,@("600570","恒生电子","金融科技","积极跟踪"),
        ,@("002415","海康威视","安防/AI","积极跟踪")
    ))

    AddEmptyLine($bodySb)
    AddHeading($bodySb, "高端制造/新材料(5只)", 3)
    AddTable($bodySb, @("代码","名称","行业","状态"), @(
        ,@("600114","东睦股份","粉末冶金","积极跟踪"),
        ,@("601689","拓普集团","汽车零部件","积极跟踪"),
        ,@("300274","阳光电源","新能源/逆变器","积极跟踪"),
        ,@("300750","宁德时代","新能源/电池","积极跟踪"),
        ,@("002594","比亚迪","新能源/整车","积极跟踪")
    ))

    AddEmptyLine($bodySb)
    AddHeading($bodySb, "消费/蓝筹(5只)", 3)
    AddTable($bodySb, @("代码","名称","行业","状态"), @(
        ,@("600519","贵州茅台","白酒","积极跟踪"),
        ,@("000858","五粮液","白酒","积极跟踪"),
        ,@("000967","盈峰环境","环保","积极跟踪"),
        ,@("600036","招商银行","银行","积极跟踪"),
        ,@("301075","多瑞医药","医药","积极跟踪")
    ))

    AddEmptyLine($bodySb)
    AddHeading($bodySb, "其他备用(7只)", 3)
    AddTable($bodySb, @("代码","名称","行业","状态"), @(
        ,@("002439","启明星辰","网安","备用"),
        ,@("300033","同花顺","金融数据","备用"),
        ,@("688256","寒武纪","AI/芯片","备用"),
        ,@("002920","德赛西威","汽车电子","备用"),
        ,@("300124","汇川技术","工控","备用"),
        ,@("002236","大华股份","安防/AI","备用"),
        ,@("300033","同花顺","金融数据","备用")
    ))

    AddHeading($bodySb, "1.4 行业覆盖率要求", 2)
    AddTable($bodySb, @("行业板块","最低覆盖","单只上限仓位","说明"), @(
        ,@("算力/AI","8只","15%","当前主线赛道"),
        ,@("半导体","5只","15%","国产替代主线"),
        ,@("网安/数字","3只","15%","政策驱动"),
        ,@("高端制造","3只","15%","制造业升级"),
        ,@("消费/蓝筹","3只","20%","防御配置"),
        ,@("其他","按需","10%","事件驱动")
    ))

    # ==================== CHAPTER 2 ====================
    AddEmptyLine($bodySb)
    AddHeading($bodySb, "第二章 板块行业分析框架", 1)

    AddHeading($bodySb, "2.1 行业分类体系", 2)
    AddParagraph($bodySb, "采用申万一级行业分类为骨架，结合市场主线进行赛道归类：")
    AddTable($bodySb, @("赛道","对应申万行业","当前热度"), @(
        ,@("算力基础设施","通信、电子、计算机","🔥高"),
        ,@("AI应用","计算机、传媒","🔥高"),
        ,@("半导体","电子","🔥高"),
        ,@("高端制造","机械、汽车、电力设备","⚡中高"),
        ,@("新能源","电力设备","⚡中"),
        ,@("消费","食品饮料、医药生物","💤中低"),
        ,@("金融","银行、非银金融","💤低"),
        ,@("网络安全","计算机","⚡中")
    ))

    AddHeading($bodySb, "2.2 板块热度评分", 2)
    AddTable($bodySb, @("因子","权重","数据源","评分标准"), @(
        ,@("行业指数涨跌幅","25%","腾讯K线[2]","前5→加分，后5→减分"),
        ,@("行业资金净流入","30%","东方财富[2]","主力净流入前5→加分"),
        ,@("政策事件驱动","20%","新闻搜索[4]","重大利好→加分，利空→减分"),
        ,@("行业成交额占比","15%","腾讯行情[1]","占比提升→热度上升"),
        ,@("龙头股表现","10%","腾讯行情[1]","龙头涨跌指引")
    ))
    AddBoldParagraph($bodySb, "评级：🔥高(≥80) | ⚡中高(60-79) | ⚡中(40-59) | 💤低(<40)")

    AddHeading($bodySb, "2.3 行业专题分析轮换", 2)
    AddParagraph($bodySb, "每日选取评分最高的2只股票所属行业进行深度分析，内容包括政策跟踪、技术动向、产业链格局、竞争格局。数据来源标注[4]新闻搜索+公开信息。")

    # ==================== CHAPTER 3 ====================
    AddEmptyLine($bodySb)
    AddHeading($bodySb, "第三章 六维度评分体系", 1)

    AddHeading($bodySb, "3.1 评分总览", 2)
    AddParagraph($bodySb, "总分 = 基础(10) + 基本面(20) + 技术面(25) + 资金面(20) + 消息面(20) + 风控(5) = 100分")
    AddTable($bodySb, @("总分","评级","操作建议"), @(
        ,@("≥90","⭐极品","优先推荐，可重仓"),
        ,@("≥80","⭐优质","积极推荐"),
        ,@("≥70","🔹达标","可推荐"),
        ,@("60-69","💤观察","不推荐，仅关注"),
        ,@("<60","🚫否决","不推荐")
    ))

    AddHeading($bodySb, "3.2 基础门槛(10分)", 2)
    AddTable($bodySb, @("子项","满分","评分条件"), @(
        ,@("非ST/非亏损","5","正常得5分，ST/亏损否决"),
        ,@("市值评分","3","50-2000亿得3分，<50亿0分，>2000亿1分"),
        ,@("流动性","2","日均成交额>1亿得2分，>5000万1分，<5000万0分")
    ))
    AddColorParagraph($bodySb, "否决条件：流通市值<30亿或日均成交额<3000万→直接否决，不进入评分", "CC0000")

    AddHeading($bodySb, "3.3 基本面(20分)", 2)
    AddTable($bodySb, @("子项","满分","评分条件","数据源"), @(
        ,@("净利润","5",">5亿得5分，>1亿得3分，>0得1分，负值否决","[3]同花顺"),
        ,@("营收","4","同比>20%得4分，>10%得2分，>0得1分","[3]同花顺"),
        ,@("毛利率","4",">50%得4分，>30%得2分，>15%得1分","[3]同花顺"),
        ,@("负债率","4","<30%得4分，<50%得2分，<70%得1分，>70%否决","[3]同花顺"),
        ,@("EPS","3",">2得3分，>1得2分，>0得1分","[3]同花顺")
    ))
    AddColorParagraph($bodySb, "否决条件：净利润连续2季度为负或资产负债率>70%", "CC0000")

    AddHeading($bodySb, "3.4 技术面(25分)", 2)

    AddParagraph($bodySb, "技术面包含8项子评分：均线系统(6分) + 趋势动量(4分) + RSI(3分) + MACD(3分) + 量价配合(4分) + 布林带(3分) + 底部形态(2分) + 突破确认(2分) = 27+, 归一化至25分。技术面评分必须依赖K线数据(60日日K)，若无K线数据则S_Tech=10(数据不足)。")

    AddHeading($bodySb, "3.4.1 均线系统(6分)", 3)
    AddTable($bodySb, @("条件","得分","判定"), @(
        ,@("MA5>MA10>MA20>MA60多头排列","6","强势多头"),
        ,@("MA5>MA10>MA20短中期多头","5","偏强"),
        ,@("MA5>MA10短期多头","4","中性偏强"),
        ,@("均线收敛(spread<1%)","4","蓄势待发"),
        ,@("MA10>MA5短期死叉","2","弱势"),
        ,@("MA10≤MA20中期空头","0且否决","趋势走坏")
    ))
    AddColorParagraph($bodySb, "v2.2修复：均线收敛(spread<1%均线几乎重合)原为6分满分→改为4分，避免横盘股伪装成强势多头。只有真正多头排列+价格在MA20上方才给6分。", "CC0000")

    AddHeading($bodySb, "3.4.2 趋势动量(4分)", 3)
    AddTable($bodySb, @("条件","得分"), @(
        ,@("近5日涨幅>10%","2"),
        ,@("价格在MA20上方>8%","1"),
        ,@("近5日中至少3根阳线","1")
    ))
    AddColorParagraph($bodySb, "v2.2新增：识别持续上涨趋势中但未触发否决的股票。累计最高+4分。", "CC0000")

    AddHeading($bodySb, "3.4.3 RSI(3分)", 3)
    AddTable($bodySb, @("RSI值","得分","信号"), @(
        ,@("40-60","3","中性偏强"),
        ,@("30-40或60-70","2","边界区"),
        ,@("<30或>70","1","超买/超卖"),
        ,@(">80","0","严重超买")
    ))
    AddColorParagraph($bodySb, "例外：若已识别has_breakout突破形态(近10日≥3日振幅>5%+放量突破)，RSI>70得2分(非0分)，突破行情允许适度超买。", "999999")

    AddHeading($bodySb, "3.4.4 MACD(3分)", 3)
    AddTable($bodySb, @("条件","得分"), @(
        ,@("DIF>DEA>0(零轴上金叉)","3"),
        ,@("DIF>DEA>0(零轴上多头减弱)","2"),
        ,@("DIF>DEA(零轴下金叉)","2"),
        ,@("DIF≤DEA(死叉)","0")
    ))

    AddHeading($bodySb, "3.4.5 量价配合(4分)", 3)
    AddTable($bodySb, @("条件","得分","说明"), @(
        ,@("横盘后放量突破","5→4","放量突破前高(最高4分)"),
        ,@("放量上涨(涨幅>3%量比>1.5)","4","真突破特征"),
        ,@("温和上涨(0-2%正常量)","3","健康上涨"),
        ,@("缩量上涨(涨幅>0量比<1.2)","3","筹码锁定"),
        ,@("正常量价","2","无明显信号"),
        ,@("高位放量滞涨","1","出货预警"),
        ,@("放量下跌(跌幅>2%量比>1.5)","0","资金出逃"),
        ,@("缩量下跌(跌幅>0量比<0.8)","1","弱势")
    ))
    AddColorParagraph($bodySb, "v2.2修复：温和上涨从5分降为3分；放量上涨从3分升为4分；新增高位放量滞涨检测(1分)。最高分5→4(横盘后突破)，与其他项合计不超4分。", "CC0000")

    AddHeading($bodySb, "3.4.6 布林带(3分)", 3)
    AddTable($bodySb, @("条件","得分"), @(
        ,@("价格在中轨至上轨间，中轨向上","3"),
        ,@("价格在中轨附近，走平","2"),
        ,@("价格在中轨至下轨间","1"),
        ,@("价格跌破下轨或上轨向下","0")
    ))

    AddHeading($bodySb, "3.4.7 底部形态(2分)", 3)
    AddTable($bodySb, @("条件","得分"), @(
        ,@("双底形态(两个相近低点+突破颈线)","4→2"),
        ,@("横盘整理(近10日振幅<15%)+放量","3→2")
    ))
    AddColorParagraph($bodySb, "v2.2新增：分值归一化后实际最高2分。目的：捕获底部盘整结束、即将启动的标的。", "CC0000")

    AddHeading($bodySb, "3.4.8 突破确认(2分)", 3)
    AddParagraph($bodySb, "has_breakout标志：近10日≥3日振幅>5%(剧烈震荡洗盘) + 当日涨幅>3% + 量比>1.5。触发且价格突破前高→+2分。同时豁免RSI>70的惩罚。")

    AddHeading($bodySb, "3.5 资金面(20分)", 2)
    AddBoldParagraph($bodySb, "数据优先使用腾讯行情[1]外盘/内盘(交易所实盘数据)，东方财富[2]作辅助参考。")

    AddHeading($bodySb, "3.5.1 买卖盘比(8分)", 3)
    AddTable($bodySb, @("买卖比","得分"), @(
        ,@(">1.10","8"),
        ,@("1.05-1.10","6"),
        ,@("1.00-1.05","5"),
        ,@("0.95-1.00","3"),
        ,@("0.90-0.95","1"),
        ,@("<0.90","0")
    ))

    AddHeading($bodySb, "3.5.2 量比趋势(6分)", 3)
    AddTable($bodySb, @("量比","得分","说明"), @(
        ,@("1.5-5.0","6","温和放量"),
        ,@("1.2-1.5","5","小幅放量"),
        ,@("0.8-1.2","4","正常量能"),
        ,@("5.0-12.0","3","大幅放量"),
        ,@("<0.8","2","缩量"),
        ,@(">12.0","封顶2","极端放量→封顶")
    ))
    AddBoldParagraph($bodySb, "量比封顶规则：量比>12时，按8.0-12.0档评分(+2分)，防止极端量比拉高评分。")

    AddHeading($bodySb, "3.5.3 主力资金流向(6分)", 3)
    AddTable($bodySb, @("净流入(估算)","得分"), @(
        ,@("净买入>成交额×5%","6"),
        ,@("净买入0-成交额×5%","4"),
        ,@("净卖出0-成交额×3%","2"),
        ,@("净卖出>成交额×3%","0")
    ))

    AddHeading($bodySb, "3.6 消息面(20分)", 2)

    AddHeading($bodySb, "3.6.1 板块热度(8分)", 3)
    AddTable($bodySb, @("条件","得分"), @(
        ,@("所属板块为市场主线热点","8"),
        ,@("所属板块近期有政策催化","6"),
        ,@("所属板块表现中性","4"),
        ,@("所属板块为冷门/衰退行业","2")
    ))

    AddHeading($bodySb, "3.6.2 RS相对强度(7分)", 3)
    AddParagraph($bodySb, "RS = 个股30日涨幅 / 大盘30日涨幅 × 100")
    AddTable($bodySb, @("RS值","得分","判定"), @(
        ,@(">120","7","显著强势"),
        ,@("100-120","5","偏强"),
        ,@("80-100","3","跟随大盘"),
        ,@("<80","1","弱势"),
        ,@("池内后20%","0","否决候选")
    ))

    AddHeading($bodySb, "3.6.3 新闻情绪(5分)", 3)
    AddTable($bodySb, @("条件","得分"), @(
        ,@("利好新闻为主","5"),
        ,@("中性","3"),
        ,@("轻微利空","1"),
        ,@("重大利空","否决")
    ))

    AddHeading($bodySb, "3.7 风控(5分)", 2)

    AddHeading($bodySb, "3.7.1 30日涨幅(3分)", 3)
    AddTable($bodySb, @("条件","得分","说明"), @(
        ,@("<30%","3","正常"),
        ,@("30-50%","1","涨幅偏大"),
        ,@(">50%","否决","暴涨股否决")
    ))

    AddHeading($bodySb, "3.7.2 波动率(2分)", 3)
    AddTable($bodySb, @("条件","得分"), @(
        ,@("近20日振幅<40%","2"),
        ,@("振幅40-60%","1"),
        ,@("振幅>60%","0")
    ))

    # ==================== CHAPTER 4 ====================
    AddEmptyLine($bodySb)
    AddHeading($bodySb, "第四章 一票否决制", 1)

    AddHeading($bodySb, "4.1 否决与评分的关系", 2)
    AddParagraph($bodySb, "一票否决在评分之前执行。触发否决的标的不计算分数、不进入推荐列表。")
    AddParagraph($bodySb, "执行流程：股票→绝对否决检查→通过→条件否决检查→通过→六维评分。不通过的标的根据不同否决类型分别处理。")

    AddHeading($bodySb, "4.2 绝对否决", 2)
    AddTable($bodySb, @("#","否决条件","阈值","典型场景"), @(
        ,@("1","净利润亏损","连续2季净利为负","亏损股"),
        ,@("2","PE估值泡沫(科技)","PE>80","海光信息PE=260"),
        ,@("3","中期趋势空头","MA10≤MA20","均线死叉"),
        ,@("4","短期暴涨","30日涨幅>50%","中际旭创+78%"),
        ,@("5","财务数据异常","PE无法计算","财报不足"),
        ,@("6","严重负面事件","立案/造假","新闻确认"),
        ,@("7","高负债率","负债率>70%","杠杆过高"),
        ,@("8","流动性枯竭","日均成交额<3000万","无人交易")
    ))

    AddHeading($bodySb, "4.3 条件否决", 2)
    AddTable($bodySb, @("#","否决条件","阈值","豁免条件"), @(
        ,@("1","PE偏高(科技)","PE>120","总分≥85"),
        ,@("2","PE偏高(高成长)","PE>80","总分≥90"),
        ,@("3","短期均线回踩","MA5<MA10×0.99","总分≥85"),
        ,@("4","30日涨幅过高",">50%(市况调整)","见第七章"),
        ,@("5","RS池内后20%","RS<80","总分≥85")
    ))

    AddHeading($bodySb, "4.4 PE估值否决细则", 2)
    AddTable($bodySb, @("行业类型","PE绝对否决","PE条件否决(需≥85分)"), @(
        ,@("科技制造(AI/算力/半导体)",">80",">80"),
        ,@("新能源/汽车",">80",">80"),
        ,@("消费/蓝筹",">50",">50"),
        ,@("金融",">15",">15"),
        ,@("亏损行业(网安)","参考PS估值","参考PS估值")
    ))
    AddBoldParagraph($bodySb, "PE(TTM)=当前股价/EPS(TTM)，EPS(TTM)=最近4个季度净利润之和/总股本。必须基于同花顺[3]EPS计算，禁用腾讯静态PE。")

    # ==================== CHAPTER 5 ====================
    AddEmptyLine($bodySb)
    AddHeading($bodySb, "第五章 操作指令引擎", 1)

    AddHeading($bodySb, "5.1 建仓条件", 2)
    AddParagraph($bodySb, "同时满足以下条件触发买入：")
    AddTable($bodySb, @("#","条件","说明"), @(
        ,@("1","股价在建仓区间内","建仓区间=[MA10,MA5]或[MA10,前收盘]"),
        ,@("2","成交量>MA5均量×1.0","有量能支撑"),
        ,@("3","未触发任何否决","见第四章"),
        ,@("4","评分≥70","见第三章"),
        ,@("5","大盘环境允许","非暴跌日")
    ))
    AddBoldParagraph($bodySb, "禁止买入条件(任一触发则取消)：开盘价>MA5+3%(不追高)；大盘当日跌幅>3%(系统性回避)；个股触发30日涨幅否决。")

    AddHeading($bodySb, "5.2 ATR动态止损", 2)
    AddParagraph($bodySb, "止损价=买入价-2×ATR(14)。ATR(14)为14日平均真实波幅，自动适应不同波动率。")
    AddTable($bodySb, @("股票","买入价","ATR(14)","2×ATR","止损价","幅度"), @(
        ,@("柏楚电子","179.26","4.1","8.2","171.06","-4.6%"),
        ,@("中科曙光","101.36","2.8","5.6","95.76","-5.5%"),
        ,@("新易盛","591.27","12.5","25.0","566.27","-4.2%")
    ))
    AddBoldParagraph($bodySb, "止损硬上限：即使ATR计算超过-8%，止损价仍在买入价的-8%。")

    AddHeading($bodySb, "5.3 分级止盈", 2)
    AddTable($bodySb, @("层级","目标涨幅","操作"), @(
        ,@("第一止盈","+5%","减仓50%"),
        ,@("第二止盈","+10%","减仓剩余50%中的50%"),
        ,@("第三止盈","+15%","清仓")
    ))
    AddBoldParagraph($bodySb, "移动止盈：达到第一止盈后，止损价上移至买入价，确保剩余仓位不亏损。")

    AddHeading($bodySb, "5.4 ATR动态仓位管理", 2)
    AddTable($bodySb, @("ATR/股价","波动率","系数","说明"), @(
        ,@("<2%","低","1.5","适度加仓"),
        @("2%-5%","中","1.0","正常仓位"),
        @(">5%","高","0.5","控制风险")
    ))

    AddHeading($bodySb, "5.5 市场环境仓位调节", 2)
    AddTable($bodySb, @("市场状态","总仓位上限","单只上限"), @(
        ,@("牛市(MA5>MA20>MA60)","100%","20%"),
        @("震荡(均线交织)","80%","15%"),
        @("熊市(MA5<MA20<MA60)","50%","10%")
    ))

    AddHeading($bodySb, "5.6 旁路机制", 2)
    AddParagraph($bodySb, "突发事件驱动的投资机会可通过旁路机制临时加入精选池。条件：明确的事件驱动逻辑+标的满足刚性条件+六维评分≥70+人工确认。单日旁路≤2只。")

    # ==================== CHAPTER 6 ====================
    AddEmptyLine($bodySb)
    AddHeading($bodySb, "第六章 组合层规则", 1)

    AddHeading($bodySb, "6.1 行业分散要求", 2)
    AddTable($bodySb, @("规则","要求"), @(
        ,@("单行业推荐上限","≤推荐总数的40%"),
        @("板块交叉","涉及至少2个不同板块"),
        @("同行业竞争标的","优先评分最高的1-2只")
    ))

    AddHeading($bodySb, "6.2 推荐数量限制", 2)
    AddTable($bodySb, @("市况","推荐上限"), @(
        ,@("正常市场","≤5只"),
        @("震荡市","3-5只"),
        @("熊市","2-3只"),
        @("特殊情况","≤8只(需备注)")
    ))

    AddHeading($bodySb, "6.3 持续跟踪规则", 2)
    AddBullet($bodySb, "持仓期间持续跟踪评分变化")
    AddBullet($bodySb, "评分<60分时触发重新评估")
    AddBullet($bodySb, "触发止损的标的5个交易日内不推荐")
    AddBullet($bodySb, "连续3次触发止损的标的冻结2周")

    # ==================== CHAPTER 7 ====================
    AddEmptyLine($bodySb)
    AddHeading($bodySb, "第七章 市场情绪自适应", 1)

    AddHeading($bodySb, "7.1 市场阶段判定", 2)
    AddTable($bodySb, @("阶段","判定标准"), @(
        ,@("🟢牛市","MA5>MA20>MA60，指数在MA20上方"),
        @("🟡震荡","均线交织，无明显方向"),
        @("🔴熊市","MA5<MA20<MA60，指数在MA20下方")
    ))

    AddHeading($bodySb, "7.2 自适应参数", 2)
    AddTable($bodySb, @("参数","牛市","震荡","熊市"), @(
        ,@("推荐阈值","≥75","≥70","≥65"),
        @("涨幅否决阈值",">80%",">50%",">30%"),
        @("总仓位上限","100%","80%","50%"),
        @("单只上限","20%","15%","10%"),
        @("ATR止损倍数","2.5×","2×","1.5×")
    ))

    AddHeading($bodySb, "7.3 极端市况应对", 2)
    AddTable($bodySb, @("场景","操作"), @(
        ,@("单日大盘跌>3%","暂停当日推荐，已持仓不操作"),
        @("连续3日跌>1.5%","阈值下调5分，减少推荐"),
        @("大盘反弹日(涨>2%)","正常推荐，建仓价在MA10附近")
    ))

    # ==================== CHAPTER 8 ====================
    AddEmptyLine($bodySb)
    AddHeading($bodySb, "第八章 数据质量与置信度", 1)

    AddHeading($bodySb, "8.1 数据来源编号", 2)
    AddTable($bodySb, @("编号","来源","用途","更新频率"), @(
        ,@("[1]","腾讯行情","实时行情、量比、买卖盘","实时"),
        @("[2]","腾讯K线","K线、均线、技术指标","日更新"),
        @("[3]","同花顺财务","财报、EPS、PE(TTM)","季度"),
        @("[4]","新闻搜索","相关新闻/公告","每次分析"),
        @("[5]","本地计算","技术指标、评分","每次分析")
    ))

    AddHeading($bodySb, "8.2 数据质量标签", 2)
    AddTable($bodySb, @("标签","含义","处理方式"), @(
        ,@("🟢完整","所有数据齐全","正常评分推荐"),
        @("🟡部分缺失","个别辅助缺失","按已有数据评分，缺失不计"),
        @("🔴严重缺失","关键数据缺失","不评分，冻结推荐")
    ))

    AddHeading($bodySb, "8.3 交叉验证原则", 2)
    AddBullet($bodySb, "腾讯行情[1]和腾讯K线[2]差异<0.5%→数据一致")
    AddBullet($bodySb, "同花顺[3]PE与腾讯[1]价格交叉验证")
    AddBullet($bodySb, "东方财富数据仅作辅助，冲突时以腾讯为准")
    AddBullet($bodySb, "API限流时启用降级路径")

    # ==================== CHAPTER 9 ====================
    AddEmptyLine($bodySb)
    AddHeading($bodySb, "第九章 报告输出规范", 1)

    AddHeading($bodySb, "9.1 每日推荐报告", 2)
    AddParagraph($bodySb, "每日19:00前输出，包含：精选推荐(评分降序)、全部标的过筛表、否决明细、合规声明。")

    AddHeading($bodySb, "9.2 报告内容要求", 2)
    AddBullet($bodySb, "精选推荐：股票名称/代码/行业标签/六维评分明细/关键指标/操作建议/核心逻辑")
    AddBullet($bodySb, "过筛表：所有核心池标的评分、否决判定")
    AddBullet($bodySb, "否决明细：逐个列出否决原因")
    AddBullet($bodySb, "合规声明：PE计算方式/数据源/免责声明")

    AddHeading($bodySb, "9.3 每日个股简报", 2)
    AddParagraph($bodySb, "内容结构：行动指南→评分总览→评分详解→否决检查→大盘行业→技术分析→关键价位→资金面→消息面→中长期趋势→行业专题→操作策略→风险提示→总结")

    AddHeading($bodySb, "9.4 输出时间线", 2)
    AddTable($bodySb, @("时间","产出","说明"), @(
        ,@("16:00-17:00","个股简报","收盘后逐只分析"),
        @("17:00-18:30","后评估(昨日推荐)","评估昨日推荐"),
        @("18:30-19:00","推荐报告","评分+过筛+推荐")
    ))

    # ==================== CHAPTER 10 ====================
    AddEmptyLine($bodySb)
    AddHeading($bodySb, "第十章 文件信息", 1)

    AddTable($bodySb, @("项目","内容"), @(
        ,@("文件名","每日荐股分析逻辑白皮书_v2.2.docx"),
        @("存储路径","Documents\\Claude\\股票分析\\每日荐股\\分析逻辑\\"),
        @("格式","Office Open XML (.docx)"),
        @("依赖的上层文档","分析的规则红线--Claude v1.0"),
        @("关联后续文档","后评估逻辑白皮书（待重构）")
    ))

    AddEmptyLine($bodySb)
    AddEmptyLine($bodySb)
    [void]$bodySb.Append('<w:p><w:pPr><w:pBdr><w:top w:val="single" w:sz="6" w:space="4" w:color="CCCCCC"/></w:pBdr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="18"/><w:color w:val="999999"/></w:rPr><w:t>本文档为铁律量化系统的核心分析逻辑规范，所有AI在执行分析任务时必须遵守。</w:t></w:r></w:p>')
    [void]$bodySb.Append('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="18"/><w:color w:val="999999"/></w:rPr><w:t>版本：v2.2 | 2026-05-22 | 铁律量化</w:t></w:r></w:p>')

    return $bodySb.ToString()
}

# Main generation
$docPath = [System.IO.Path]::GetFullPath("Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))\每日荐股\分析逻辑\每日荐股分析逻辑白皮书_v2.2.docx")
$tmpZip = [System.IO.Path]::GetTempFileName() + ".zip"

$bodyContent = New-OoxmlDoc

# Content Types
$contentTypes = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
</Types>'

# Relationships
$rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'

# Word relationships (document.xml.rels)
$wordRels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
</Relationships>'

# Styles
$styles = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <w:style w:type="paragraph" w:styleId="Normal" w:default="1">
    <w:name w:val="Normal"/>
    <w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="22"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/>
    <w:pPr><w:spacing w:before="240" w:after="120"/></w:pPr>
    <w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="36"/><w:b/><w:color w:val="1A1A2E"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="heading 2"/>
    <w:pPr><w:spacing w:before="200" w:after="100"/></w:pPr>
    <w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="28"/><w:b/><w:color w:val="16213E"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading3">
    <w:name w:val="heading 3"/>
    <w:pPr><w:spacing w:before="160" w:after="80"/></w:pPr>
    <w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="24"/><w:b/><w:color w:val="333333"/></w:rPr>
  </w:style>
  <w:style w:type="table" w:styleId="TableGrid">
    <w:name w:val="Table Grid"/>
    <w:pPr><w:spacing w:after="0"/></w:pPr>
    <w:tblPr><w:tblBorders><w:top w:val="single" w:sz="4" w:space="0" w:color="CCCCCC"/><w:left w:val="single" w:sz="4" w:space="0" w:color="CCCCCC"/><w:bottom w:val="single" w:sz="4" w:space="0" w:color="CCCCCC"/><w:right w:val="single" w:sz="4" w:space="0" w:color="CCCCCC"/><w:insideH w:val="single" w:sz="4" w:space="0" w:color="CCCCCC"/><w:insideV w:val="single" w:sz="4" w:space="0" w:color="CCCCCC"/></w:tblBorders></w:tblPr>
  </w:style>
</w:styles>'

# Numbering (for bullets and numbered lists)
$numbering = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:abstractNum w:abstractNumId="0">
    <w:multiLevelType w:val="hybridMultilevel"/>
    <w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="●"/><w:rPr><w:rFonts w:ascii="Symbol" w:hAnsi="Symbol"/></w:lvlText></w:lvl>
  </w:abstractNum>
  <w:abstractNum w:abstractNumId="1">
    <w:multiLevelType w:val="hybridMultilevel"/>
    <w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/></w:lvl>
  </w:abstractNum>
  <w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
  <w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>
</w:numbering>'

# Build document XML
$documentXml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <w:body>' + $bodyContent + '</w:body>
</w:document>'

try {
    # Create ZIP with proper directory structure
    $zipStream = [System.IO.File]::Open($tmpZip, [System.IO.FileMode]::Create)
    $zip = New-Object System.IO.Compression.ZipArchive($zipStream, [System.IO.Compression.ZipArchiveMode]::Create)

    # Required OOXML parts
    $entries = @(
        @("[Content_Types].xml", $contentTypes),
        @("_rels/.rels", $rels),
        @("word/document.xml", $documentXml),
        @("word/styles.xml", $styles),
        @("word/numbering.xml", $numbering),
        @("word/_rels/document.xml.rels", $wordRels)
    )

    foreach ($entry in $entries) {
        $name = $entry[0]
        $content = $entry[1]
        $file = $zip.CreateEntry($name)
        $writer = New-Object System.IO.StreamWriter($file.Open(), [System.Text.Encoding]::UTF8)
        $writer.Write($content)
        $writer.Flush()
        $writer.Dispose()
    }

    $zip.Dispose()
    $zipStream.Dispose()

    # Rename to .docx and move
    $finalDocx = $tmpZip -replace '\.zip$', '.docx'
    Rename-Item -Path $tmpZip -NewName ([System.IO.Path]::GetFileName($finalDocx)) -Force

    if (Test-Path $docPath) { Remove-Item $docPath -Force }
    Move-Item -Path $finalDocx -Destination $docPath -Force

    Write-Host "SUCCESS: Document generated at $docPath"
    Write-Host "Size: $((Get-Item $docPath).Length) bytes"
}
catch {
    Write-Host "ERROR: $_"
    try { if ($zip) { $zip.Dispose() } } catch {}
    try { if ($zipStream) { $zipStream.Dispose() } } catch {}
    if (Test-Path $tmpZip) { Remove-Item $tmpZip -Force }
    if (Test-Path ($tmpZip -replace '\.zip$', '.docx')) { Remove-Item ($tmpZip -replace '\.zip$', '.docx') -Force }
    exit 1
}
