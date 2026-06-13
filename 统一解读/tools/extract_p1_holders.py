#!/usr/bin/env python3
"""
P1 PDF 字段抽取脚本 — 从已下载的定期报告PDF中抽取前十大股东字段。

用法:
  python3 extract_p1_holders.py \
    --manifest /path/to/manifest.json \
    --target-shareholder "基本养老保险基金"
"""

import json, os, sys, re

try:
    import pypdf
except ImportError:
    pypdf = None

def extract_text_from_pdf(pdf_path):
    """用 pypdf 抽取文本"""
    if pypdf is None:
        return None, "pypdf 未安装，无法抽取PDF文本"
    try:
        reader = pypdf.PdfReader(pdf_path)
        pages_text = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text)
        full_text = "\n".join(pages_text)
        if len(full_text.strip()) < 50:
            return None, "PDF文本抽取结果为空或过短（可能为扫描件）"
        return full_text, None
    except Exception as e:
        return None, f"PDF抽取异常: {e}"


def search_holder_in_text(text, target_name):
    """在文本中搜索目标股东名称，返回匹配片段和上下文"""
    results = []
    # 直接搜索
    if target_name in text:
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if target_name in line:
                start = max(0, i - 3)
                end = min(len(lines), i + 4)
                ctx = "\n".join(lines[start:end])
                results.append({"line": i, "context": ctx})
    # 如果没有直接命中，尝试按关键词分段
    if not results:
        keywords = target_name[:6]
        if keywords in text:
            lines = text.split("\n")
            for i, line in enumerate(lines):
                if keywords in line:
                    start = max(0, i - 3)
                    end = min(len(lines), i + 4)
                    ctx = "\n".join(lines[start:end])
                    results.append({"line": i, "context": ctx, "partial": True})
    return results


def search_top10_section(text):
    """搜索前十大股东相关段落"""
    markers = ["前十名股东", "前十名无限售条件股东", "前十名股东持股情况",
               "前十名无限售条件股东持股情况"]
    sections = []
    lines = text.split("\n")
    for i, line in enumerate(lines):
        for m in markers:
            if m in line:
                start = i
                end = min(len(lines), i + 20)
                section = "\n".join(lines[start:end])
                sections.append({"marker": m, "line": i, "section": section})
    return sections


