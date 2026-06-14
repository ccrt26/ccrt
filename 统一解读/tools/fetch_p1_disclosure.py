#!/usr/bin/env python3
"""
P1 官方公告采集脚本 — 从巨潮资讯(cninfo)搜索并下载定期报告PDF
用 cninfo 公开搜索API定位公告，下载PDF，输出manifest.json。

用法:
  python3 fetch_p1_disclosure.py \\
    --stock-code 600114 \\
    --stock-name 东睦股份 \\
    --keyword "2025年第三季度报告" \\
    --sdate 2025-10-01 \\
    --edate 2025-11-15 \\
    --out-dir /Users/ccrt/ccrt/统一解读/evidence/p1_disclosures/600114/2025Q3
"""

import json, os, sys, hashlib, re, time, urllib.request, urllib.parse
from datetime import datetime

def fetch_cninfo_search(keyword, sdate, edate, page_num=1, page_size=30):
    """调用 cninfo 全文搜索API"""
    url = "http://www.cninfo.com.cn/new/fulltextSearch/full"
    data = {
        "searchkey": keyword,
        "sdate": sdate,
        "edate": edate,
        "isfulltext": "false",
        "sortName": "pubdate",
        "sortType": "desc",
        "pageNum": str(page_num),
        "pageSize": str(page_size),
    }
    data_enc = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=data_enc)
    req.add_header("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)")
    req.add_header("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
    req.add_header("Accept", "*/*")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except Exception as e:
        return {"error": str(e)}


def download_pdf(pdf_url, out_path):
    """下载PDF到本地"""
    req = urllib.request.Request(pdf_url)
    req.add_header("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
            with open(out_path, "wb") as f:
                f.write(data)
        sha256 = hashlib.sha256(data).hexdigest()
        return {"size": len(data), "sha256": sha256, "path": out_path}
    except Exception as e:
        return {"error": str(e)}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="P1 官方公告采集")
    parser.add_argument("--stock-code", required=True)
    parser.add_argument("--stock-name", required=True)
    parser.add_argument("--keyword", required=True)
    parser.add_argument("--sdate", required=True)
    parser.add_argument("--edate", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    # Step 1: 搜索cninfo
    print(f"[1/3] 搜索 cninfo: keyword={args.keyword} sdate={args.sdate} edate={args.edate}")
    search_result = fetch_cninfo_search(args.keyword, args.sdate, args.edate)

    if "error" in search_result:
        print(f"[FAIL] cninfo 搜索失败: {search_result['error']}")
        manifest = {
            "stock_code": args.stock_code,
            "stock_name": args.stock_name,
            "keyword": args.keyword,
            "search_status": "failed",
            "search_error": search_result["error"],
            "search_timestamp": datetime.now().isoformat(),
        }
        with open(os.path.join(args.out_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        sys.exit(1)

    # Step 2: 解析搜索结果
    total_announcements = search_result.get("totalAnnouncement", 0)
    announcements = search_result.get("announcements", [])
    if isinstance(announcements, list):
        pass
    elif isinstance(announcements, dict):
        announcements = announcements.get("announcements", [])
    else:
        announcements = []

    # 过滤：code匹配args.stock_code, 标题含 keyword
    filtered = []
    for ann in announcements:
        sec_code = str(ann.get("secCode", ""))
        title = ann.get("announcementTitle", "")
        if not sec_code.endswith(args.stock_code):
            continue
        # 排除明显的摘要（全文通常在另一条）
        if "摘要" in title:
            continue
        # 标题应含stock_name和keyword
        if args.stock_name not in title and args.stock_name not in str(ann.get("secName", "")):
            continue
        # 关键词匹配（去掉HTML标签）
        clean_title = re.sub(r'<[^>]+>', '', title)
        if args.keyword.replace(" ", "") not in clean_title.replace(" ", ""):
            continue
        filtered.append(ann)

    if not filtered:
        print(f"[FAIL] 未找到匹配公告 (total={total_announcements}, matched=0)")
        print(f"  原始返回条目数: {len(announcements)}")
        # 保存搜索响应以便调试
        debug_path = os.path.join(args.out_dir, "search_response.json")
        with open(debug_path, "w", encoding="utf-8") as f:
            json.dump(search_result, f, ensure_ascii=False, indent=2)
        print(f"  搜索响应已保存: {debug_path}")
        manifest = {
            "stock_code": args.stock_code,
            "search_status": "no_match",
            "total_announcements": total_announcements,
            "filtered_count": 0,
            "search_timestamp": datetime.now().isoformat(),
            "debug_response_path": debug_path,
        }
        with open(os.path.join(args.out_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        sys.exit(1)

    # 取第一条匹配的(按排序最新)
    ann = filtered[0]
    title = ann.get("announcementTitle", "").strip()
    adjunct_url = ann.get("adjunctUrl", "").strip()
    announcement_time = ann.get("announcementTime", int(time.time() * 1000))
    if isinstance(announcement_time, int) and announcement_time > 1e10:
        disclosure_date = datetime.fromtimestamp(announcement_time / 1000).strftime("%Y-%m-%d")
    else:
        disclosure_date = str(announcement_time)

    pdf_url = f"http://static.cninfo.com.cn/{adjunct_url}"
    print(f"  匹配公告: {title}")
    print(f"  PDF URL: {pdf_url}")
    print(f"  披露日期: {disclosure_date}")

    # Step 3: 下载PDF
    print(f"[2/3] 下载 PDF ...")
    pdf_path = os.path.join(args.out_dir, "original.pdf")
    dl_result = download_pdf(pdf_url, pdf_path)

    if "error" in dl_result:
        print(f"[FAIL] PDF 下载失败: {dl_result['error']}")
        manifest = {
            "stock_code": args.stock_code,
            "stock_name": args.stock_name,
            "report_period": keyword_to_period(args.keyword),
            "announcement_title": title,
            "disclosure_date": disclosure_date,
            "source_platform": "cninfo",
            "source_url": pdf_url,
            "local_pdf_path": pdf_path,
            "pdf_download_status": "failed",
            "pdf_error": dl_result["error"],
            "verification_status": "download_failed",
            "search_timestamp": datetime.now().isoformat(),
        }
        with open(os.path.join(args.out_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        sys.exit(1)

    print(f"  已下载: {dl_result['size']} bytes, sha256={dl_result['sha256'][:16]}...")

    # Step 4: 输出 manifest
    print(f"[3/3] 输出 manifest.json")
    manifest = {
        "stock_code": args.stock_code,
        "stock_name": args.stock_name,
        "report_period": keyword_to_period(args.keyword),
        "announcement_title": title,
        "disclosure_date": disclosure_date,
        "source_platform": "cninfo",
        "source_url": pdf_url,
        "local_pdf_path": os.path.abspath(pdf_path),
        "local_pdf_size": dl_result["size"],
        "sha256": dl_result["sha256"],
        "downloaded_at": datetime.now().isoformat(),
        "verification_status": "downloaded",
        "search_timestamp": datetime.now().isoformat(),
    }
    manifest_path = os.path.join(args.out_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"  manifest: {manifest_path}")
    print("\n✅ P1 PDF 下载完成。")


def keyword_to_period(kw):
    """从关键词提取报告期"""
    m = re.search(r"(\d{4})年(.{1,4})报告", kw)
    if m:
        year = m.group(1)
        season = m.group(2)
        if "第三" in season or "三季" in season:
            return f"{year}Q3"
        if "第二" in season or "中" in season:
            return f"{year}Q2"
        if "第一" in season:
            return f"{year}Q1"
        if "年" in season and "报" in season:
            return f"{year}年报"
    return "unknown"


if __name__ == "__main__":
    main()
