#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
铁律量化 · 评分引擎 v2.9 — 入口包装
原文件已拆分为 engine/ 包，本文件保留作为兼容入口。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine.engine import main

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--date", type=str, default=None, help="交易日 YYYY-MM-DD")
    p.add_argument("--verbose", action="store_true", default=False)
    args = p.parse_args()
    main(run_date=args.date, verbose=args.verbose)
