"""消费画像 + 回本测算引擎。

设计原则：
1. 宽容解析：MCP 订单字段结构以官方文档为准但可能调整，
   这里对时间/金额/渠道/餐品都做多候选字段解析，解析不到就跳过并计数。
2. 保守口径：所有权益折算都取保守值，宁可低估不建议错。
3. 可解释：每个结论都附带推导所需的原始数字，不做黑盒。
"""
from __future__ import annotations

import datetime as _dt
import re
from collections import Counter

from .cards import is_breakfast_time

# ---------- 候选字段（按优先级排列） ----------

TIME_FIELDS = ["create_time", "order_time", "pay_time", "created_at", "submit_time", "orderDate"]
AMOUNT_FIELDS = ["pay_amount", "actual_pay", "payAmount", "total_amount", "paid_amount",
                 "amount", "final_amount", "orderAmount", "payMoney"]
STATUS_FIELDS = ["status", "order_status", "state", "orderStatus"]
CHANNEL_FIELDS = ["order_type", "eat_type", "channel", "orderType", "scene",
                  "delivery_type", "take_type", "orderMode"]
ITEMS_FIELDS = ["items", "products", "order_items", "meals", "foods", "details"]
ID_FIELDS = ["order_id", "orderId", "id"]

COUPON_NAME_FIELDS = ["name", "title", "coupon_name", "couponName"]
COUPON_AMOUNT_FIELDS = ["amount", "value", "denomination", "discount", "reduce"]
COUPON_EXPIRE_FIELDS = ["expire_time", "expiry", "end_time", "validity_end",
                        "expired_time", "expireTime", "valid_until"]
COUPON_STATUS_FIELDS = ["status", "state", "use_status"]

CANCELLED_KEYWORDS = ("cancel", "取消", "已取消", "refund", "退款")


# ---------- 基础解析 ----------

def _pick(d, fields, default=None):
    if not isinstance(d, dict):
        return default
    for f in fields:
        if f in d and d[f] not in (None, ""):
            return d[f]
    return default


def parse_time(value):
    """把各种时间表示解析为 datetime；失败返回 None。"""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        ts = float(value)
        if ts > 1e12:  # 毫秒时间戳
            ts /= 1000.0
        try:
            return _dt.datetime.fromtimestamp(ts)
        except (OverflowError, OSError, ValueError):
            return None
    s = str(value).strip()
    if not s:
        return None
    if re.fullmatch(r"\d{10,13}", s):
        return parse_time(int(s))
    fmts = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f",
            "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d")
    for fmt in fmts:
        try:
            return _dt.datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        return _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_amount(value):
    """从 '12.90元' / 12.9 / '￥12.9' 中提取浮点数。"""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    s = str(value).replace("￥", "").replace("¥", "").replace(",", "").strip()
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def classify_channel(order):
    """返回 delivery / takeout / dinein / unknown。"""
    raw = str(_pick(order, CHANNEL_FIELDS, "") or "")
    low = raw.lower()
    if any(k in low for k in ("delivery", "麦乐送", "外送", "外卖", "配送", "送餐")):
        return "delivery"
    if any(k in low for k in ("take", "pick", "取餐", "自提", "得来速")):
        return "takeout"
    if any(k in low for k in ("dine", "堂食", "eat_in", "eat in", "instore")):
        return "dinein"
    return "unknown"


def _extract_items(order):
    raw = _pick(order, ITEMS_FIELDS, [])
    names = []
    if isinstance(raw, list):
        for it in raw:
            if isinstance(it, dict):
                nm = _pick(it, ["name", "title", "product_name", "food_name"], "")
                if nm:
                    names.append(str(nm))
            elif isinstance(it, str):
                names.append(it)
    return names