def main():
    import argparse
    parser = argparse.ArgumentParser(description="P1 PDF 股东字段抽取")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--target-shareholder", required=True)
    parser.add_argument("--expected-mode", default="present", choices=["present", "absent"],
                        help="present: 目标股东应出现在前十大; absent: 目标股东应在PDF中不存在")
    args = parser.parse_args()

    with open(args.manifest, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    pdf_path = manifest.get("local_pdf_path")
    if not pdf_path or not os.path.exists(pdf_path):
        print(f"[FAIL] PDF 不存在: {pdf_path}")
        sys.exit(1)

    out_dir = os.path.dirname(os.path.abspath(args.manifest))

    # Step 1: 抽取文本
    print(f"[1/3] 抽取文本: {pdf_path}")
    text, error = extract_text_from_pdf(pdf_path)

    result = {
        "manifest_path": args.manifest,
        "target_shareholder": args.target_shareholder,
        "pdf_path": pdf_path,
        "extraction_status": "unknown",
        "holder_matches": [],
        "top10_sections": [],
        "needs_ocr": False,
        "notes": []
    }

    if error:
        print(f"  [FAIL] {error}")
        result["extraction_status"] = "failed"
        result["notes"].append(error)
        # Check if it might be a scanned PDF
        if "pypdf" in str(error) or "过短" in str(error):
            result["needs_ocr"] = True
        with open(os.path.join(out_dir, "holders_extract.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"  输出: {os.path.join(out_dir, 'holders_extract.json')}")
        sys.exit(0 if result["needs_ocr"] else 1)

    print(f"  抽取 {len(text)} 字符")

    # Step 2: 搜索前十大段落
    print(f"[2/3] 搜索前十大股东段落 ...")
    top10s = search_top10_section(text)
    result["top10_sections"] = top10s
    if top10s:
        print(f"  找到 {len(top10s)} 个相关段落")
        for t in top10s:
            print(f"    L{t['line']}: {t['marker']}")
    else:
        print(f"  未找到前十大股东段落")
        result["notes"].append("未找到前十大股东标题段落")

    # Step 3: 搜索目标股东
    print(f"[3/3] 搜索目标股东: {args.target_shareholder} ...")
    matches = search_holder_in_text(text, args.target_shareholder)
    result["holder_matches"] = matches

    hit = bool(matches)
    result["holder_matches"] = matches

    # 判断匹配是否在前十大段落中（排除会计制度等非前十大段落中的"基本养老保险费"类误伤）
    top10_line_ranges = []
    for t in top10s:
        start_line = max(0, t["line"] - 2)
        end_line = t["line"] + 25
        top10_line_ranges.append((start_line, end_line))

    def is_in_top10_context(match_line):
        for lo, hi in top10_line_ranges:
            if lo <= match_line <= hi:
                return True
        return False

    if matches and args.expected_mode == "absent":
        # 检查匹配是否在前十大段落中
        top10_hits = [m for m in matches if is_in_top10_context(m["line"])]
        other_hits = [m for m in matches if not is_in_top10_context(m["line"])]
        if not top10_hits and other_hits:
            # 只有非前十大段落误伤，实际缺席
            print(f"  目标股东仅出现在非前十大段落({len(other_hits)}处)，前十大段落未出现（absent 模式 ✅）")
            result["extraction_status"] = "verified_absent"
            result["absence_verified"] = True
            result["target_shareholder_found"] = False
            result["top10_sections_count"] = len(top10s)
            result["notes"].append(f"前十大段落已抽取({len(top10s)}段)，目标股东仅出现在非前十大段落（如会计注释），确认前十大缺席")
            hit = False  # 强制视为absent
            matches = []
            result["holder_matches"] = [{"line": m["line"], "context": m["context"],
                "note": "非前十大段落命中（如会计注释），不影响缺席判定"} for m in other_hits]

    if args.expected_mode == "present":
        if hit:
            print(f"  找到 {len(matches)} 处匹配（present 模式 ✅）")
            for m in matches:
                print(f"    L{m['line']}: {m['context'][:120]}")
            result["extraction_status"] = "hit"
        else:
            partial = args.target_shareholder[:4]
            partial_matches = search_holder_in_text(text, partial)
            if partial_matches:
                print(f"  [WARN] 未完全命中，仅部分匹配（{partial}）")
                result["notes"].append(f"仅部分匹配关键词'{partial}'，非完整名称")
                result["extraction_status"] = "partial_hit"
            else:
                print(f"  [FAIL] expected_mode=present 但未找到目标股东")
                result["extraction_status"] = "miss"
                result["notes"].append(f"PDF文本中未找到'{args.target_shareholder}'")
    else:  # expected_mode == "absent"
        if not hit and top10s:
            print(f"  目标股东未出现，且前十大段落存在（absent 模式 ✅）")
            result["extraction_status"] = "verified_absent"
            result["absence_verified"] = True
            result["target_shareholder_found"] = False
            result["top10_sections_count"] = len(top10s)
            result["notes"].append(f"前十大段落已抽取({len(top10s)}段)，目标股东未命中，确认缺席")
        elif not hit and not top10s:
            print(f"  [WARN] 目标股东未出现，但前十大段落也未找到，无法确认")
            result["extraction_status"] = "uncertain_absent"
            result["notes"].append("未找到前十大段落，无法确认缺席是否有意义")
        else:
            print(f"  [WARN] expected_mode=absent 但意外命中目标股东")
            result["extraction_status"] = "unexpected_hit"
            result["notes"].append(f"expected_mode=absent 但目标股东出现于PDF文本中")

    # 输出抽取结果
    extract_path = os.path.join(out_dir, "holders_extract.json")
    with open(extract_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n  输出: {extract_path}")

    # 同时保存原始文本供人工核查
    text_path = os.path.join(out_dir, "extracted_text.txt")
    with open(text_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"  原始文本: {text_path}")

    if result["extraction_status"] == "hit":
        print("\n✅ 目标股东命中")
    elif result["extraction_status"] == "partial_hit":
        print("\n⚠️ 部分命中，需人工确认")
    else:
        print("\n⚠️ 未命中，可能需要OCR")


if __name__ == "__main__":
    main()
