# Generate 次日后评估白皮书 v1.5.docx
# 遵循白皮书：次日后评估白皮书 v1.5（§模拟交易、§归因分析、§误判分类）
# 注意：此脚本为遗留硬编码版本，后续修改请使用 build_docx.ps1 从 .md 生成
function New-EvalDocBody {
    $sb = New-Object System.Text.StringBuilder
    function AddH($sb, $text, $lvl) {
        $sid = if ($lvl -eq 1) { "Heading1" } elseif ($lvl -eq 2) { "Heading2" } else { "Heading3" }
        $sz = @{1="36";2="28";3="24"}[$lvl]; $clr = @{1="1A1A2E";2="16213E";3="333333"}[$lvl]
        [void]$sb.Append('<w:p><w:pPr><w:pStyle w:val="' + $sid + '"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="' + $sz + '"/><w:b/><w:color w:val="' + $clr + '"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape($text) + '</w:t></w:r></w:p>')
    }
    function AddP($sb, $t) { [void]$sb.Append('<w:p><w:pPr><w:spacing w:line="360" w:lineRule="auto"/><w:jc w:val="both"/><w:ind w:firstLine="420"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="22"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape($t) + '</w:t></w:r></w:p>') }
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
    [void]$sb.Append('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="36"/><w:b/><w:color w:val="16213E"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape("v1.5") + '</w:t></w:r></w:p>')
    AddE $sb
    [void]$sb.Append('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="22"/><w:color w:val="666666"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape("铁律量化 · 次日归因与反馈引擎 · 自我迭代") + '</w:t></w:r></w:p>')
    [void]$sb.Append('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="20"/><w:color w:val="666666"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape("版本：v1.5 | 2026-05-22 | 调度：N日20:00分析→N+1日19:00评估→20:00新版分析") + '</w:t></w:r></w:p>')
    [void]$sb.Append('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="20"/><w:color w:val="666666"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape("核心升级：首次实战回检修复——维度误判率改用大盘环境动态基线，评分区分度新增相对排名法") + '</w:t></w:r></w:p>')
    AddE $sb; AddE $sb
    AddH $sb "版本历史" 1
    AddTbl $sb @("版本","日期","作者","变更内容","变更原因") @(
        ,@("v1.5","2026-05-22","Claude","首次实战回检修复：维度误判率动态基线、评分区分度相对排名、数据源补充、拥挤度分位阈值、路径6特征、日内止损、5日滚动窗口","首次实战执行v1.4框架发现强势市场日维度误判率完全失效等14个问题")
        ,@("v1.4","2026-05-22","Claude","首次月度外部知识融合：新增3项评估指标、场景化回检、更新外部调研记录","落实v1.3月度外部知识融合机制")
        ,@("v1.3","2026-05-22","Claude","新增外部知识融合（月度搜索+对比融合）","评估体系需要外部知识输入")
        ,@("v1.2","2026-05-21","Claude","误判子类型分拆、对照组评估、自动化回测引擎","评估体系需要自我迭代能力")
        ,@("v1.1","2026-05-21","Claude","对齐自动化调度时间线、评估报告命名规范","配合 daily_workflow.ps1 定时调度")
        ,@("v1.0","2026-05-21","Claude","初始版，聚焦次日归因闭环","评估v1.2缺少评估到逻辑优化的反馈链路")
    )
    # Chapter 1
    AddE $sb; AddH $sb "一、评估体系总纲" 1
    AddH $sb "（一）核心定位" 2
    AddP $sb "次日后评估是「评分质量检验 + 规则有效性验证 + 逻辑迭代驱动」三位一体的优化引擎。形成N日20:00分析→N+1日15:00收盘→N+1日19:00评估→N+1日20:00新版分析的完整闭环。评估结果驱动逻辑白皮书参数迭代，最终目标是将评估发现转化为可执行的参数修改建议。"
    AddH $sb "（二）核心指标" 2
    AddTbl $sb @("指标","目标","说明") @(
        ,@("次日胜率","≥60%","按T+1收盘价计，含滑点")
        ,@("次日盈亏比","≥1.5:1","含次数权重")
        ,@("组合次日收益",">0%","等权组合视角")
        ,@("超额收益",">0%","跑赢大盘")
        ,@("评分区分度","≥15%","高分股确实比低分股好")
        ,@("评分区分度（相对排名）",">0.2","Spearman相关，去除市场beta")
        ,@("维度误判率","≤20%","视大盘环境动态调整基线")
        ,@("否决误杀率","≤15%","否决是否过严")
        ,@("豁免成功率","≥65%","豁免条件是否有效")
        ,@("拥挤度预警有效性","≥60%","高换手拥挤标记有效性")
        ,@("路径优选有效性","≥15%","各路径胜率差异")
    )
    AddP $sb "大盘环境归因：所有指标附带当日大盘状态标记（强势/正常/弱势）。强势市场日（全市场平均涨跌幅>+2%）维度误判率改用「跑输大盘>3%」而非绝对亏损。"
    AddH $sb "（三）自动化调度时间线" 2
    AddTbl $sb @("时间","任务","模式","产出") @(
        ,@("N日20:00","每日荐股分析","daily","每日股票推荐报告")
        ,@("N+1日19:00","次日后评估","eval","评估报告_YYYYMMDD.docx")
        ,@("N+1日20:00","每日荐股分析（新版）","daily_latest","使用优化后白皮书")
    )
    AddP $sb "每个任务内建开盘判断（is_market_open.ps1），非交易日自动跳过。评估完成后自动优化白皮书，1小时后新版分析使用优化后参数。次版本升级需人工确认。"
    AddH $sb "（四）输出文档命名规范" 2
    AddP $sb "评估报告统一命名为 评估报告_YYYYMMDD.docx（YYYYMMDD为被评估荐股日期N日）。存储于事后评估目录。报告包含整体表现、逐股明细、维度回检摘要、规则验证、参数校准建议、优化状态六部分。"
    # Chapter 2
    AddE $sb; AddH $sb "二、次日数据采集与比对" 1
    AddH $sb "（一）数据获取" 2
    AddTbl $sb @("数据项","来源","用途") @(
        ,@("T日推荐列表","T日荐股报告","评估对象")
        ,@("T日评分明细","评分系统输出","归因基准")
        ,@("T+1日开盘价","腾讯行情","模拟买入价")
        ,@("T+1日收盘价","腾讯行情","模拟卖出价")
        ,@("T+1日最高/最低价","腾讯行情","止损触发判断")
        ,@("T+1日成交量/换手率","腾讯行情","量能验证")
        ,@("T+1日沪深300涨跌","腾讯行情","大盘对照")
        ,@("T+1日板块指数","东方财富","板块验证")
        ,@("沪深300指数涨跌","东方财富API","超额收益基准")
        ,@("全市场A股等权平均涨跌幅","东方财富API","大盘环境判断")
    )
    AddP $sb "否决池数据补充：否决池必须包含与推荐池相同的字段（量比、换手率、MA5/MA10/MA20、RSI、申万一级行业），用于拥挤度预警计算和路径分类分析。"
    AddH $sb "（二）模拟交易计算" 2
    AddBP $sb "买入：正常开盘→开盘价×1.005（含0.5%滑点）。一字涨停→无法成交。开盘跌>3%→开盘异常。"
    AddBP $sb "卖出（优先级）：1）日内最低价≤止损价→触发价卖出（止损价=买入价−2×ATR(14)，上限−8%）；2）盈利>10%后收盘破MA5→次日开盘卖出；3）大盘跌>3%→当日收盘卖出；4）均未触发→T+1日收盘卖出。"
    AddP $sb "日内止损检查：每个标的在T+1日模拟卖出前先检查日内最低价是否触发止损。若触发则以触发价卖出并记录 exit_reason = intraday_stop；否则继续检查其他条件。"
    AddH $sb "（三）逐项比对表" 2
    AddP $sb "对每个推荐标的逐项比对T日预期与T+1日实际：收盘价偏差影响持仓盈亏，成交量/换手率验证量价判断，板块涨跌验证板块相位判断，评分预期验证评分有效性，催化剂验证消息面预期。"
    # Chapter 3
    AddE $sb; AddH $sb "三、评分维度回检" 1
    AddH $sb "（一）逐维度预期验证" 2
    AddP $sb "对每个亏损>3%的推荐标的，回检技术面（均线/成交量/RSI/MACD）、资金面（资金流向/换手率）、板块面（潜伏/启动/主升三阶段）、消息面（催化剂落地）、风向标（同行业龙头对照）五个维度的预期是否成立。"
    AddH $sb "（二）维度误判率" 2
    AddP $sb "维度误判率=某维度给高分（高于满分60%）且次日触发误判条件的次数/该维度高分总次数。误判条件根据大盘环境动态调整："
    AddTbl $sb @("大盘环境","全市场平均涨幅","误判触发条件") @(
        ,@("强势市场",">+2%","跑输大盘>3%")
        ,@("正常市场","−2%~+2%","亏损>3%")
        ,@("弱势市场","<−2%","亏损>2%")
    )
    AddP $sb "误判率分级：≤10%优秀维持权重，10−20%正常关注趋势，20−30%偏高（连续5日触发维度重构），>30%失效（立即暂停维度）。亏损>3%时需标注技术面(TECH)/资金面(MONEY)/板块面(SECTOR)/消息面(NEWS)/基本面(FUND)/风控(RISK)误判标记。"
    AddH $sb "（三）相关系数计算（周更）" 2
    AddP $sb "每周计算各维度评分与次日涨跌幅的Spearman相关系数。ρ>0.3有效可上调权重；0.1−0.3弱相关维持权重；<0.1无预测力需重构；<0为反向指标立即暂停。改用5日滚动窗口计算，更快反映预测力变化。"
    AddH $sb "（四）误判子类型分析" 2
    AddP $sb "同一维度内不同误判原因命中率差异很大，需拆到子类型级别精准关闭失效信号。14种子类型覆盖技术面（假突破/量价背离/RSI钝化/假金叉/支撑破位）、资金面（假流入/尾盘出货/缩量反弹）、板块面（潜伏误判/启动夭折/见顶）、消息面（延迟/落空/反向）。"
    AddP $sb "子类型命中率=标记次数/信号出现总次数。≤10%维持，10−20%观察，20−30%降权50%，>30%立即暂停。暂停后30日内命中率≤15%可恢复，先以50%权重运行10日。"
    AddH $sb "（五）场景化回检——路径优选分析" 2
    AddP $sb "来源：华泰金工2026年5月研究，路径优选模型夏普比1.72显著优于不分路径的等权模型。"
    AddTbl $sb @("路径","特征","适用维度") @(
        ,@("追高(Chase-High)","多头+放量+RSI>55","技术面权重最高")
        ,@("抄底(Bottom-Fish)","缩量+RSI<35+布林下轨","资金面+基本面最高")
        ,@("追空(Chase-Short)","空头+放量下跌","风控权重最高")
        ,@("逃顶(Escape-Top)","大涨+RSI>70+拥挤预警","风控+资金面最高")
    )
    AddP $sb "分类特征使用6特征矩阵：MA位置、RSI、当日涨跌幅、量比、布林带位置、MACD位置。路径优选有效性=max(各路径胜率)−min(各路径胜率)，目标≥15%。数据积累≥10日后可指导权重自适应调整。"
    # Chapter 4
    AddE $sb; AddH $sb "四、规则有效性诊断" 1
    AddH $sb "（一）否决规则验证" 2
    AddP $sb "绝对否决误杀率=被否决但次日涨>5%只数/被否决总只数，目标≤5%，连续3日>5%审查阈值。条件否决差额=推荐池平均涨幅−否决池平均涨幅，差值>3%说明阈值过严。豁免组胜率≥65%有效，<50%失效，连续3天低于非豁免组10%暂停。"
    AddH $sb "（二）巨量惩罚监控" 2
    AddP $sb "拥挤度预警改用动态分位阈值：换手率>该股20日分位80%值且量比>1.5，或换手率>推荐池80分位值且量比>推荐池80分位值。量比惩罚阈值根据大盘动态调整：强势>15、正常>12、弱势>8。量比超标股中后续3日跌>3%比例应≥70%。"
    AddH $sb "（三）分市场阶段分析" 2
    AddP $sb "按牛市(MA5>MA20>MA60)/震荡(均线交织)/熊市(MA5<MA20<MA60)三阶段拆分胜率，识别评分体系在不同市场环境下的表现差异。"
    AddH $sb "（四）对照组评估" 2
    AddP $sb "每日同时评估三组：推荐池（目标≥60%）、被否决池（目标≤40%）、全市场基准（≈50%）。"
    AddTbl $sb @("指标","公式","目标","预警值") @(
        ,@("否决有效度","推荐胜率−否决池胜率","≥20%","<10%连续5日")
        ,@("评分区分度","推荐胜率−全市场胜率","≥10%","<5%连续5日")
        ,@("否决误杀率","否决池涨>5%占比","≤15%",">15%连续3日")
    )
    AddP $sb "否决有效度<10%→暂停区分度最低的否决条件。评分区分度<5%→全面审查六维评分。否决池跑赢推荐池→立即暂停所有否决条件逐一回测。"
    # Chapter 5
    AddE $sb; AddH $sb "五、逻辑迭代引擎" 1
    AddH $sb "（一）参数映射表" 2
    AddTbl $sb @("逻辑参数","监控指标","调整规则") @(
        ,@("推荐阈值(牛70/震65/熊60)","70−79分段胜率","连5日<55%→+3；>75%→−3")
        ,@("涨幅否决阈值","被否决股表现","误杀率>5%→放宽10%")
        ,@("PE否决阈值","PE否决误杀率","误杀率>5%→行业阈值+10")
        ,@("ATR止损倍数","止损触发率","触发率>40%→扩大倍数")
        ,@("量比封顶阈值(当前12)","封顶误杀率","连3天误杀≥2只→上调至15/20")
        ,@("均线收敛间距(<1%)","方向正确率","<60%→放宽至<2%")
    )
    AddH $sb "（二）版本升级决策树" 2
    AddBP $sb "参数微调（不升版本）：单阈值调整≤10%，不改变评分逻辑结构，连续5日以上数据支撑，AI自动执行。"
    AddBP $sb "次版本升级（v1.x→v1.x+1）：AI提建议人工确认，触发条件为维度误判率>20%连续5日/评分区分度<10%连续5日/胜率<50%连续一周。"
    AddBP $sb "主版本升级（v1.x→v2.0）：必须人工审核，触发条件为月度胜率<45%/多维度同时失效/市场结构变化。"
    AddH $sb "（三）灰度测试与回测引擎" 2
    AddP $sb "并行运行5日→数据对比（新胜率≥旧+5%）→正式切换→跟踪10日。自动化回测引擎在参数修改前用历史数据验证，覆盖PE阈值、涨幅阈值、ATR倍数、量比阈值、均线间距、流入天数、子类型权重等7类参数。回测记录存入backtest_log.csv，无回测数据的参数变更不被允许。"
    # Chapter 6
    AddE $sb; AddH $sb "六、数据存储与版本管理" 1
    AddH $sb "（一）评估记录存储" 2
    AddP $sb "records.csv：逐日评估明细（股票/评分/买卖价/收益率/误判维度/子类型/否决类型等）。summary.csv：按周/月汇总（胜率/盈亏比/超额/误判率/否决有效度/评分区分度）。issues.csv：问题跟踪（描述/严重度/优先级/状态）。backtest_log.csv：回测记录（参数/新旧值/数据范围/胜率对比/提升幅度）。"
    AddH $sb "（二）数据积累里程碑" 2
    AddTbl $sb @("时段","最少数据量","可执行分析") @(
        ,@("第1周","≥15条","基础胜率统计")
        ,@("第1个月","≥60条","维度相关性分析")
        ,@("第2个月","≥120条","否决条件定量优化")
        ,@("第3个月","≥180条","权重调整+子类型命中率稳定")
        ,@("第6个月","≥360条","分市场阶段最优参数组合")
    )
    AddH $sb "（三）文档版本管理" 2
    AddP $sb "版本号规则：参数微调不升版本（AI自动），内容修订升次版本（人工确认），结构性变更升主版本（人工审核）。每次变更需同步更新CHANGELOG和文档版本索引。"
    # Chapter 7
    AddE $sb; AddH $sb "七、优化决策流程" 1
    AddH $sb "（一）触发条件" 2
    AddTbl $sb @("触发条件","判定标准","响应动作") @(
        ,@("胜率警告","连续2周<40%","暂停策略全面排查")
        ,@("回撤警告","单周组合<−10%","暂停策略全面排查")
        ,@("维度失效","误判率>20%连续3天","触发维度重构")
        ,@("否决有效度低","有效度<10%连续5日","暂停区分度最低否决条件")
        ,@("评分区分度低","区分度<5%连续5日","全面审查相关系数")
        ,@("子类型命中率高","命中率>20%连续5日","信号降权50%")
        ,@("否决池跑赢推荐池","否决有效度为负","暂停所有否决条件逐一回测")
        ,@("全参数回测","每月1日","对所有可调参数执行回测")
    )
    AddH $sb "（二）假设—验证—切换流程" 2
    AddP $sb "Step1假设（基于评估数据提出具体假设）→Step2回测（≥10日历史数据验证）→Step3灰度（新旧并行1周）→Step4切换（胜率提升≥5%且盈亏比不降）→Step5跟踪（切换后2周确认）。异常回滚：新规则胜率低于旧规则→回退参数重新分析。"
    AddH $sb "（三）外部知识融合（月度大循环）" 2
    AddP $sb "内部评估发现我们哪做错了，外部调研发现别人有什么更好的方法。外部方法经回测验证→灰度测试→正式切换。每月1日通过定时任务触发，搜索量化交易新方法，与当前体系对比后生成采纳建议（建议尝试/跟踪观察/暂不采纳）。"
    AddH $sb "首次执行结果（2026-05-22）" 2
    AddTbl $sb @("发现","来源","优先级","状态") @(
        ,@("路径优选模型","华泰金工(2026.05)","高","已落地§3.5")
        ,@("动态权重切换","Stratapro(2026)","高","已新增指标§1.2")
        ,@("分钟级资金流","开源证券(2026.02)","中","跟踪观察")
        ,@("算子网格搜索","山西证券(2026.04)","中","跟踪观察")
        ,@("拥挤度因子","衡泰xCN4(2026)","高","已新增指标§1.2")
    )
    # Footer
    AddE $sb; AddE $sb
    [void]$sb.Append('<w:p><w:pPr><w:pBdr><w:top w:val="single" w:sz="6" w:space="4" w:color="CCCCCC"/></w:pBdr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="18"/><w:color w:val="999999"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape("本评估体系为铁律量化选股系统配套文档。所有优化决策必须有数据支撑。") + '</w:t></w:r></w:p>')
    [void]$sb.Append('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="Microsoft YaHei"/><w:sz w:val="18"/><w:color w:val="999999"/></w:rPr><w:t>' + [System.Security.SecurityElement]::Escape("版本：v1.5 | 2026-05-22 | 铁律量化") + '</w:t></w:r></w:p>')
    return $sb.ToString()
}
# Main
$docPath = [System.IO.Path]::GetFullPath("Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))\每日荐股\事后评估\次日后评估白皮书_v1.5.docx")
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