def extract_order_list(raw):
    """把 MCP 返回的各种包装形态统一成订单 dict 列表。"""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [o for o in raw if isinstance(o, dict)]
    if isinstance(raw, dict):
        for key in ("orders", "data", "list", "result", "items", "records"):
            v = raw.get(key)
            if isinstance(v, list):
                return [o for o in v if isinstance(o, dict)]
            if isinstance(v, dict):
                for k2 in ("list", "records", "items"):
                    if isinstance(v.get(k2), list):
                        return [o for o in v[k2] if isinstance(o, dict)]
        if _pick(raw, ID_FIELDS) is not None:
            return [raw]
    return []


def is_cancelled(order):
    status = str(_pick(order, STATUS_FIELDS, "") or "").lower()
    return any(k in status for k in CANCELLED_KEYWORDS)


# ---------- 消费画像 ----------

def build_profile(raw_orders, now=None, days=90):
    """从原始订单生成消费画像。"""
    now = now or _dt.datetime.now()
    window_start = now - _dt.timedelta(days=days)

    orders = extract_order_list(raw_orders)
    counted, skipped_cancel, no_time = [], 0, 0
    for o in orders:
        if is_cancelled(o):
            skipped_cancel += 1
            continue
        t = parse_time(_pick(o, TIME_FIELDS))
        if t is None:
            no_time += 1  # 无时间戳的保守计入
            counted.append((o, None))
            continue
        if t >= window_start:
            counted.append((o, t))

    n = len(counted)
    months = max(days / 30.0, 0.5)
    pays, breakfast, delivery, items = [], 0, 0, Counter()
    for o, t in counted:
        amt = parse_amount(_pick(o, AMOUNT_FIELDS))
        if amt is not None:
            pays.append(amt)
        if t is not None and is_breakfast_time(t.hour, t.minute):
            breakfast += 1
        if classify_channel(o) == "delivery":
            delivery += 1
        for nm in _extract_items(o):
            items[nm] += 1

    profile = {
        "window_days": days,
        "total_orders": n,
        "skipped_cancelled": skipped_cancel,
        "no_timestamp": no_time,
        "months": round(months, 2),
        "orders_per_month": round(n / months, 1) if n else 0.0,
        "breakfast_orders": breakfast,
        "breakfast_ratio": round(breakfast / n, 3) if n else 0.0,
        "breakfast_per_month": round(breakfast / months, 1) if n else 0.0,
        "delivery_orders": delivery,
        "delivery_ratio": round(delivery / n, 3) if n else 0.0,
        "delivery_per_month": round(delivery / months, 1) if n else 0.0,
        "avg_pay": round(sum(pays) / len(pays), 1) if pays else 0.0,
        "monthly_spend": round(sum(pays) / months, 1) if pays else 0.0,
        "top_items": items.most_common(3),
    }
    return profile


# ---------- 回本测算 ----------

def _monthly_cost(card):
    return card["price"] / (card["period_days"] / 30.0)


def evaluate_breakfast_card(profile, card):
    """早餐卡测算：权益只在早餐时段生效，每单省 5~8.6 元。"""
    bpm = profile["breakfast_per_month"]
    save_low = bpm * card["save_per_order_low"]
    save_high = bpm * card["save_per_order_high"]
    cost = _monthly_cost(card)
    # 整张卡周期内回本所需早餐单数（保守/乐观两档）
    orders_low = card["price"] / card["save_per_order_low"]
    orders_high = card["price"] / card["save_per_order_high"]
    if bpm > 0:
        months_low = orders_low / bpm
        months_high = orders_high / bpm
    else:
        months_low = months_high = float("inf")

    if bpm <= 0:
        verdict, verdict_label = "no", "不建议开通"
    elif save_low > cost:
        verdict, verdict_label = "yes", "建议开通"
    elif save_high <= cost:
        verdict, verdict_label = "no", "不建议开通"
    else:
        verdict, verdict_label = "maybe", "可以观望"

    return {
        "key": "breakfast_dual",
        "display": card["display"],
        "price": card["price"],
        "period_days": card["period_days"],
        "monthly_cost": round(cost, 1),
        "breakfast_per_month": bpm,
        "monthly_save_low": round(save_low, 1),
        "monthly_save_high": round(save_high, 1),
        "payback_orders_low": round(orders_low, 1),
        "payback_orders_high": round(orders_high, 1),
        "payback_months_low": None if months_low == float("inf") else round(months_low, 1),
        "payback_months_high": None if months_high == float("inf") else round(months_high, 1),
        "net_monthly_low": round(save_low - cost, 1),
        "net_monthly_high": round(save_high - cost, 1),
        "verdict": verdict,
        "verdict_label": verdict_label,
        "note": card.get("verdict_note", ""),
    }


