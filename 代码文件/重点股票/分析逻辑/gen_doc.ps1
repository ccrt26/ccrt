# Generate 重点股票跟踪分析逻辑白皮书 v1.0.docx
# 遵循白皮书：重点股票跟踪分析逻辑白皮书 v2.0（§多周期预判、§证据加权、§操作建议体系）
# 注意：此脚本为遗留硬编码版本，后续修改请使用 build_docx.ps1 从 .md 生成
function New-KeystockDocBody {
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
        [void]$sb.Append('<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="9500" w:type="dxa"/><w:jc w:val="center"/></w:tblPr>')
        [void]$sb.Append('<w:tr><w:trPr><w:jc w:val="center"/></w:trPr>')
        foreach ($h in $hds) {
            [void]$sb.Append('<w:tc><w:tcPr><w:shd w:val="clear" w:color="auto" w:fill="1A1A2E"/><w:tcW w:w="' + [math]::Round(9500/$hds.Count) + '" w:type="dxa"/></w:tcPr><w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="18"/><w:b/><w:color w:val="FFFFFF"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape($h) + '</w:t></w:r></w:p></w:tc>')
        }
        [void]$sb.Append('</w:tr>')
        foreach ($row in $rows) {
            [void]$sb.Append('<w:tr><w:trPr><w:jc w:val="center"/></w:trPr>')
            foreach ($cell in $row) {
                [void]$sb.Append('<w:tc><w:tcPr><w:tcW w:w="' + [math]::Round(9500/$hds.Count) + '" w:type="dxa"/></w:tcPr><w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="18"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape($cell) + '</w:t></w:r></w:p></w:tc>')
            }
            [void]$sb.Append('</w:tr>')
        }
        [void]$sb.Append('</w:tbl>')
    }
    # ===== BUILD =====
    AddE $sb; AddE $sb; AddE $sb
    [void]$sb.Append('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="48"/><w:b/><w:color w:val="1A1A2E"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape("重点股票跟踪分析逻辑白皮书") + '</w:t></w:r></w:p>')
    AddE $sb
    [void]$sb.Append('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="36"/><w:b/><w:color w:val="16213E"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape("v1.2") + '</w:t></w:r></w:p>')
    AddE $sb
    [void]$sb.Append('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="22"/><w:color w:val="666666"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape("铁律量化 · 重点股票深度跟踪与多周期预判引擎") + '</w:t></w:r></w:p>')
    [void]$sb.Append('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="20"/><w:color w:val="666666"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape("版本：v1.2 | 2026-05-22 | 体系定位：对重点标的进行多层次、多维度、多周期的深度分析") + '</w:t></w:r></w:p>')
    AddE $sb; AddE $sb
    AddH $sb "版本历史" 1
    AddTbl $sb @("版本","日期","作者","变更内容","变更原因") @(
        ,@("v1.2","2026-05-22","Claude","基于30日walk-forward回测(180样本)优化:调整技术评分权重,移除短期看空(映射为中性),下调评级阈值80/65/45/30","回测验证:布林上轨触及有效性61.1%,缩量下跌反转60.5%,RSI超卖36.8%为反向信号;原阈值85/70/55/40评分区分度仅0.32%")
	        ,@("v1.1","2026-05-21","Claude","数据源合规审计整改:标注所有指标的数据源编号与实测状态;将不可获取指标降级为框架性参考;补充数据源引用","规则红线v1.1审计要求:所有指标必须有明确数据源,未实测的需标注待验证,不可获取的需明确降级")
        ,@("v1.0","2026-05-21","Claude","初始版。基于多周期多维度融合分析框架建立重点股票跟踪体系","需要独立的重点股票深度分析体系，与每日荐股的广度筛选形成互补")
    )
    # Chapter 1
    AddE $sb; AddH $sb "第一章 多维度分析框架" 1
    AddP $sb "重点股票分析从六个独立维度展开，每个维度输出独立的信号（看多/中性/看空），最终通过证据加权形成综合预判。"
    AddP $sb "技术面、基本面、消息面、板块行业、资金面、宏观 —— 六维融合，多周期共振。"
    AddP $sb "数据源合规：本文档所有指标已按《分析的规则红线 v1.1》§1.5完成合规审计，每个指标均标注数据源编号与实测状态。具体详见各章节标注。"
    AddH $sb "1.1 技术面分析" 2
    AddP $sb "技术面是判断买卖时机和趋势状态的核心手段，采用多周期趋势、量价关系、关键形态、指标组合四层递进。"
    AddH $sb "1.1.1 多周期趋势判断" 3
    AddTbl $sb @("周期","均线体系","趋势定义","用途") @(
        ,@("短期（日线）","MA5/MA10/MA20","MA5>MA10>MA20多头排列→短期上升趋势","入场/离场时机")
        ,@("中期（周线）","MA10/MA20/MA50","周线MA10>MA20且价格在MA20之上→中期上升趋势","持仓/方向判断")
        ,@("长期（月线）","MA20/MA50/MA120","月线级别均线多头→长期牛市格局","战略仓位判断")
    )
    AddBP $sb "趋势一致性原则：三个周期趋势方向一致时趋势强劲可重仓；短期与中长期方向相反按中长期方向定战略；中期趋势不明以区间震荡对待。"
    AddH $sb "1.1.2 量价关系分析（Wyckoff）" 3
    AddTbl $sb @("量价形态","含义","操作含义") @(
        ,@("价涨量增","需求旺盛，趋势健康","持仓或加仓")
        ,@("价涨量缩","上涨动力减弱，量价背离","警惕回调，减仓")
        ,@("价跌量缩","下跌无承接，但仍未企稳","观望，等待放量企稳")
        ,@("价跌量增","恐慌抛售或主力出货","区分是Selling Climax还是Distribution")
        ,@("放量突破压力位","Wyckoff的Sign of Strength(SOS)","确认突破有效，加仓")
        ,@("缩量回踩支撑位","Wyckoff的Last Point of Support(LPS)","最佳加仓点")
        ,@("放量跌破支撑位","趋势转弱","止损离场")
    )
    AddTbl $sb @("阶段","典型特征","操作策略") @(
        ,@("吸筹区(Accumulation)","长期下跌后横盘，成交量逐步放大，底部抬高","建立底仓")
        ,@("拉升区(Markup)","放量突破横盘区，均线多头排列","加仓/持仓")
        ,@("派发区(Distribution)","大幅上涨后横盘，高位放量滞涨，出现上冲回落的Upthrust","逐步减仓")
        ,@("下跌区(Markdown)","跌破派发区，均线空头排列","清仓/观望")
    )
    AddH $sb "1.1.3 经典技术形态识别" 3
    AddTbl $sb @("形态名称","周期","含义","目标位测算") @(
        ,@("头肩底/双底","日/周线","中期底部反转","颈线高度等距")
        ,@("头肩顶/双顶","日/周线","中期顶部反转","颈线高度等距")
        ,@("上升/下降旗形","日线","趋势中继","旗杆高度等距")
        ,@("上升/下降三角形","日/周线","趋势突破在即","三角形最宽处")
        ,@("圆弧底","周/月线","长期底部","缓慢，持久")
        ,@("W底/M顶","日/周线","常见反转形态","颈线高度等距")
    )
    AddH $sb "1.1.4 技术指标组合" 3
    AddP $sb "不依赖单一指标，采用组合确认策略。至少两个独立指标同时发出信号方可确认。"
    AddTbl $sb @("指标维度","指标","参数","用法") @(
        ,@("趋势","MACD(12,26,9)","标准参数","DIF方向+柱状体+零轴位置判断趋势强度")
        ,@("趋势","均线系统","5/10/20/50/120/250","多周期趋势状态")
        ,@("趋势","ADX(14)",">25趋势行情<20震荡","判断是否为趋势市")
        ,@("动量","RSI(14)","超买>70超卖<30；底背离/顶背离","短期反转信号")
        ,@("动量","Stochastic(14,3,3)","%K与%D交叉，超买/超卖区域","辅助RSI确认")
        ,@("动量","MFI(14)","带量的RSI，>80超买<20超卖","量价结合的动量判断")
        ,@("波动率","Bollinger Bands(20,2)","触及上下轨+带宽变化","超买超卖+突破确认")
        ,@("波动率","ATR(14)","衡量波动幅度，设置止损","动态止损参考")
        ,@("成交量","OBV","趋势确认，背离信号","量先行于价")
        ,@("成交量","成交量均线(5/20)","放量/缩量对照","量能变化")
    )
    AddBP $sb "组合确认规则："
    AddBP $sb "做多信号：均线多头+MACD零轴上方金叉/DIF向上+RSI 40-60区间向上+成交量配合"
    AddBP $sb "做空信号：均线空头+MACD零轴下方死叉/DIF向下+RSI 60-80区间向下+成交量配合"
    AddBP $sb "背离信号：价格新高但RSI/MACD未新高→顶背离(看空)；价格新低但RSI/MACD未新低→底背离(看多)"
    AddBP $sb "震荡判断：ADX<20+布林带走平+价格在上下轨之间来回→区间操作"
    AddH $sb "1.1.5 K线形态分析（辅助验证）" 3
    AddTbl $sb @("K线形态","含义","确认要求") @(
        ,@("十字星/纺锤线","多空平衡，变盘信号","次日方向确认")
        ,@("锤子线/上吊线","底部/顶部反转","长下影线+放量")
        ,@("吞没形态","强反转信号","实体完全覆盖前一根")
        ,@("晨星/暮星","底部/顶部反转","三根K线组合")
        ,@("三白兵/三黑鸦","持续/反转","三根连续同向")
    )
    AddH $sb "1.2 基本面分析" 2
    AddP $sb "基本面用于判断股票的内在价值和安全边际，决定中长期持仓的底气。"
    AddH $sb "1.2.1 财务健康评估" 3
    AddTbl $sb @("指标","计算方式","健康标准（A股）","用途") @(
        ,@("ROE","净利润/股东权益","≥15%优秀；≥10%合格","盈利能力的核心指标")
        ,@("毛利率","(营收-营业成本)/营收","≥30%优秀；≥20%合格","护城河与议价能力")
        ,@("净利润增长率","(本期净利润/上期净利润)-1","连续3年≥20%为成长股","成长性判断")
        ,@("营收增长率","(本期营收/上期营收)-1","≥15%","收入端扩张情况")
        ,@("资产负债率","总负债/总资产","≤50%稳健；≤30%优秀","财务风险")
        ,@("经营性现金流/净利润","经营活动现金流净额/净利润","≥1优秀；≥0.8合格","利润质量")
        ,@("存货周转率","营业成本/平均存货","行业对比","运营效率")
        ,@("PE百分位","当前PE/近5年PE区间","<30%低估>70%高估","估值位置")
        ,@("PEG","PE/净利润增速","<1为低估","成长性估值匹配")
    )
    AddH $sb "1.2.2 估值评估" 3
    AddTbl $sb @("估值方法","适用范围","判断标准") @(
        ,@("PE（市盈率）","盈利稳定的公司","与行业平均PE对比+历史百分位")
        ,@("PB（市净率）","金融/周期/重资产","破净<1为低估信号<0.8深度低估")
        ,@("PS（市销率）","亏损/高成长/互联网","行业对比")
        ,@("EV/EBITDA","跨行业比较","消除资本结构差异")
        ,@("DCF（现金流折现）","现金流稳定的成熟公司","内在价值vs当前市价")
        ,@("股息率","分红稳定的蓝筹","高于10年期国债收益率时具配置价值")
    )
    AddH $sb "1.2.3 核心竞争力分析" 3
    AddTbl $sb @("维度","评估内容","强度判断") @(
        ,@("护城河","品牌/专利/渠道/网络效应/成本优势","强/中/弱")
        ,@("行业地位","市占率排名、定价权","龙头/领先/跟随")
        ,@("技术壁垒","研发投入占比、专利数量","高/中/低")
        ,@("管理层","历史业绩、战略清晰度","优秀/合格/存疑")
    )
    AddH $sb "1.3 消息面与情绪面分析" 2
    AddP $sb "消息面决定短期股价的核心驱动力——炒股炒预期，预期靠消息催化。"
    AddH $sb "1.3.1 催化剂分级体系" 3
    AddTbl $sb @("级别","类型","影响周期","预期影响幅度") @(
        ,@("S级","业绩超预期/重磅政策/行业变革","1-6个月",">±20%")
        ,@("A级","大订单/重大合同/股权激励","1-4周","±10-20%")
        ,@("B级","新产品发布/合作签约/回购","3-10日","±5-10%")
        ,@("C级","行业新闻/分析师评级/传闻","1-3日","±3-5%")
    )
    AddH $sb "1.3.2 催化剂跟踪框架" 3
    AddP $sb "对每个重点股票维护一个催化剂日历，记录未来1个月的催化剂清单及其落地跟踪状态（待落地/已兑现/落空）。"
    AddH $sb "1.3.3 情绪面指标" 3
    AddTbl $sb @("情绪指标","数据来源","判断标准","合规状态") @(
        ,@("研报覆盖数","东方财富/同花顺[11]","近期密集覆盖→市场关注度提升","⚠️待验证")
        ,@("分析师评级变动","Wind/东财[11]","上调/下调数量对比","⚠️待验证")
        ,@("互动平台活跃度","上证e互动/深交所互动易","提问量激增→散户关注度高","❌框架性参考,无公开API")
        ,@("融资融券余额变化","交易所数据[12]","融资余额大幅增加→多头情绪","⚠️待验证")
        ,@("社交媒体热度","雪球/微博/股吧","热度异常→短期情绪拐点信号","❌框架性参考,无稳定API")
    )
    AddP $sb "合规说明:[11][12]尚未实测验证,输出时须标注待验证。互动平台和社交媒体两项无自动化数据源,仅作为分析框架参考,不参与自动评分计算。"
    AddH $sb "1.3.4 消息面验证规则" 3
    AddBP $sb "利多消息判断：消息真伪(官方公告>媒体报道>传闻)→是否Price In(公布前已大涨则利好出尽)→市场反应(首日涨幅+成交量)→位置判断(低位利好积极解读，高位利好警惕出货)"
    AddBP $sb "利空消息判断：实质性vs情绪性(业绩暴雷=实质，负面新闻=情绪)→是否过度反应(跌幅>预期可能超跌机会)→低位利空往往最后一跌，高位利空趋势可能转势"
    AddH $sb "1.4 板块与行业分析" 2
    AddP $sb "个股走势与板块高度相关——A股中约60%的个股日涨跌幅可由板块解释。选股必须先看板块。"
    AddH $sb "1.4.1 板块相位判断" 3
    AddTbl $sb @("相位","板块指数特征","对应操作") @(
        ,@("见底期","长期下跌后企稳，成交量开始放大，底部抬高","开始关注，选股纳入观察")
        ,@("启动期","板块放量突破下跌趋势线或横盘区，龙头股率先上涨","重点关注，可建仓")
        ,@("主升期","板块指数沿5/10周线上涨，成交量持续活跃，多只个股共振","加仓/持仓")
        ,@("高潮期","板块放巨量滞涨，上影线，波动加大，非龙头补涨","分批减仓")
        ,@("退潮期","板块跌破20周线，龙头股率先下跌，成交量萎缩","清仓回避")
    )
    AddH $sb "1.4.2 板块轮动位置" 3
    AddTbl $sb @("市场阶段","优势板块类型","避免板块","轮动速度") @(
        ,@("牛市初期","券商+金融+科技龙头","防御型板块","慢")
        ,@("牛市中期","成长+消费+赛道股","周期股","中")
        ,@("牛市末期","周期+补涨+小盘","高位白马","快")
        ,@("熊市初期","防御型(公用事业+消费)","高估值成长","快")
        ,@("熊市末期","超跌+政策受益","补跌股","慢")
    )
    AddH $sb "1.4.3 行业内个股联动分析" 3
    AddTbl $sb @("分析维度","方法","判断") @(
        ,@("龙头追踪","行业龙头走势vs目标股","龙头强+目标股强→板块健康；龙头弱+目标股强→个股独立行情")
        ,@("共振度","行业内上涨/下跌个股比例",">70%个股上涨→强共振趋势可靠")
        ,@("分化度","行业内涨幅标准差","标准差大→内部分化，选股能力重要")
        ,@("资金集中度","行业内前3大成交额占比","集中度高→资金聚焦少数龙头")
    )
    AddH $sb "1.5 资金面分析" 2
    AddP $sb "A股是资金驱动型市场，资金流向往往领先于价格变化。"
    AddH $sb "1.5.1 主力资金追踪" 3
    AddTbl $sb @("资金类型","数据来源","判断标准","合规状态") @(
        ,@("北向资金(沪/深股通)","交易所每日披露[8]","连续3日净流入→外资看好；单日超5亿净买入→强信号","⚠️待验证")
        ,@("主力净流入/出(超大单)","Level-2数据[9]","大单净买入占比>30%→主力介入；连续流出→主力出货","⚠️待验证")
        ,@("机构大宗交易","交易所披露","折价大宗→机构调仓；溢价大宗→抢筹","❌框架性参考，无免费API")
        ,@("行业资金流向","东方财富/同花顺[10]","行业整体资金流入/流出对比","⚠️待验证")
    )
    AddP $sb "合规说明：[8][9][10]尚未实测验证，输出时须标注待验证。机构大宗交易无自动化数据源，需人工录入交易所披露数据。"
    AddH $sb "1.5.2 市场成交量分析" 3
    AddTbl $sb @("量能状态","成交额特征","含义") @(
        ,@("放量上涨","成交额>5日均量2倍+涨幅>3%","增量资金入场，趋势可靠")
        ,@("缩量上涨","成交额<5日均量×0.7+上涨","存量博弈，上涨动力不足")
        ,@("放量下跌","成交额>5日均量2倍+跌幅>3%","恐慌抛售或主力出逃")
        ,@("缩量下跌","成交额<5日均量×0.7+下跌","下跌动能衰竭，可能见底")
        ,@("地量","成交额创近30日新低","市场关注度极低，变盘前兆")
    )
    AddH $sb "1.5.3 筹码分布分析" 3
    AddP $sb "筹码分布数据需要付费Level-2行情接口，当前无免费API可获取。本节所有分析为框架性参考，不参与自动评分计算，仅供人工分析时参考。"
    AddTbl $sb @("筹码特征","含义","操作含义") @(
        ,@("高位套牢盘密集(>30%筹码在现价上方20%内)","上方抛压较大","突破前需充分洗盘")
        ,@("低位筹码密集峰支撑","成本集中，有支撑","回调至密集峰上沿可买入")
        ,@("获利比例>80%且换手率<3%","持股集中度提升","主力锁仓，可能加速上涨")
        ,@("获利比例<20%","深度套牢","抛压小但需等主力进场")
    )
    # Chapter 2
    AddE $sb; AddH $sb "第二章 三周期预判体系" 1
    AddP $sb "对每个重点股票，必须同时给出短期/中期/长期三个时间维度的预判，形成完整的趋势意见书。"
    AddH $sb "2.1 短期预判（1-5个交易日）" 2
    AddTbl $sb @("分析依据","权重","关键信号") @(
        ,@("日线级别技术形态","35%","K线组合+支撑/阻力位+日内量价关系")
        ,@("短期均线排列(5/10/20)","20%","多头/空头/纠缠")
        ,@("短期技术指标(RSI/Stoch/布林带)","15%","超买超卖+交叉信号")
        ,@("近3日消息面催化","15%","是否有近期催化剂将落地")
        ,@("次日大盘预期","15%","大盘短期方向影响个股")
    )
    AddBP $sb "短期预判输出格式：方向(看多/偏多/中性/偏空)(v1.2起看空不再直接输出——回测验证看空方向胜率仅20%,已映射为中性) 关键阻力位 关键支撑位 短期催化剂 置信度(高>70%/中50-70%/低<50%)"
    AddH $sb "2.2 中期预判（1-4周）" 2
    AddTbl $sb @("分析依据","权重","关键信号") @(
        ,@("周线级别趋势","30%","周线均线排列+周线MACD方向")
        ,@("板块相位与轮动","20%","板块所处生命周期阶段")
        ,@("中期催化剂","20%","未来1-4周内确定性催化事件")
        ,@("基本面趋势","15%","业绩预期+估值水平")
        ,@("资金面中期趋势","15%","北向资金/主力资金连续方向")
    )
    AddBP $sb "中期预判输出格式：方向(趋势看多/区间震荡/趋势看空) 目标区间(上沿/下沿) 关键验证点 中期催化剂"
    AddH $sb "2.3 长期预判（1-6个月）" 2
    AddTbl $sb @("分析依据","权重","关键信号") @(
        ,@("基本面价值评估","30%","ROE趋势+营收增速+估值百分位")
        ,@("行业/产业趋势","25%","渗透率+替代率+市占率(三率体系)")
        ,@("月线级别大趋势","20%","月线均线+长期技术形态(Wyckoff大周期位置)")
        ,@("宏观政策方向","15%","政策受益/受损判断")
        ,@("机构共识","10%","分析师目标价+机构持仓变化趋势")
    )
    AddBP $sb "长期预判输出格式：方向(长期看好/中性/看空) Wyckoff周期阶段 合理估值区间 核心逻辑"
    AddH $sb "2.4 三周期综合判断矩阵" 2
    AddTbl $sb @("短期","中期","长期","综合判断","建议操作") @(
        ,@("↑","↑","↑","强势看多","重仓持有，每次回调都是加仓点")
        ,@("↑","↑","→","谨慎看多","持仓，关注长期逻辑是否强化")
        ,@("↑","→","↑","短期机会","可在支撑位做多，注意中期风险")
        ,@("↑","↓","↑","反弹看待","仅做短线，中期压力大")
        ,@("→","↑","↑","等待买点","中期趋势好，等短期回调企稳介入")
        ,@("↓","↑","↑","中期趋势中的回调","重点观察是否是健康的缩量回调")
        ,@("↓","↓","↑","中期调整","减仓，等中期趋势明朗再回补")
        ,@("↓","↓","↓","强势看空","清仓回避，等待反转信号")
        ,@("↑","↓","↓","超跌反弹","仅做短线反弹，快进快出")
        ,@("→","→","→","方向不明","观望，减少交易")
    )
    AddP $sb "↑=看多 →=中性/震荡 ↓=看空"
    # Chapter 3
    AddE $sb; AddH $sb "第三章 综合评分与评级体系" 1
    AddH $sb "3.1 六维评分" 2
    AddP $sb "对每个重点股票，从六个维度分别打分（0-100分），汇总形成综合评分。"
    AddTbl $sb @("维度","权重","数据源","高分标准(≥70分)","低分信号(≤40分)") @(
        ,@("技术面","25%","[2]→[5] ✅已实测","多周期均线多头+量价配合+指标组合看多","均线空头+量价背离+指标组合看空")
        ,@("基本面","20%","[3]→[5] ✅已实测","ROE≥15%+营收增速≥15%+PE百分位<50%","ROE<8%+营收负增长+PE百分位>80%")
        ,@("消息面","15%","[11] ⚠️待验证+AI定性","有S/A级催化剂即将落地","无催化剂+或有利空未消化")
        ,@("板块行业","20%","[7] ⚠️待验证+AI定性","板块处于启动/主升期+资金流入","板块处于退潮期+资金流出")
        ,@("资金面","15%","[8][9][10] ⚠️待验证","主力连续净流入+量能配合","主力连续流出+缩量")
        ,@("宏观/大盘","5%","[7] ⚠️待验证+AI定性","大盘处于上升趋势+流动性宽松","大盘下跌+流动性收紧")
    )
    AddH $sb "3.1.1 综合评级" 3
    AddTbl $sb @("综合评分","评级","含义") @(
        ,@("≥80","★★★★ 强烈关注","多维度共振看多，适合重点配置")
        ,@("65-79","★★★ 关注","整体偏多，可以在回调时介入")
        ,@("45-64","★★ 观察","多空因素均衡，维持观察")
        ,@("30-44","★ 谨慎","偏空因素占优，仓位需控制")
        ,@("<30","☆ 回避","多维度看空，避免介入")
    )
    AddH $sb "3.2 趋势健康度评估" 2
    AddP $sb "追踪趋势的持续性和健康度，防止过早下车或该走不走。"
    AddTbl $sb @("指标","健康","预警","危险") @(
        ,@("上升趋势中的回调幅度","<10%","10-15%",">15%")
        ,@("上升中的成交量","量增","缩量上涨","放量滞涨/放量下跌")
        ,@("均线发散状态","多头平行向上","均线开始走平","死叉/交叉向下")
        ,@("MACD状态","DIF在零轴上方+柱状体向上","DIF走平","DIF下穿零轴")
        ,@("RSI趋势","50-70之间震荡向上","70以上钝化","跌破50")
        ,@("板块相对强度","强于大盘","与大盘同步","弱于大盘")
    )
    AddBP $sb "趋势健康度评分触发规则：≥80正常持有 → 60-79关注预警设定止损 → 40-59进入警戒准备减仓 → <40立即评估是否需要清仓"
    # Chapter 4
    AddE $sb; AddH $sb "第四章 跟踪与更新机制" 1
    AddH $sb "4.1 重点股票档案结构" 2
    AddP $sb "每个重点股票建立独立档案，包含：基础信息(行业/板块/市值/股价/评分)、多维分析摘要(技术/基本面/消息面/板块/资金面)、三周期预判(短/中/长期方向与关键价位)、跟踪日志(按时间倒序)、历史预判回溯(对错归因)。"
    AddH $sb "4.2 更新频率" 2
    AddTbl $sb @("事件类型","更新频率","更新内容") @(
        ,@("每日例行","每个交易日收盘后","检查技术信号变化、消息面、板块动态")
        ,@("关键价位触发","即时","股价触及支撑/阻力/止损位时重新评估")
        ,@("催化事件前后","事件前1日+事件后1日","更新催化剂预期/落地情况")
        ,@("财报发布","发布后24小时内","全面更新基本面评估")
        ,@("板块重大变化","即时","板块相位变更、行业政策变化")
        ,@("完整复盘","每周","更新综合评分、三周期预判、趋势健康度")
    )
    AddH $sb "4.3 重点股票池管理" 2
    AddTbl $sb @("池级别","入选条件","最多数量","更新频率") @(
        ,@("核心观察池","综合评分≥70或有S级催化即将落地","10只","每日")
        ,@("跟踪池","综合评分55-69或有A级催化","20只","每周2次")
        ,@("雷达池","综合评分40-54但基本面优秀","30只","每周1次")
    )
    AddH $sb "4.4 退出机制" 2
    AddTbl $sb @("退出条件","操作","是否可重新进入") @(
        ,@("综合评分<40连续5日","移出核心观察池","评分回升至≥55后可重新进入")
        ,@("三周期预判均转为看空","清仓并移出所有池","至少等待1个月后重新评估")
        ,@("基本面恶化(ROE连续2季下滑)","移除跟踪/雷达池","基本面企稳后可重新评估")
        ,@("触发止损","执行止损","重新形成底部结构后可再评估")
    )
    # Chapter 5
    AddE $sb; AddH $sb "第五章 数据存储与版本管理" 1
    AddH $sb "5.1 文件结构" 2
    AddP $sb "重点股票目录结构：分析逻辑(白皮书MD/DOCX+CHANGELOG+gen_doc.ps1) → 股票档案(每只重点股票独立MD文件) → 预判记录(predictions.csv) → 汇总(weekly_review周复盘)"
    AddH $sb "5.2 版本管理" 2
    AddTbl $sb @("变更类型","版本号","审核要求") @(
        ,@("分析框架微调(指标参数、阈值)","不升版本","AI自动")
        ,@("新增/移除分析维度","v1.x→v1.(x+1)","人工确认")
        ,@("分析体系重构","v1.x→v2.0","人工审核")
    )
    AddH $sb "5.3 同步更新要求" 2
    AddBP $sb "每次版本变更时同步更新：1) CHANGELOG.md  2) 文档版本索引.md"
    # Appendix A
    AddE $sb; AddH $sb "附录A：分析流程速查卡" 1
    AddBP $sb "重点股票分析每日流程："
    AddBP $sb "1. 检查技术面(5分钟)：查看日/周/月线趋势(均线排列)→检查MACD/RSI/布林带状态→识别K线形态→判断量价关系是否健康"
    AddBP $sb "2. 检查消息面(3分钟)：搜索近3日相关新闻→检查互动平台提问→查看分析师评级变动"
    AddBP $sb "3. 检查板块/行业(2分钟)：板块指数走势→行业内龙头股表现"
    AddBP $sb "4. 更新预判(2分钟)：三周期方向是否有变化→关键价位是否需调整→综合评分是否需修正"
    # Appendix B
    AddE $sb; AddH $sb "附录B：关键术语表" 1
    AddTbl $sb @("术语","解释") @(
        ,@("Wyckoff吸筹","主力在低位通过震荡建仓的过程，特征为底部抬高+量能放大")
        ,@("Selling Climax","下跌末期放量暴跌，意味着最后一批恐慌盘出逃")
        ,@("Sign of Strength(SOS)","强势信号——放量上涨突破关键阻力")
        ,@("Last Point of Support(LPS)","最佳买点——缩量回踩支撑后企稳")
        ,@("Upthrust(UTAD)","冲高回落——突破阻力后立即反转，主力出货信号")
        ,@("证据加权","多个独立维度发出相同信号时才形成结论")
        ,@("板块相位","板块所处生命周期阶段(见底/启动/主升/高潮/退潮)")
        ,@("三率体系","渗透率(产业生命周期)、替代率(全球竞争力)、市占率(竞争格局)")
        ,@("三周期预判","短期1-5日/中期1-4周/长期1-6月的趋势方向判断")
        ,@("六维评分","技术/基本面/消息面/板块行业/资金面/宏观六维度加权评分系统")
    )
    # Footer
    AddE $sb; AddE $sb
    [void]$sb.Append('<w:p><w:pPr><w:pBdr><w:top w:val="single" w:sz="6" w:space="4" w:color="CCCCCC"/></w:pBdr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="18"/><w:color w:val="999999"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape("本分析体系为铁律量化选股系统的深度分析配套文档。与《每日荐股分析逻辑白皮书》的广度筛选形成互补——广度找机会，深度做判断。") + '</w:t></w:r></w:p>')
    [void]$sb.Append('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="18"/><w:color w:val="999999"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape("版本：v1.2 | 2026-05-22 | 铁律量化") + '</w:t></w:r></w:p>')
    return $sb.ToString()
}
# Main
$docPath = [System.IO.Path]::GetFullPath("Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))\重点股票\分析逻辑\重点股票跟踪分析逻辑白皮书_v1.2.docx")
$tmpZip = [System.IO.Path]::GetTempFileName() + ".zip"
$bodyContent = New-KeystockDocBody
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

