#!/usr/bin/env python3
"""cninfo公告API封装 — 巨潮资讯网公开JSON API

Replaces pigeon_cninfo.ps1. macOS compatible.
Data source [16]: cninfo.com.cn, backup [17]: china-stock-mcp
Code level: L0
"""
import json
import os
import time
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent.parent.parent)
CONFIG_PATH = os.path.join(ROOT, "代码文件", "信鸽信息采集", "pigeon_config.json")


def get_config():
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"Pigeon config not found: {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_announcements(stock_code, stock_name, start_date, end_date, max_results=20):
    """从巨潮资讯网获取上市公司公告列表

    Args:
        stock_code: 6-digit stock code
        stock_name: Stock name for search keyword
        start_date: yyyy-MM-dd
        end_date: yyyy-MM-dd
        max_results: Max results to return

    Returns:
        list of dicts with title/content/publish_time/pdf_url/sec_name/sec_code/source
    """
    config = get_config()
    api = config.get("api", {})
    base_url = api.get("cninfo_base_url", "http://www.cninfo.com.cn/new/fulltextSearch/query")
    timeout = api.get("cninfo_timeout_sec", 10)
    max_retries = api.get("cninfo_max_retries", 3)
    interval_ms = api.get("cninfo_interval_ms", 500)

    search_key = urllib.parse.quote(stock_name)
    url = (f"{base_url}?searchkey={search_key}&sdate={start_date}&edate={end_date}"
           f"&isfulltext=true&sortName=pubdate&sortType=desc&pageNum=1")

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "http://www.cninfo.com.cn/new/fulltextSearch",
    }

    last_error = None
    for attempt in range(max_retries):
        try:
            time.sleep(interval_ms / 1000)
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            announcements = data.get("announcements", [])
            if not announcements:
                print(f"[cninfo] {stock_code} {stock_name}: 0 announcements (empty response)")
                return []

            results = []
            for item in announcements[:max_results]:
                title = item.get("announcementTitle", "").replace("<em>", "").replace("</em>", "")
                content = (item.get("announcementContent", "") or "").replace("<em>", "").replace("</em>", "")

                ann_id = item.get("announcementId") or item.get("announcementid")
                if not ann_id:
                    adj_url = item.get("adjunctUrl", "")
                    import re
                    m = re.search(r"/(\d+)\.PDF$", adj_url, re.IGNORECASE)
                    if m:
                        ann_id = m.group(1)

                cninfo_url = (f"http://www.cninfo.com.cn/new/disclosure/detail?"
                              f"stockCode={item.get('secCode', '')}&announcementId={ann_id}") if ann_id else None

                results.append({
                    "title": title,
                    "content": content,
                    "publish_time": item.get("announcementTime", ""),
                    "pdf_url": "http://static.cninfo.com.cn/" + item.get("adjunctUrl", ""),
                    "sec_name": item.get("secName", ""),
                    "sec_code": item.get("secCode", ""),
                    "source": "cninfo",
                    "source_type": "primary",
                    "announcement_id": str(ann_id) if ann_id else None,
                    "cninfo_url": cninfo_url,
                })

            print(f"[cninfo] {stock_code} {stock_name}: {len(results)} announcements fetched")
            return results

        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                backoff = 2 ** (attempt + 1)
                print(f"[cninfo] {stock_code} retry {attempt+1}/{max_retries} after {backoff}s: {e}")
                time.sleep(backoff)

    print(f"[cninfo] {stock_code} FAILED after {max_retries} attempts: {last_error}")
    print(f"[cninfo] {stock_code}: falling back to china-stock-mcp[17]")
    return None


def fetch_announcements_backup(stock_code, stock_name, max_results=20):
    """备源[17] — china-stock-mcp (cninfo主源失败时触发)"""
    print(f"[china-stock-mcp] {stock_code}: attempting backup fetch via MCP...")
    print(f"[china-stock-mcp] MCP备源暂未集成 — 返回空，使用缓存[C]兜底")
    return []