def evaluate_gold_card(profile, card):
    """麦金卡测算：免外送费权益 + 套餐专享价权益（保守系数）。"""
    dpm = profile["delivery_per_month"]
    delivery_value = dpm * card["delivery_fee_saved"]
    nonbreakfast_pm = max(profile["orders_per_month"] - profile["breakfast_per_month"], 0.0)
    meal_value = nonbreakfast_pm * card["set_meal_hit_rate"] * card["set_meal_save_per_order"]
    monthly_value = delivery_value + meal_value
    cost = _monthly_cost(card)
    payback_months = (card["price"] / monthly_value) if monthly_value > 0 else float("inf")

    if monthly_value <= 0:
        verdict, verdict_label = "no", "不建议开通"
    elif monthly_value - cost > card["price"] * 0.2:
        verdict, verdict_label = "yes", "建议开通"
    elif monthly_value <= cost:
        verdict, verdict_label = "no", "不建议开通"
    else:
        verdict, verdict_label = "maybe", "可以观望"

    return {
        "key": "gold_month",
        "display": card["display"],
        "price": card["price"],
        "period_days": card["period_days"],
        "monthly_cost": round(cost, 1),
        "delivery_per_month": dpm,
        "delivery_value": round(delivery_value, 1),
        "nonbreakfast_per_month": round(nonbreakfast_pm, 1),
        "meal_value": round(meal_value, 1),
        "monthly_value": round(monthly_value, 1),
        "payback_months": None if payback_months == float("inf") else round(payback_months, 2),
        "net_monthly": round(monthly_value - cost, 1),
        "verdict": verdict,
        "verdict_label": verdict_label,
        "note": card.get("verdict_note", ""),
    }


# ---------- 券资产检查 ----------

def check_coupons(my_raw, available_raw, now=None):
    """盘点未用券、临近过期券、可领未领券。"""
    now = now or _dt.datetime.now()
    my_list = my_raw if isinstance(my_raw, list) else extract_order_list(my_raw)
    avail_list = available_raw if isinstance(available_raw, list) else extract_order_list(available_raw)

    unused, expiring_soon, total_value = 0, 0, 0.0
    for c in my_list:
        if not isinstance(c, dict):
            continue
        status = str(_pick(c, COUPON_STATUS_FIELDS, "") or "")
        if any(k in status for k in ("已使用", "已过期", "used", "expired")):
            continue
        unused += 1
        amt = parse_amount(_pick(c, COUPON_AMOUNT_FIELDS))
        if amt:
            total_value += amt
        exp = parse_time(_pick(c, COUPON_EXPIRE_FIELDS))
        if exp and 0 <= (exp - now).days <= 3:
            expiring_soon += 1

    return {
        "unused_count": unused,
        "unused_total_value": round(total_value, 1),
        "expiring_3d": expiring_soon,
        "available_unclaimed": len(avail_list),
    }


# ---------- 汇总 ----------

def analyze(raw_orders, my_coupons=None, available_coupons=None, account=None,
            card_params=None, now=None, days=90):
    now = now or _dt.datetime.now()
    from .cards import load_card_params

    params = load_card_params(card_params)
    profile = build_profile(raw_orders, now=now, days=days)
    breakfast = evaluate_breakfast_card(profile, params["breakfast_dual"])
    gold = evaluate_gold_card(profile, params["gold_month"])
    coupons = check_coupons(my_coupons, available_coupons, now=now)

    return {
        "generated_at": now.strftime("%Y-%m-%d %H:%M"),
        "profile": profile,
        "cards": [breakfast, gold],
        "coupons": coupons,
        "account": account or {},
    }
