#!/bin/bash
# install_crontab.sh — ⛔ 已废弃，使用 generate_launchd.py
#
# 铁律量化调度系统已迁移至 macOS launchd。
# 当前唯一调度注册器：代码文件/每日荐股/scripts/generate_launchd.py
# 当前唯一调度执行器：launchd
#
# 禁止 crontab 继续运行铁律量化任务。

echo ""
echo "⛔  install_crontab.sh 已废弃"
echo ""
echo "    铁律量化调度系统已全面迁移至 macOS launchd。"
echo "    crontab 不再作为铁律量化任务的调度入口。"
echo ""
echo "    请使用以下命令管理调度任务："
echo ""
echo "        python3 代码文件/每日荐股/scripts/generate_launchd.py --list"
echo "        python3 代码文件/每日荐股/scripts/generate_launchd.py --install all"
echo "        python3 代码文件/每日荐股/scripts/generate_launchd.py --uninstall all"
echo "        python3 代码文件/每日荐股/scripts/generate_launchd.py --status"
echo ""
exit 2
