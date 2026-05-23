"""铁律量化 · A股金融数据 MCP Server v1.1
对接腾讯行情/新浪K线/东方财富财务，提供实时行情、历史K线、财务数据。
MCP Python SDK 1.27+ compatible.
"""
import json
import time
import urllib.request
from datetime import datetime

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("tielv-financial")


# ── API 数据源 ────────────────────────────────────────

def _http_get(url: str, timeout: int = 10):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": "https://finance.eastmoney.com/",
    })
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception:
            if attempt == 2:
                return None
            time.sleep(0.5)


def _resolve_code(code: str) -> str:
    """6位代码 → 市场前缀代码"""
    if code.startswith(("6", "9")):
        return f"sh{code}"
    return f"sz{code}"


def _get_tencent_quote(code: str) -> dict | None:
    full = _resolve_code(code)
    raw = _http_get(f"https://qt.gtimg.cn/q={full}")
    if not raw:
        return None
    try:
        parts = raw.split("~")
        if len(parts) < 50:
            return None
        return {
            "代码": parts[2], "名称": parts[1],
            "最新价": float(parts[3]) if parts[3] else None,
            "昨收": float(parts[4]) if parts[4] else None,
            "开盘": float(parts[5]) if parts[5] else None,
            "成交量(手)": int(parts[6]) if parts[6] else None,
            "最高": float(parts[33]) if parts[33] else None,
            "最低": float(parts[34]) if parts[34] else None,
            "涨跌幅%": float(parts[32]) if parts[32] else None,
            "换手率%": float(parts[38]) if parts[38] else None,
            "市盈率": float(parts[39]) if parts[39] else None,
            "流通市值(亿)": round(float(parts[44]) / 1e8, 2) if parts[44] else None,
            "总市值(亿)": round(float(parts[45]) / 1e8, 2) if parts[45] else None,
            "更新时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    except (ValueError, IndexError):
        return None


def _get_sina_kline(code: str, days: int = 30) -> list[dict] | None:
    full = _resolve_code(code)
    url = (
        f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        f"CN_MarketData.getKLineData?symbol={full}&scale=240&ma=no&datalen={days}"
    )
    raw = _http_get(url)
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return [{
            "日期": d.get("day", ""),
            "开盘": float(d["open"]) if d.get("open") else None,
            "收盘": float(d["close"]) if d.get("close") else None,
            "最高": float(d["high"]) if d.get("high") else None,
            "最低": float(d["low"]) if d.get("low") else None,
            "成交量": int(d["volume"]) if d.get("volume") else None,
        } for d in data[-days:]]
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def _get_eastmoney_financial(code: str) -> dict | None:
    url = (
        "https://datacenter.eastmoney.com/securities/api/data/v1/get"
        "?reportName=RPT_DMSK_FN_MAININDICATOR"
        "&columns=SECURITY_CODE,SECURITY_NAME_ABBR,NOTICE_DATE,BASIC_EPS,"
        "WEIGHTAVG_ROE,GROSS_PROFIT_RATIO,NET_PROFIT_MARGIN,"
        "DEBT_ASSET_RATIO,CURRENT_RATIO,YSTZ,YSYSTZ,"
        "TOTAL_OPERATE_INCOME,TOTAL_PROFIT,PARENT_NETPROFIT"
        f"&filter=(SECURITY_CODE%3D%22{code}%22)"
        "&pageSize=4&sort=NOTICE_DATE&sortTypes=-1"
    )
    raw = _http_get(url)
    if not raw:
        return None
    try:
        resp = json.loads(raw)
        if not resp.get("success") or not resp.get("result"):
            return None
        items = resp["result"]["data"]
        if not items:
            return None
        latest = items[0]
        return {
            "代码": latest.get("SECURITY_CODE", code),
            "名称": latest.get("SECURITY_NAME_ABBR", ""),
            "报告期": latest.get("NOTICE_DATE", ""),
            "基本每股收益": latest.get("BASIC_EPS"),
            "加权ROE%": latest.get("WEIGHTAVG_ROE"),
            "毛利率%": latest.get("GROSS_PROFIT_RATIO"),
            "净利率%": latest.get("NET_PROFIT_MARGIN"),
            "资产负债率%": latest.get("DEBT_ASSET_RATIO"),
            "流动比率": latest.get("CURRENT_RATIO"),
            "营业总收入(亿)": round(latest["TOTAL_OPERATE_INCOME"] / 1e8, 2) if latest.get("TOTAL_OPERATE_INCOME") else None,
            "归母净利润(亿)": round(latest["PARENT_NETPROFIT"] / 1e8, 2) if latest.get("PARENT_NETPROFIT") else None,
            "营收同比%": latest.get("YSTZ"),
            "归母净利润同比%": latest.get("YSYSTZ"),
        }
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


# ── 工具定义 ──────────────────────────────────────────

TOOLS = [
    Tool(
        name="get_realtime_quote",
        description="获取A股实时行情报价（价格、成交量、涨跌幅、市盈率、市值）",
        inputSchema={
            "type": "object",
            "properties": {
                "stock_code": {
                    "type": "string",
                    "description": "6位股票代码，如 000001(平安银行) 或 600519(贵州茅台)",
                }
            },
            "required": ["stock_code"],
        },
    ),
    Tool(
        name="get_kline_data",
        description="获取A股历史日K线数据（开盘、收盘、最高、最低、成交量）",
        inputSchema={
            "type": "object",
            "properties": {
                "stock_code": {"type": "string", "description": "6位股票代码"},
                "days": {"type": "integer", "description": "获取最近多少天的K线，默认30天，最大100天", "default": 30},
            },
            "required": ["stock_code"],
        },
    ),
    Tool(
        name="get_financial_data",
        description="获取A股最新季报关键财务指标（ROE、毛利率、净利率、营收、净利润同比等）",
        inputSchema={
            "type": "object",
            "properties": {
                "stock_code": {"type": "string", "description": "6位股票代码"},
            },
            "required": ["stock_code"],
        },
    ),
    Tool(
        name="get_stock_brief",
        description="一键获取A股综合简报：实时行情+近10日K线趋势+最新季报财务核心指标",
        inputSchema={
            "type": "object",
            "properties": {
                "stock_code": {"type": "string", "description": "6位股票代码"},
            },
            "required": ["stock_code"],
        },
    ),
]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    code = arguments.get("stock_code", "").strip()

    if name == "get_realtime_quote":
        result = _get_tencent_quote(code)
        text = json.dumps(result, ensure_ascii=False, indent=2) if result else f"❌ 无法获取 {code} 的实时行情"

    elif name == "get_kline_data":
        days = min(int(arguments.get("days", 30)), 100)
        result = _get_sina_kline(code, days)
        text = json.dumps(result, ensure_ascii=False, indent=2) if result else f"❌ 无法获取 {code} 的K线数据"

    elif name == "get_financial_data":
        result = _get_eastmoney_financial(code)
        text = json.dumps(result, ensure_ascii=False, indent=2) if result else f"❌ 无法获取 {code} 的财务数据"

    elif name == "get_stock_brief":
        quote = _get_tencent_quote(code)
        kline = _get_sina_kline(code, 10)
        fin = _get_eastmoney_financial(code)
        brief = {"代码": code, "查询时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        if quote:
            brief["行情"] = {k: quote[k] for k in ["名称","最新价","涨跌幅%","市盈率","总市值(亿)"] if k in quote}
        if kline:
            closes = [d["收盘"] for d in kline if d.get("收盘")]
            if closes:
                brief["K线摘要"] = {"近10日最高": round(max(closes),2), "近10日最低": round(min(closes),2), "最新收盘": closes[-1], "较10日前变化%": round((closes[-1]/closes[0]-1)*100,2)}
        if fin:
            brief["财务"] = {k: fin[k] for k in ["加权ROE%","毛利率%","归母净利润(亿)","营收同比%"] if k in fin}
        text = json.dumps(brief, ensure_ascii=False, indent=2)

    else:
        text = f"❌ 未知工具: {name}"

    return [TextContent(type="text", text=text)]


# ── 启动 ──────────────────────────────────────────────

async def main():
    async with stdio_server() as (stdin, stdout):
        await server.run(stdin, stdout)

if __name__ == "__main__":
    import anyio
    anyio.run(main)
