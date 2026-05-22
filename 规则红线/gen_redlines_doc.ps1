# Generate 分析的规则红线--Claude v1.2.docx
function New-RedlinesDocBody {
    $sb = New-Object System.Text.StringBuilder
    function AddH($sb, $text, $lvl) {
        $sid = if ($lvl -eq 1) { "Heading1" } elseif ($lvl -eq 2) { "Heading2" } else { "Heading3" }
        $sz = @{1="36";2="28";3="24"}[$lvl]; $clr = @{1="1A1A2E";2="16213E";3="333333"}[$lvl]
        [void]$sb.Append('<w:p><w:pPr><w:pStyle w:val="' + $sid + '"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="' + $sz + '"/><w:b/><w:color w:val="' + $clr + '"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape($text) + '</w:t></w:r></w:p>')
    }
    function AddP($sb, $t) { [void]$sb.Append('<w:p><w:pPr><w:spacing w:line="360" w:lineRule="auto"/><w:jc w:val="both"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="22"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape($t) + '</w:t></w:r></w:p>') }
    function AddBP($sb, $t) { [void]$sb.Append('<w:p><w:pPr><w:spacing w:line="360" w:lineRule="auto"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="22"/><w:b/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape($t) + '</w:t></w:r></w:p>') }
    function AddE($sb) { [void]$sb.Append('<w:p><w:pPr><w:spacing w:line="360" w:lineRule="auto"/></w:pPr></w:p>') }
    function AddTbl($sb, $hds, $rows) {
        $w = if ($hds.Count -ge 6) { "9500" } else { "8500" }
        [void]$sb.Append('<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="' + $w + '" w:type="dxa"/><w:jc w:val="center"/></w:tblPr>')
        [void]$sb.Append('<w:tr><w:trPr><w:jc w:val="center"/></w:trPr>')
        foreach ($h in $hds) {
            [void]$sb.Append('<w:tc><w:tcPr><w:shd w:val="clear" w:color="auto" w:fill="1A1A2E"/><w:tcW w:w="' + [math]::Round([int]$w/$hds.Count) + '" w:type="dxa"/></w:tcPr><w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="16"/><w:b/><w:color w:val="FFFFFF"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape($h) + '</w:t></w:r></w:p></w:tc>')
        }
        [void]$sb.Append('</w:tr>')
        foreach ($row in $rows) {
            [void]$sb.Append('<w:tr><w:trPr><w:jc w:val="center"/></w:trPr>')
            foreach ($cell in $row) {
                [void]$sb.Append('<w:tc><w:tcPr><w:tcW w:w="' + [math]::Round([int]$w/$hds.Count) + '" w:type="dxa"/></w:tcPr><w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="16"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape($cell) + '</w:t></w:r></w:p></w:tc>')
            }
            [void]$sb.Append('</w:tr>')
        }
        [void]$sb.Append('</w:tbl>')
    }
    # ===== BUILD =====
    AddE $sb; AddE $sb; AddE $sb
    [void]$sb.Append('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="44"/><w:b/><w:color w:val="1A1A2E"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape("量化分析铁律 - 分析的规则红线") + '</w:t></w:r></w:p>')
    AddE $sb
    [void]$sb.Append('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="32"/><w:b/><w:color w:val="16213E"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape("v1.2") + '</w:t></w:r></w:p>')
    AddE $sb
    [void]$sb.Append('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="20"/><w:color w:val="666666"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape("当前版本: v1.2 | 最后更新: 2026-05-22 | 更新人: Claude | 生效范围: 所有A股量化分析/选股/荐股/报告生成/白皮书版本管理") + '</w:t></w:r></w:p>')
    AddE $sb
    [void]$sb.Append('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="20"/><w:color w:val="CC0000"/><w:b/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape("违反后果: 必须立即停止并修正 | 前置要求: AI必须遵守") + '</w:t></w:r></w:p>')
    AddE $sb; AddE $sb
    # Version history
    AddH $sb "版本历史" 1
    AddTbl $sb @("版本","日期","作者","修改内容","修改原因") @(
        ,@("v1.2","2026-05-22","Claude","新增§5.4全分析白皮书版本管理要求:覆盖4份白皮书，明确版本号规则/变更流程/归档策略/修改权限","用户要求所有分析白皮书更新必须执行版本管理流程")
        ,@("v1.1","2026-05-21","Claude","新增数据源[6]~[12](akshare系列)；新增§1.5数据源实测状态；更新§4检查清单；逐项审计重点股票白皮书指标合规性","重点股票跟踪分析逻辑白皮书v1.0引入多维度新指标，需要明确数据源合规性")
        ,@("v1.0","2026-05-21","Claude","初始版本创建。基于原v1.7重构","用户要求重构规则红线文档")
    )
    # Chapter 1
    AddE $sb; AddH $sb "一、数据真实性铁律（最高优先级）" 1
    AddH $sb "1.1 绝对禁止" 2
    AddBP $sb "所有出现在报告中的数字，必须来自真实数据源。"
    AddBP $sb "允许：从腾讯行情API、同花顺(akshare)、Baostock等接口获取的真实数据；基于真实数据的本地计算（移动均线、RSI、MACD、量比等）；标注为[季报数据，非实时]的财报数据。"
    AddBP $sb "禁止：在没有数据时凭空赋值或编造任何数字；用AI模型推断缺失的财务指标；使用无法通过截图或链接验证的听说数据。"
    AddH $sb "1.2 数据源编号与标注规则" 2
    AddP $sb "报告中每个关键数字必须标注其数据来源："
    AddTbl $sb @("编号","数据源","用途","实时性","调用方式") @(
        ,@("[1]","腾讯行情API","当前价/涨跌幅/外盘内盘/量比/换手率/流通市值","实时","HTTP GET")
        ,@("[2]","腾讯K线","日K线数据(开/收/高/低/成交量)","实时","HTTP GET")
        ,@("[3]","同花顺财务摘要(akshare)","净利润/营收/毛利率/负债率/EPS/扣非净利","季度","akshare")
        ,@("[4]","Baostock","K线验证/净利润交叉验证/全市场股票列表","日/季度","baostock")
        ,@("[5]","本地计算","均线/RSI/MACD/布林/PE(TTM)/支撑阻力","基于原始数据","—")
        ,@("[6]","akshare深度财务","EV/EBITDA组件/存货周转率/经营性现金流/股息率","季度","akshare stock_financial_abstract")
        ,@("[7]","东方财富板块行业","申万行业/概念板块指数走势/成分股列表","日","HTTP GET(East Money push2)")
        ,@("[8]","东方财富北向资金","沪/深股通持股明细(个股季度持股)","季度","HTTP GET(datacenter-web)")
        ,@("[9]","东方财富个股资金流向","主力净流入/超大单/大单净流入","日","HTTP GET(East Money push2)")
        ,@("[10]","东方财富行业资金流向","各行业资金净流入排名","日","HTTP GET(East Money push2)")
        ,@("[11]","东方财富研报/评级","研报标题/机构/评级/盈利预测","日","HTTP GET(reportapi.eastmoney.com)")
        ,@("[12]","东方财富融资融券","融资余额/融券余额/融资净买入/融券余量","日","HTTP GET(datacenter.eastmoney.com)")
    )
    AddBP $sb "标注格式示例：[估值区间来源于同花顺深度财务数据] 估值区间[6]；[北向资金净流入来源于akshare北向资金接口] 北向资金净流入8.2亿[8]"
    AddH $sb "1.3 PE(TTM) 计算红线" 2
    AddP $sb "禁止直接使用腾讯行情API提供的静态PE作为否决依据。"
    AddBP $sb "PE(TTM) = 当前价[1] / TTM_EPS[3]"
    AddBP $sb "TTM_EPS = 最新年报EPS - 去年同季EPS + 最新季报EPS"
    AddH $sb "1.4 双源交叉验证规则" 2
    AddTbl $sb @("指标","主源","辅源","偏差处理规则") @(
        ,@("净利润","同花顺[3]","Baostock[4]","<5%采用同花顺;5~15%取较低值;>15%需核查")
        ,@("营收","同花顺[3]","Baostock[4]","同上")
        ,@("PE(TTM)","TTM EPS计算","腾讯静PE(参考)","TTM PE为主判据")
        ,@("毛利率","同花顺[3]","Baostock[4]","偏差<5%即可")
        ,@("扣非净利润","同花顺[3]","无","唯一来源,标注仅供参考")
        ,@("当前价/K线","腾讯[1][2]","Baostock[4]","已确认100%一致")
        ,@("外盘/内盘/买卖比","腾讯[1]","无","标注交易所实时数据")
        ,@("量比/换手率","腾讯[1]","无","标注交易所实时数据")
        ,@("板块指数","东方财富[7]HTTP","Baostock[4]","✅已实测")
        ,@("北向资金持股","东方财富[8]HTTP","无","✅已实测(季度数据)")
        ,@("资金流向","东方财富[9][10]HTTP","无","✅已实测,唯一来源,标注仅供参考")
    )
    AddH $sb "1.5 数据源实测状态" 2
    AddP $sb "本表记录每个数据源的实测情况。未实测的数据源在报告中必须标注待验证，严禁将未验证的数据作为否决依据。"
    AddTbl $sb @("编号","数据源","实测状态","验证日期","覆盖","备注") @(
        ,@("[1]","腾讯行情API","✅已实测","2026-05-21","全市场","已在每日荐股中使用")
        ,@("[2]","腾讯K线","✅已实测","2026-05-21","全市场","已在每日荐股中使用")
        ,@("[3]","同花顺财务摘要","✅已实测","2026-05-21","全市场","已在每日荐股中使用")
        ,@("[4]","Baostock","✅已实测","2026-05-21","全市场","用于交叉验证")
        ,@("[5]","本地计算","✅已实测","2026-05-21","全市场","均线/MACD/RSI等标准算法")
        ,@("[6]","深度财务(东财HTTP)","⚠️待验证","—","—","接口待集成测试")
        ,@("[7]","东方财富板块行业","✅已实测","2026-05-21","行业/概念","HTTP GET已验证")
        ,@("[8]","东方财富北向资金","✅已实测","2026-05-21","全市场","HTTP GET已验证(季度持股)")
        ,@("[9]","东方财富个股资金流向","✅已实测","2026-05-21","全市场","HTTP GET已验证")
        ,@("[10]","东方财富行业资金流向","✅已实测","2026-05-21","全行业","HTTP GET已验证")
        ,@("[11]","东方财富研报/评级","✅已实测","2026-05-21","全市场","HTTP GET已验证")
        ,@("[12]","东方财富融资融券","✅已实测","2026-05-21","全市场","HTTP GET已验证")
    )
    AddH $sb "1.5.1 关键指标数据来源映射" 3
    AddTbl $sb @("章节","指标","数据源","测试状态","决策依据") @(
        ,@("1.1.1","多周期均线趋势","[2]→[5]","✅已实测","✅可决策")
        ,@("1.1.2","Wyckoff量价分析","[2]→[5]AI分析","✅底层数据可信","✅可决策")
        ,@("1.1.3","经典技术形态","[2]→[5]模式识别","✅底层数据可信","✅可参考")
        ,@("1.1.4","MACD/RSI/布林/ADX/OBV等","[2]→[5]","✅已实测","✅可决策")
        ,@("1.1.5","K线组合形态","[2]→[5]","✅底层数据可信","✅可参考")
        ,@("1.2.1","ROE/毛利率/增长率/负债率/PE","[3]→[5]","✅已实测","✅可决策")
        ,@("1.2.1","PE百分位(历史)","[2]+[3]→[5]计算模块","✅已开发实测","✅可输出(已验证)")
        ,@("1.2.2","PE/PB/PS/股息率","[3]","✅已实测","✅可决策")
        ,@("1.2.2","EV/EBITDA","[6]","❌未实测","⚠️不可输出数值")
        ,@("1.2.2","DCF估值","[3][6]+AI推算","❌推算类","⚠️必须标注估算")
        ,@("1.2.3","核心竞争力分析","AI定性","✅AI分析","✅可输出")
        ,@("1.3.1","催化剂分级S/A/B/C","AI分析","✅AI判断","✅可输出")
        ,@("1.3.3","研报覆盖数/分析师评级","[11]HTTP GET","✅已实测","✅可输出(30天内)")
        ,@("1.3.3","融资融券余额","[12]HTTP GET","✅已实测","✅可输出")
        ,@("1.3.3","社交媒体热度","无免费API","❌不可获取","❌移除或人工录入")
        ,@("1.3.3","互动平台活跃度","无公开API","❌不可获取","❌移除或人工录入")
        ,@("1.4.1","板块相位判断","[7]HTTP GET","✅已实测","✅可输出")
        ,@("1.4.2","板块轮动位置","AI定性","✅AI分析","✅可输出")
        ,@("1.4.3","行业内联动/共振度","[2][4][7]","✅板块[7]已实测","⚠️需开发批量计算")
        ,@("1.5.1","北向资金持股","[8]HTTP GET","✅已实测(季度)","✅可输出(季度持股)")
        ,@("1.5.1","主力净流入/超大单","[9]HTTP GET","✅已实测","✅可输出")
        ,@("1.5.1","机构大宗交易","无免费API","❌不可获取","❌移除或人工录入")
        ,@("1.5.1","行业资金流向","[10]HTTP GET","✅已实测","✅可输出")
        ,@("1.5.2","量能分析(放量/缩量)","[2]→[5]","✅已实测","✅可决策")
        ,@("1.5.3","筹码分布/获利比例","需Level-2付费","❌不可获取","❌移除或人工录入")
        ,@("3.1","六维评分","多源融合+AI","✅技术/基本面/板块/资金已验证","⚠️消息面/宏观待验证")
        ,@("3.2","趋势健康度","[2]→[5]","✅可计算","✅可输出")
    )
    AddH $sb "1.5.2 指标整改优先级" 3
    AddTbl $sb @("优先级","指标","整改要求","完成时限") @(
        ,@("P2","EV/EBITDA[6]","实测东财深度财务HTTP接口","一个月内")
        ,@("—","北向资金/研报/融券[8][11][12]","✅已通过HTTP GET解决","已完成")
        ,@("P3","筹码分布/大宗交易/社交情绪","评估替代方案或移除","待定")
        ,@("P3","筹码分布","评估是否购买Level-2或降级","待定")
        ,@("P3","社交媒体/互动平台/大宗交易","评估替代方案或移除","待定")
    )
    # Chapter 2
    AddE $sb; AddH $sb "二、资源节约铁律" 1
    AddH $sb "2.1 核心原则" 2
    AddP $sb "Token是付费资源。能用本地或免费资源完成的工作，禁止用AI Token完成。免费公开API抓取->本地计算处理->AI分析。"
    AddTbl $sb @("层级","成本","承担工作") @(
        ,@("数据获取层","零Token","API调用/数据格式化/缓存读写-由代码执行，AI不参与")
        ,@("分析决策层","消耗Token","评分判断/否决判定/报告文本生成-AI参与")
        ,@("校验层","少量Token","交叉验证/异常检测-AI参与，原始数据比对由代码完成")
    )
    AddH $sb "2.2 Token使用边界" 2
    AddBP $sb "允许：AI处理分析逻辑判断/规则解读/报告文本生成；AI对比多个数据源做一致性校验；AI根据评估结果提出规则优化建议。"
    AddBP $sb "禁止：让AI用自然语言估算已有API可获取的数据；无谓的重复调用；把原始数据全文喂给AI做阅读理解。"
    # Chapter 3
    AddE $sb; AddH $sb "三、API调用纪律与缓存策略" 1
    AddH $sb "3.1 数据分层与缓存" 2
    AddTbl $sb @("层级","数据","数据源","调用时机","缓存策略") @(
        ,@("实时","收盘价/涨跌幅/买卖比","腾讯行情[1]","每次分析时","不缓存，必须当日")
        ,@("实时","120日日K线","腾讯K线[2]","每次分析时","不缓存")
        ,@("实时","技术指标","本地计算[5]","每次分析时","基于K线实时计算")
        ,@("日更","板块行业","东方财富[7]HTTP","每次分析时","缓存24h")
        ,@("日更","北向资金(季度持股)","东方财富[8]HTTP","每次分析时","缓存24h")
        ,@("日更","资金流向","东方财富[9][10]HTTP","每次分析时","缓存24h")
        ,@("日更","研报/评级","东方财富[11]HTTP","每次分析时","缓存24h")
        ,@("日更","融资融券","东方财富[12]HTTP","每次分析时","缓存24h")
        ,@("日更","消息面新闻","同花顺新闻","每次分析时","缓存24h")
        ,@("季度","财务数据","[3]/Baostock[4]","季报发布后","缓存30天")
        ,@("季度","深度财务","akshare[6]","季报发布后","缓存30天")
        ,@("季度","PE(TTM)","本地计算[5]","财报更新日","财报不换PE不变")
    )
    AddH $sb "3.2 防封禁规则" 2
    AddBP $sb "每次API调用后强制间隔>=0.3秒；每10次调用后额外休息>=2秒；同花顺/akshare财务数据仅在缓存过期时调用(每季度1次)；禁止在短时间内(<5分钟)重复拉取同一只股票的同一类数据。"
    AddH $sb "3.3 降级路径" 2
    AddTbl $sb @("主数据源","降级方案","标注要求") @(
        ,@("腾讯行情[1]","腾讯买卖五档","标注降级源")
        ,@("腾讯K线[2]","腾讯日K/qfqday","标注降级源")
        ,@("同花顺财务[3]","使用缓存数据","标注可能滞后")
        ,@("Baostock[4]","接受单源","标注未经交叉验证")
        ,@("东方财富系列[7]~[12]","降级为缓存数据","标注数据不可用，降级定性判断")
    )
    AddH $sb "3.4 调用监控与告警" 2
    AddBP $sb "以下情况必须告警并暂停分析：单次分析API调用失败率>20%；连续3次同花顺/akshare API调用失败；腾讯API响应时间异常(单次>3秒)；降级路径连续2次以上仍不可用；akshare接口返回空数据或异常数据。"
    # Chapter 4
    AddE $sb; AddH $sb "四、执行检查清单" 1
    $checklist = @(
        "所有数据有来源标记","关键财务已双源验证","无编造数据","PE(TTM)用同花顺EPS",
        "API调用已加延迟","季度数据用缓存","报告有免责声明","一票否决已执行",
        "降级路径已标注","数据时效已标注",
        "未实测数据源[6]须标注待验证([1]~[5][7]~[12]已实测可用)",
        "不可获取指标(筹码分布/大宗交易/社交情绪)不得输出具体数值",
        "PE百分位已开发完成,可输出(需标注数据范围)"
    )
    foreach ($item in $checklist) {
        AddBP $sb ("☐ " + $item)
    }
    # Chapter 5
    AddE $sb; AddH $sb "五、规则变更协议" 1
    AddH $sb "5.1 变更权限" 2
    AddP $sb "红线规则修改需人工确认，AI不可直接执行。变更前必须读取当前版本和同级CHANGELOG.md。"
    AddH $sb "5.2 变更条件" 2
    AddTbl $sb @("变更类型","触发条件","最低数据量") @(
        ,@("数据源新增/替换","实测验证通过","3只股票以上")
        ,@("API调用策略调整","连续3次以上失败","3次失败记录")
        ,@("交叉验证规则修改","5个以上样本支撑","5个样本")
        ,@("降级路径调整","降级连续2次仍不可用","2次不可用")
        ,@("数据源状态变更(未实测->已实测)","接口验证通过+3只股票以上确认","3只股票")
    )
    AddH $sb "5.3 变更执行流程" 2
    AddBP $sb "每次变更必须：1)在版本历史表追加新行；2)更新CHANGELOG；3)更新文档版本索引；4)修改文件名(主版本需保留旧版存档)；5)更新数据源实测状态表。"
    AddH $sb "5.4 全分析白皮书版本管理要求(红线)" 2
    AddP $sb "红线：以下4份白皮书只要有内容更新，必须执行本版本管理流程。不允许无版本号的直接修改。"
    AddTbl $sb @("白皮书","存储路径") @(
        ,@("重点股票次日后评估白皮书","重点股票\次日评估\")
        ,@("重点股票跟踪分析逻辑白皮书","重点股票\分析逻辑\")
        ,@("每日荐股分析逻辑白皮书","每日荐股\分析逻辑\")
        ,@("次日后评估白皮书","每日荐股\事后评估\")
    )
    AddH $sb "5.4.1 版本号规则" 3
    AddP $sb "格式 v<主版本>.<次版本>。主版本：评估维度重构、核心方法论变更(v1→v2)。次版本：新增/删除章节、调整阈值权重、信号列表管理(v1.2→v1.3)。不设patch级别。"
    AddH $sb "5.4.2 版本载体" 3
    AddTbl $sb @("载体","位置","用途") @(
        ,@("文档头","> 当前版本: vX.Y | 最后更新","一眼看到当前版本")
        ,@("版本历史表","文档开头版本历史表格","快速回顾，保留最近10条")
        ,@("CHANGELOG.md","同目录独立文件","完整永久记录，每条含文件变更清单")
    )
    AddH $sb "5.4.3 变更流程" 3
    AddP $sb "AI或人发现需要改 -> 记录到改进日志.md(含证据) -> 人工确认 -> [确认采纳] -> 升版本号+更新日期 -> 修改文档正文 -> 更新版本历史表 -> 更新CHANGELOG.md -> 生成新版DOCX"
    AddH $sb "5.4.4 归档策略" 3
    AddP $sb "每个版本独立文件(白皮书名称_vX.Y.md+.docx)，旧版本保留不删，历史可追溯。CHANGELOG.md是权威变更记录，文档内版本历史表是快速索引。"
    AddH $sb "5.4.5 修改权限" 3
    AddP $sb "人：任何时候可发起、审批、执行版本变更。AI：只能提议变更(写入改进日志)，经人确认后才能执行版本修改。"
    # Chapter 6
    AddE $sb; AddH $sb "六、文件信息" 1
    AddTbl $sb @("项目","内容") @(
        ,@("文件名","分析的规则红线--Claude_v1.2.docx")
        ,@("存储路径","C:\Users\34269\Documents\Claude\股票分析\规则红线")
        ,@("当前版本","v1.2")
        ,@("最后更新","2026-05-22")
        ,@("更新人","Claude")
        ,@("关联CHANGELOG","分析的规则红线--Claude_CHANGELOG.md")
        ,@("文档版本索引","文档版本索引.md")
    )
    # Footer
    AddE $sb; AddE $sb
    [void]$sb.Append('<w:p><w:pPr><w:pBdr><w:top w:val="single" w:sz="6" w:space="4" w:color="CCCCCC"/></w:pBdr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="18"/><w:color w:val="999999"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape("本文档为铁律量化系统最高优先级规则。其他所有分析逻辑必须在不违反本文档的前提下执行。") + '</w:t></w:r></w:p>')
    [void]$sb.Append('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="18"/><w:color w:val="999999"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape("版本：v1.2 | 2026-05-22 | 铁律量化") + '</w:t></w:r></w:p>')
    return $sb.ToString()
}
# Main
$docPath = [System.IO.Path]::GetFullPath("C:\Users\34269\Documents\Claude\股票分析\规则红线\分析的规则红线--Claude_v1.2.docx")
$tmpZip = [System.IO.Path]::GetTempFileName() + ".zip"
$bodyContent = New-RedlinesDocBody
$contentTypes = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
</Types>'
$rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'
$wordRels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
</Relationships>'
$styles = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:styleId="Normal" w:default="1"><w:name w:val="Normal"/><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="22"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:pPr><w:spacing w:before="240" w:after="120"/></w:pPr><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="36"/><w:b/><w:color w:val="1A1A2E"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:pPr><w:spacing w:before="200" w:after="100"/></w:pPr><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="28"/><w:b/><w:color w:val="16213E"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:pPr><w:spacing w:before="160" w:after="80"/></w:pPr><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="24"/><w:b/><w:color w:val="333333"/></w:rPr></w:style>
  <w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/><w:pPr><w:spacing w:after="0"/></w:pPr><w:tblPr><w:tblBorders><w:top w:val="single" w:sz="4" w:space="0" w:color="CCCCCC"/><w:left w:val="single" w:sz="4" w:space="0" w:color="CCCCCC"/><w:bottom w:val="single" w:sz="4" w:space="0" w:color="CCCCCC"/><w:right w:val="single" w:sz="4" w:space="0" w:color="CCCCCC"/><w:insideH w:val="single" w:sz="4" w:space="0" w:color="CCCCCC"/><w:insideV w:val="single" w:sz="4" w:space="0" w:color="CCCCCC"/></w:tblBorders></w:tblPr></w:style>
</w:styles>'
$numbering = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="hybridMultilevel"/><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="●"/><w:rPr><w:rFonts w:ascii="Symbol" w:hAnsi="Symbol"/></w:rPr></w:lvl></w:abstractNum>
  <w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
</w:numbering>'
$documentXml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <w:body>' + $bodyContent + '</w:body>
</w:document>'
try {
    [System.Reflection.Assembly]::LoadWithPartialName("System.IO.Compression.FileSystem") | Out-Null
    [System.Reflection.Assembly]::LoadWithPartialName("System.IO.Compression") | Out-Null
    $zipStream = [System.IO.File]::Open($tmpZip, [System.IO.FileMode]::Create)
    $zip = New-Object System.IO.Compression.ZipArchive($zipStream, [System.IO.Compression.ZipArchiveMode]::Create)
    $entries = @(@("[Content_Types].xml",$contentTypes),@("_rels/.rels",$rels),@("word/document.xml",$documentXml),@("word/styles.xml",$styles),@("word/numbering.xml",$numbering),@("word/_rels/document.xml.rels",$wordRels))
    foreach ($entry in $entries) {
        $file = $zip.CreateEntry($entry[0])
        $writer = New-Object System.IO.StreamWriter($file.Open(), [System.Text.Encoding]::UTF8)
        $writer.Write($entry[1]); $writer.Flush(); $writer.Dispose()
    }
    $zip.Dispose(); $zipStream.Dispose()
    $finalDocx = $tmpZip -replace '\.zip$', '.docx'
    Rename-Item -Path $tmpZip -NewName ([System.IO.Path]::GetFileName($finalDocx)) -Force
    if (Test-Path $docPath) { Remove-Item $docPath -Force }
    Move-Item -Path $finalDocx -Destination $docPath -Force
    $size = (Get-Item $docPath).Length
    Write-Output "SUCCESS: $docPath ($size bytes)"
} catch {
    Write-Output "ERROR: $_"
    if (Test-Path $tmpZip) { Remove-Item $tmpZip -Force }
    $finalDocx = $tmpZip -replace '\.zip$', '.docx'
    if (Test-Path $finalDocx) { Remove-Item $finalDocx -Force }
    exit 1
}
