# Generate 次日后评估白皮书 v1.3.docx
# 遵循白皮书：次日后评估白皮书 v1.5（§模拟交易、§归因分析、§误判分类）
# 注意：此脚本为遗留硬编码版本，后续修改请使用 build_docx.ps1 从 .md 生成
function New-EvalDocBody {
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
    [void]$sb.Append('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="48"/><w:b/><w:color w:val="1A1A2E"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape("次日后评估白皮书") + '</w:t></w:r></w:p>')
    AddE $sb
    [void]$sb.Append('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="36"/><w:b/><w:color w:val="16213E"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape("v1.3") + '</w:t></w:r></w:p>')
    AddE $sb
    [void]$sb.Append('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="22"/><w:color w:val="666666"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape("铁律量化 · 次日归因与反馈引擎 · 自我迭代") + '</w:t></w:r></w:p>')
    [void]$sb.Append('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="20"/><w:color w:val="666666"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape("版本：v1.3 | 2026-05-22 | 调度：N日20:00分析→N+1日19:00评估→20:00新版分析") + '</w:t></w:r></w:p>')
    AddE $sb; AddE $sb
    AddH $sb "版本历史" 1
    AddTbl $sb @("版本","日期","作者","变更内容","变更原因") @(
        ,@("v1.3","2026-05-22","Claude","新增第7.4节外部知识融合（月度搜索+对比融合）","评估体系需要外部知识输入，避免闭门造车")
        ,@("v1.2","2026-05-21","Claude","新增误判子类型分拆（3.4节）；新增对照组评估（4.4节）；新增自动化回测引擎（5.5节）；更新优化决策流程（7.1节新增自我迭代触发项）","评估体系需要自我迭代能力，不能只评估推荐结果而不评估评估方法本身")
        ,@("v1.1","2026-05-21","Claude","对齐自动化调度时间线；新增评估报告命名规范；明确自动优化流程","配合 daily_workflow.ps1 定时调度框架，确保评估→优化→新版本分析无缝衔接")
        ,@("v1.0","2026-05-21","Claude","初始版。基于评估白皮书v1.2重构，聚焦次日归因闭环","评估v1.2缺少从评估到逻辑优化的直接反馈链路")
    )
    # Chapter 1
    AddE $sb; AddH $sb "第一章 评估体系总纲" 1
    AddH $sb "1.1 核心定位" 2
    AddP $sb "次日后评估是"评分质量检验+规则有效性验证+逻辑迭代驱动"三位一体的优化引擎，兼具自我迭代能力（v1.3）。评估结果直接驱动逻辑白皮书参数迭代与评估体系自身的信号优化。"
    AddH $sb "1.2 核心指标" 2
    AddTbl $sb @("指标","公式","目标","说明") @(
        ,@("次日胜率","盈利次数/总推荐次数","≥60%","按T+1收盘价计，含滑点")
        ,@("次日盈亏比","总盈利/总亏损","≥1.5:1","含次数权重")
        ,@("组合次日收益","Σ收益率/推荐只数",">0%","等权组合视角")
        ,@("超额收益","组合收益-沪深300",">0%","跑赢大盘")
        ,@("评分区分度","≥70分组vs<70分组胜率差","≥15%","高分股确实更好")
        ,@("维度误判率","某维度高分但亏损>3%次数/高分总次数","≤20%","识别评分偏差")
        ,@("否决误杀率","被否股次日涨>5%只数/被否总只数","≤15%","否决是否过严")
        ,@("豁免成功率","豁免股盈利比例","≥65%","豁免条件是否有效")
    )
    AddH $sb "1.3 自动化调度时间线" 2
    AddTbl $sb @("时间","任务","模式","开盘检查") @(
        ,@("N日 20:00","每日荐股分析","daily","✅")
        ,@("N+1日 19:00","次日后评估","eval","✅")
        ,@("N+1日 20:00","每日荐股分析(新版)","daily_latest","✅")
    )
    AddP $sb "每个任务内建开盘判断(is_market_open.ps1)，非交易日自动跳过。评估完成后自动优化白皮书，1小时后(20:00)新版分析使用优化后参数。"
    AddH $sb "1.4 评估报告命名规范" 2
    AddP $sb "评估报告统一命名为 评估报告_YYYYMMDD.docx，其中YYYYMMDD为被评估的荐股日期(N日)。存储于事后评估目录。"
    # Chapter 2
    AddE $sb; AddH $sb "第二章 次日数据采集与比对" 1
    AddH $sb "2.1 数据获取" 2
    AddTbl $sb @("数据项","来源","用途") @(
        ,@("T日推荐列表","T日荐股报告","评估对象")
        ,@("T日评分明细","评分系统输出","归因基准")
        ,@("T+1日开盘价","腾讯行情[1]","模拟买入价")
        ,@("T+1日收盘价","腾讯行情[1]","模拟卖出价")
        ,@("T+1日最高/最低价","腾讯行情[1]","止损触发判断")
        ,@("T+1日成交量/换手率","腾讯行情[1]","量能验证")
        ,@("T+1日沪深300涨跌","腾讯行情[1]","大盘对照")
        ,@("T+1日板块指数","东方财富","板块验证")
    )
    AddH $sb "2.2 模拟交易计算" 2
    AddBP $sb "买入：正常开盘→开盘价×1.005(含0.5%滑点)。一字涨停→标记无法成交。开盘跌>3%→标记异常。"
    AddBP $sb "卖出(优先级)：1)止损触发→触发价卖出(止损价=买入价-2×ATR(14)，上限-8%)；2)盈利>10%后收盘破MA5→次日开盘卖出；3)大盘跌>3%→当日收盘卖出；4)均未触发→T+1日收盘价卖出。"
    # Chapter 3
    AddE $sb; AddH $sb "第三章 评分维度回检" 1
    AddH $sb "3.1 维度误判率" 2
    AddP $sb "维度误判率=某维度给高分(高于满分60%)且亏损>3%次数/该维度高分总次数"
    AddTbl $sb @("误判率","判定","操作") @(
        ,@("≤10%","优秀","维持权重"),@("10-20%","正常","关注趋势"),@("20-30%","偏高","连续5日超20%→触发维度重构"),@(">30%","失效","立即暂停维度")
    )
    AddH $sb "3.2 误判类型标记" 2
    AddTbl $sb @("误判维度","标记","典型场景") @(
        ,@("技术面","TECH_MISJUDGE","均线多头但破位"),@("资金面","MONEY_MISJUDGE","资金流入但主力出货"),@("板块面","SECTOR_MISJUDGE","判断潜伏但板块大跌"),@("消息面","NEWS_MISJUDGE","催化预期落空")
    )
    AddH $sb "3.3 相关系数(周更)" 2
    AddP $sb "每周计算各维度评分与次日涨跌幅的Spearman相关系数。ρ>0.3有效→权重上调；0.1-0.3弱相关→维持；<0.1无预测力→重构；<0反向指标→立即暂停。"
    AddH $sb "3.4 误判子类型分析(v1.2新增)" 2
    AddP $sb "核心思路：同一维度内不同误判原因命中率差异很大，只有拆到子类型级别才能精准关闭失效信号。亏损>3%时需同时标注维度级和子类型级误判标记。"
    AddTbl $sb @("维度级","子类型","标记","典型场景") @(
        ,@("技术面","均线多头假突破","TECH_FAKE_BREAK","均线刚多头次日破位")
        ,@("技术面","量价背离","TECH_DIVERGENCE","放量不涨/缩量上涨")
        ,@("技术面","RSI钝化","TECH_RSI_BLUNT","RSI>60钝化后回落")
        ,@("技术面","MACD假金叉","TECH_FAKE_GOLDEN","DIF上穿DEA后立即死叉")
        ,@("资金面","主力假流入","MONEY_FAKE_INFLOW","大单净买但小单净卖更大")
        ,@("资金面","尾盘拉升出货","MONEY_CLOSE_PUMP","收盘前拉升但全天净流出")
        ,@("板块面","潜伏期误判","SECTOR_EARLY_MISS","判断潜伏实际仍在下跌")
        ,@("板块面","启动期夭折","SECTOR_ABORT","启动后立即回调")
        ,@("消息面","催化落空","NEWS_FAIL","催化剂取消或远低于预期")
    )
    AddP $sb "子类型命中率=该子类型标记次数/对应评分信号出现总次数。≤10%维持，10-20%观察，20-30%信号降权50%，>30%立即暂停。被暂停的信号在后续30日命中率降至≤15%后可自动恢复。"
    # Chapter 4
    AddE $sb; AddH $sb "第四章 规则有效性诊断" 1
    AddH $sb "4.1 否决规则验证" 2
    AddP $sb "绝对否决误杀率=被否决但次日涨>5%只数/被否决总只数。目标≤5%，连续3日>5%审查阈值。条件否决：记录被条件否决标的次日表现，否决平均涨幅vs推荐平均涨幅，差值>3%说明阈值过严。"
    AddH $sb "4.2 趋势豁免评估" 2
    AddP $sb "豁免组胜率≥65%有效；<50%失效；连续3天低于非豁免组10%→暂停豁免功能。"
    AddH $sb "4.3 分市场阶段分析" 2
    AddP $sb "按牛/震荡/熊三阶段拆分胜率，识别评分体系在不同市场环境下的表现差异。"
    AddH $sb "4.4 对照组评估(v1.2新增)" 2
    AddP $sb "每日同时评估三组：推荐池(期望≥60%)、被否决池(期望≤40%)、全市场基准(≈50%)。"
    AddTbl $sb @("指标","公式","目标","预警值") @(
        ,@("否决有效度","推荐胜率-否决池胜率","≥20%","<10%连续5日")
        ,@("评分区分度","推荐胜率-全市场胜率","≥10%","<5%连续5日")
        ,@("否决误杀率","否决池涨>5%占比","≤15%",">15%连续3日")
    )
    AddP $sb "否决有效度<10%→暂停区分度最低的否决条件。评分区分度<5%→全面审查六维评分。否决池跑赢推荐池→立即暂停所有否决条件。"
    # Chapter 5
    AddE $sb; AddH $sb "第五章 逻辑迭代引擎" 1
    AddH $sb "5.1 参数映射表" 2
    AddTbl $sb @("逻辑参数","监控指标","调整规则") @(
        ,@("推荐阈值(牛70/震65/熊60)","70-79分段胜率","连续5日<55%→+3；>75%→-3")
        ,@("涨幅否决阈值","被否决股后续表现","误杀率>5%→放宽10%")
        ,@("PE否决阈值(科技80/消费50/金融15)","PE否决误杀率","误杀率>5%→行业阈值+10")
        ,@("ATR止损倍数(牛2.5/震2.0/熊1.5)","止损触发率","触发率>40%→扩大倍数")
        ,@("量比封顶阈值(当前12)","封顶误杀率","误杀≥2只/天连3天→上调至15/20")
        ,@("均线收敛间距(<1%)","方向正确率","<60%→放宽至<2%")
        ,@("连续流入天数(3/5日)","资金面评分胜率","<50%→缩短天数")
    )
    AddH $sb "5.2 版本升级决策树" 2
    AddBP $sb "参数微调(不升版本)：单阈值调整≤10%，不改变评分逻辑结构，连续5日以上数据支撑。AI自动执行。"
    AddBP $sb "次版本升级(v1.x→v1.x+1)：AI提建议人工确认。触发：维度误判率>20%连续5日/评分区分度<10%连续5日/胜率<50%连续一周。"
    AddBP $sb "主版本升级(v1.x→v2.0)：必须人工审核。触发：月度胜率<45%/多维度同时失效/市场结构变化。"
    AddH $sb "5.3 灰度测试" 2
    AddTbl $sb @("阶段","时长","操作","切换条件") @(
        ,@("并行运行","5个交易日","新旧规则同时评分","-")
        ,@("数据对比","第6日","对比新旧规则胜率","新规则≥旧规则+5%")
        ,@("正式切换","对比次日","旧规则下线","人工确认")
        ,@("跟踪确认","切换后10日","监控新规则胜率","无明显下降")
    )
    AddH $sb "5.4 自动化回测引擎(v1.2新增)" 2
    AddP $sb "每次参数修改前先用历史数据验证。回测流程：加载历史数据→用新参数重新评分→对比新旧参数结果→输出回测报告。"
    AddP $sb "可回测参数：PE否决阈值、涨幅否决阈值、ATR止损倍数、量比封顶阈值、均线收敛间距、连续流入天数、子类型信号权重。"
    AddP $sb "自动触发条件：维度误判率>20%连3日自动回测子信号权重调整、否决有效度<10%连3日自动回测否决阈值、子类型命中率>30%自动回测剔除效果、每月1日全参数回测扫描。"
    AddP $sb "每次回测生成回测记录(backtest_log.csv)，包含参数名称、新旧值、回测胜率对比、提升幅度。没有回测数据的参数变更不被允许。"
    # Chapter 6
    AddE $sb; AddH $sb "第六章 数据存储与版本管理" 1
    AddH $sb "6.1 评估记录" 2
    AddP $sb "records.csv: 逐日评估明细(股票/评分/买入价/卖出价/收益率/误判维度/误判子类型/否决类型等)"
    AddP $sb "summary.csv: 按周/月汇总(胜率/盈亏比/超额收益/各维度误判率/否决有效度/评分区分度)"
    AddP $sb "issues.csv: 问题跟踪(描述/严重程度/优先级/状态/验证结果)"
    AddP $sb "backtest_log.csv: 回测记录(参数名称/新旧值/数据范围/胜率对比/提升幅度/采纳状态)"
    AddH $sb "6.2 数据积累里程碑" 2
    AddTbl $sb @("时段","最少数据量","可执行分析") @(
        ,@("第1周","≥15条","基础胜率统计")
        ,@("第1个月","≥60条","维度相关性分析")
        ,@("第2个月","≥120条","否决条件定量优化")
        ,@("第3个月","≥180条","权重调整+子类型命中率稳定")
        ,@("第6个月","≥360条","分市场阶段最优参数组合")
    )
    # Chapter 7
    AddE $sb; AddH $sb "第七章 优化决策流程" 1
    AddH $sb "7.1 触发条件" 2
    AddTbl $sb @("触发条件","判定标准","响应动作") @(
        ,@("胜率警告","连续2周<40%","暂停策略全面排查")
        ,@("回撤警告","单周组合<-10%","暂停策略全面排查")
        ,@("维度失效","误判率>20%连续3天","触发维度重构")
        ,@("否决有效度低","有效度<10%连续5日","暂停区分度最低否决条件")
        ,@("评分区分度低","区分度<5%连续5日","全面审查相关系数")
        ,@("子类型命中率偏高","命中率>20%连续5日","信号降权50%")
        ,@("子类型命中率失效","命中率>30%","立即暂停该信号")
        ,@("否决池跑赢推荐池","否决有效度为负","暂停所有否决条件逐一回测")
        ,@("全参数回测","每月1日","对所有可调参数执行回测扫描")
        ,@("月度体检","月度胜率<50%","全面审视")
    )
    AddH $sb "7.2 假设-验证-切换流程" 2
    AddP $sb "Step1假设→Step2回测(≥10日历史)→Step3灰度(新旧并行1周)→Step4切换(胜率提升≥5%且盈亏比不降)→Step5跟踪(切换后2周确认)。异常回滚：新规则胜率低于旧规则→回退参数重新分析。"
    AddH $sb "7.4 外部知识融合（月度大循环）" 2
    AddP $sb "核心思路：当前评估体系的自我迭代完全依赖内部数据，月度外部知识融合打破这个闭环，主动获取外部知识。每月初搜索业界新方法，与当前体系对比融合。外部调研结果直接输入§7.2 Step1「假设」环节。"
    AddH $sb "7.4.1 搜索策略" 3
    AddP $sb "中文：A股短线技术指标有效性实证、量化选股因子衰减T+1研究、资金流向量价分析预测能力、止损策略最优参数回测对比、评分模型区分度检验方法。英文：short-term signal effectiveness A-share, technical indicator predictive power China, factor decay short-term quantitative trading."
    AddH $sb "7.4.2 融合流程" 3
    AddP $sb "搜索→阅读摘要→对比当前体系→生成采纳建议→记录到外部知识调研日志。每种发现包含核心发现、与当前体系差异、适用性评估、对接环节、采纳建议。"
    AddH $sb "7.4.3 与内部评估的协作关系" 3
    AddP $sb "外部方法→回测验证(§5.5)→灰度测试(§5.3)→正式切换。新方法进入候选信号列表等待内部数据验证；参数优化方向直接回测验证；已在用的方法记录无需变更；冲突方法设计对照实验验证。"
    AddH $sb "7.4.4 调度与存储" 3
    AddP $sb "通过定时任务每月1日触发，与重点股票后评估系统共用月度调研任务。调研记录追加写入逻辑积累\元评估\外部知识调研日志.md。外部方法经初步评估后进入候选信号.json。"
    # Footer
    AddE $sb; AddE $sb
    [void]$sb.Append('<w:p><w:pPr><w:pBdr><w:top w:val="single" w:sz="6" w:space="4" w:color="CCCCCC"/></w:pBdr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="18"/><w:color w:val="999999"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape("本评估体系为铁律量化选股系统配套文档。所有优化决策必须有数据支撑。") + '</w:t></w:r></w:p>')
    [void]$sb.Append('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="18"/><w:color w:val="999999"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape("版本：v1.3 | 2026-05-22 | 铁律量化") + '</w:t></w:r></w:p>')
    return $sb.ToString()
}
# Main
$docPath = [System.IO.Path]::GetFullPath("Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))\每日荐股\事后评估\次日后评估白皮书_v1.3.docx")
$tmpZip = [System.IO.Path]::GetTempFileName() + ".zip"
$bodyContent = New-EvalDocBody
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