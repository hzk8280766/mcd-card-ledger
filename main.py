#!/usr/bin/env python3
"""麦卡账房 mcd-card-ledger —— CLI 入口。

用法：
  python main.py --mock                       # 离线演示（无需 Token）
  python main.py --mock --mock-profile weekend  # 换一个用户画像演示
  python main.py                              # 真实模式：读取 config.json 里的 MCP Token
  python main.py --days 60 --html report.html
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys

try:  # 支持 python -m mcdledger.main
    from . import __version__
    from .analyzer import analyze
    from .mock import (make_mock_orders, make_mock_coupons,
                       make_mock_available_coupons, make_mock_account)
    from .report import render_text, render_html
except ImportError:  # 支持直接 python main.py
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from mcdledger import __version__
    from mcdledger.analyzer import analyze
    from mcdledger.mock import (make_mock_orders, make_mock_coupons,
                                make_mock_available_coupons, make_mock_account)
    from mcdledger.report import render_text, render_html

DEFAULT_CONFIG = "config.json"


def load_config(path):
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError) as e:
        print("警告：配置文件 %s 解析失败（%s），将使用默认参数" % (path, e))
        return {}


def fetch_live_data(client):
    """按顺序拉取分析所需数据；非关键数据失败时降级继续。"""
    orders = client.call_tool("order-list")
    try:
        my_coupons = client.call_tool("query-my-coupons")
    except Exception as e:
        print("警告：我的优惠券查询失败（%s），券盘点将跳过" % e)
        my_coupons = []
    try:
        available = client.call_tool("available-coupons")
    except Exception as e:
        print("警告：麦麦省可领券查询失败（%s），已跳过" % e)
        available = []
    try:
        account = client.call_tool("query-my-account")
    except Exception as e:
        print("警告：积分查询失败（%s），已跳过" % e)
        account = {}
    return orders, my_coupons, available, account


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="mcd-card-ledger",
        description="麦当劳付费卡（麦金卡/早餐卡）回本计算器：用你的真实订单算一笔账",
    )
    parser.add_argument("--mock", action="store_true",
                        help="离线演示模式：使用内置模拟数据，无需 MCP Token")
    parser.add_argument("--mock-profile", choices=["commuter", "weekend"],
                        default="commuter", help="模拟用户画像（默认 commuter）")
    parser.add_argument("--config", default=DEFAULT_CONFIG,
                        help="配置文件路径（默认 ./config.json）")
    parser.add_argument("--days", type=int, default=None,
                        help="分析窗口天数（默认 90，可被 config.json 覆盖）")
    parser.add_argument("--html", default="mcd-card-report.html",
                        help="HTML 卡片输出路径")
    parser.add_argument("--json", dest="json_out", default=None,
                        help="可选：把分析结果另存为 JSON")
    parser.add_argument("--no-color", action="store_true", help="终端输出不带颜色")
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    args = parser.parse_args(argv)

    cfg = load_config(args.config)
    days = args.days or cfg.get("analysis_days", 90)

    if args.mock:
        source = "mock(%s)" % args.mock_profile
        orders = make_mock_orders(days=days, profile=args.mock_profile)
        my_coupons = make_mock_coupons()
        available = make_mock_available_coupons()
        account = make_mock_account()
    else:
        token = cfg.get("mcp_token") or os.environ.get("MCD_MCP_TOKEN", "")
        if not token or "粘贴" in token:
            print("错误：未配置 MCP Token。")
            print("  1. 到 https://open.mcd.cn/mcp 用手机号登录，控制台里点「激活」申请")
            print("  2. 复制 config.example.json 为 config.json，把 Token 填进去")
            print("  3. 或者先用 python main.py --mock 体验完整演示流程")
            return 2
        try:
            from .mcp_client import MCDClient, MCPError
        except ImportError:
            from mcdledger.mcp_client import MCDClient, MCPError
        client = MCDClient(token)
        try:
            client.initialize()
        except MCPError as e:
            print("错误：MCP 握手失败：%s" % e)
            print("  请检查 Token 是否有效、网络是否能访问 mcp.mcd.cn")
            return 3
        try:
            orders, my_coupons, available, account = fetch_live_data(client)
        except Exception as e:
            print("错误：拉取订单数据失败：%s" % e)
            print("  order-list 是核心数据，失败时无法继续；可先用 --mock 模式体验。")
            return 4
        source = "mcd-mcp(live)"

    result = analyze(orders, my_coupons, available, account,
                     card_params=cfg.get("card_params"), days=days)

    print(render_text(result, color=not args.no_color))

    if args.html:
        try:
            with open(args.html, "w", encoding="utf-8") as f:
                f.write(render_html(result))
            print("HTML 卡片已生成：%s（浏览器打开即可截图分享）" % args.html)
        except OSError as e:
            print("警告：HTML 写出失败：%s" % e)

    if args.json_out:
        try:
            with open(args.json_out, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print("JSON 结果已保存：%s" % args.json_out)
        except OSError as e:
            print("警告：JSON 写出失败：%s" % e)

    print("数据来源：%s ｜ 分析窗口：%d 天" % (source, days))
    return 0


if __name__ == "__main__":
    sys.exit(main())
