#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Volume Profile CLI — 供PowerShell通过管道调用 calc_volume_profile

用法:
    powershell: $klines | ConvertTo-Json | python vp_cli.py
    bash:       echo '{"highs":[...],...}' | python vp_cli.py

输入 JSON 格式:
    { "highs": [...], "lows": [...], "closes": [...], "volumes": [...],
      "num_bins": 50, "lookback": null }

输出: calc_volume_profile() 返回的 dict → JSON stdout
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.technical import calc_volume_profile


def main():
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            json.dump({"error": "empty stdin"}, sys.stdout, ensure_ascii=False)
            sys.exit(0)
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        json.dump({"error": f"JSON decode: {e}"}, sys.stdout, ensure_ascii=False)
        sys.exit(0)

    result = calc_volume_profile(
        highs=data.get("highs", []),
        lows=data.get("lows", []),
        closes=data.get("closes", []),
        volumes=data.get("volumes", []),
        num_bins=data.get("num_bins", 50),
        lookback=data.get("lookback"),
    )
    json.dump(result, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
