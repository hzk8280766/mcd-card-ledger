"""麦当劳付费卡参数模型。

参数基于 2026-10 公开信息整理（麦当劳中国官网活动页、支付宝小程序等），
均为保守估计；可在 config.json 的 card_params 中覆盖，不必改代码。

口径说明：
- 麦金卡「免外送费」权益：麦乐送早餐时段实付满 19 元 / 正餐时段满 29 元免外送费，
  每天限 2 次。外送费按常见 6 元/单估计。
- 麦金卡「套餐专享价」权益：大堡口福 5 件套专享价 = 非持卡 4 件套价格，多一份派，
  按每单省 1 个派（约 7 元）估计；并非每单都点专享套餐，给 30% 命中率的保守系数。
- 早餐卡「6 折起」权益：实测每单省 5 ~ 8.6 元（双月卡 15.8 元时 3~4 顿回本）。
"""

DEFAULT_CARD_PARAMS = {
    "gold_month": {
        "display": "麦金卡（月卡）",
        "price": 19.9,
        "period_days": 30,
        "delivery_fee_saved": 6.0,
        "set_meal_save_per_order": 7.0,
        "set_meal_hit_rate": 0.3,
        "verdict_note": "配送权益按 6 元/单、套餐权益按 30% 命中率保守估算",
    },
    "breakfast_dual": {
        "display": "早餐卡（双月卡）",
        "price": 15.8,
        "price_official": 19.8,
        "period_days": 60,
        "save_per_order_low": 5.0,
        "save_per_order_high": 8.6,
        "verdict_note": "每单节省按实测 5~8.6 元区间估计",
    },
}

# 早餐时段（麦当劳早餐一般至上午 10:30 结束）
BREAKFAST_START_HOUR = 5
BREAKFAST_END_MINUTES = 10 * 60 + 30  # 10:30


def load_card_params(overrides=None):
    """合并用户配置覆盖，返回完整参数副本。"""
    import copy

    params = copy.deepcopy(DEFAULT_CARD_PARAMS)
    for card_key, card_cfg in (overrides or {}).items():
        if card_key in params and isinstance(card_cfg, dict):
            params[card_key].update(card_cfg)
    return params


def is_breakfast_time(hour, minute):
    """判断是否早餐时段：05:00 - 10:30。"""
    if hour < BREAKFAST_START_HOUR or hour >= 24:
        return False
    return hour * 60 + minute < BREAKFAST_END_MINUTES
