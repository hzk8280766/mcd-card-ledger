"""离线 Mock 数据：没有 MCP Token 也能完整跑通全流程。

内置两个典型用户画像，方便演示和回归测试：
- commuter（通勤党）：月均约 11 单，早餐+外送都频繁 → 两张卡都值
- weekend（周末党）：月均约 4 单，几乎不吃早餐、很少外送 → 两张卡都不值
"""
from __future__ import annotations

import datetime as _dt
import random

_BURGERS = ["麦辣鸡腿汉堡", "板烧鸡腿堡", "双层吉士汉堡", "麦香鱼"]
_SIDES = ["中薯条", "麦乐鸡(5块)", "玉米杯", "香芋派"]
_BREAKFAST = ["猪柳蛋麦满分两件套", "吉士蛋麦满分两件套", "脆薯饼+豆浆", "枫糖厚松饼猪柳堡三件套"]


def _order(order_id, when, amount, channel, items, status="已完成"):
    return {
        "order_id": order_id,
        "status": status,
        "create_time": when.strftime("%Y-%m-%d %H:%M:%S"),
        "pay_amount": round(amount, 2),
        "order_type": channel,
        "items": [{"name": n} for n in items],
    }


def make_mock_orders(days=90, profile="commuter", seed=1024, now=None):
    """生成假订单。字段名与真实 MCP 订单的常见字段对齐，解析器零改动可用。

    默认 seed=1024（程序员节彩蛋）：该 seed 下 commuter 画像为月均约 12.7 单、
    早餐占比约 34%、外送占比约 58%，是较典型的「通勤党」分布。
    """
    now = now or _dt.datetime.now()
    rng = random.Random(seed + (0 if profile == "commuter" else 1000))

    if profile == "commuter":
        p_breakfast_wd, p_breakfast_we = 0.18, 0.08
        p_dinner_wd, p_dinner_we = 0.22, 0.40
        p_delivery = 0.5
    else:  # weekend
        p_breakfast_wd, p_breakfast_we = 0.03, 0.10
        p_dinner_wd, p_dinner_we = 0.08, 0.20
        p_delivery = 0.25

    orders = []
    seq = 10000
    day = _dt.timedelta(days=1)
    d = now - _dt.timedelta(days=days)
    while d <= now:
        wd = d.weekday()
        # 早餐单（05:00-10:30）
        p_bf = p_breakfast_wd if wd < 5 else p_breakfast_we
        if rng.random() < p_bf:
            seq += 1
            when = d.replace(
                hour=rng.randint(6, 9), minute=rng.randint(0, 59),
                second=rng.randint(0, 59),
            )
            amount = round(rng.uniform(6.6, 15.9), 2)
            channel = "takeout" if rng.random() > 0.25 else "delivery"
            orders.append(
                _order("MOCK-B-%d" % seq, when, amount, channel,
                       [rng.choice(_BREAKFAST)])
            )
        # 正餐单
        p_dn = p_dinner_wd if wd < 5 else p_dinner_we
        if rng.random() < p_dn:
            seq += 1
            hour = rng.choice([11, 12, 12, 13, 17, 18, 18, 19, 20])
            when = d.replace(hour=hour, minute=rng.randint(0, 59), second=rng.randint(0, 59))
            amount = round(rng.uniform(18.0, 45.0), 2)
            channel = "delivery" if rng.random() < p_delivery else "takeout"
            items = [rng.choice(_BURGERS), rng.choice(_SIDES)]
            orders.append(_order("MOCK-D-%d" % seq, when, amount, channel, items))
        d += day
    orders.sort(key=lambda o: o["create_time"], reverse=True)
    return orders


def make_mock_coupons(now=None):
    """我的优惠券：5 张未用，其中 2 张 3 天内过期。"""
    now = now or _dt.datetime.now()

    def _exp(days):
        return (now + _dt.timedelta(days=days)).strftime("%Y-%m-%d 23:59:59")

    return [
        {"name": "麦乐鸡(5块)立减券", "amount": 5.0, "expire_time": _exp(1), "status": "未使用"},
        {"name": "中薯条买一送一券", "amount": 6.0, "expire_time": _exp(2), "status": "未使用"},
        {"name": "麦辣鸡腿汉堡套餐满减券", "amount": 8.0, "expire_time": _exp(12), "status": "未使用"},
        {"name": "外送费立减券", "amount": 4.0, "expire_time": _exp(25), "status": "未使用"},
        {"name": "下午茶甜筒第二份半价券", "amount": 3.0, "expire_time": _exp(40), "status": "未使用"},
    ]


def make_mock_available_coupons():
    """麦麦省里可领未领的券。"""
    return [
        {"name": "早餐时段满20减6券", "amount": 6.0},
        {"name": "麦乐送满39减8券", "amount": 8.0},
        {"name": "新地立减3元券", "amount": 3.0},
    ]


def make_mock_account():
    """积分账户。"""
    return {
        "available_points": 850,
        "total_points": 3260,
        "frozen_points": 0,
        "expiring_points": 120,
    }
