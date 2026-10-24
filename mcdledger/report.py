"""报告渲染：终端文本 + 单文件 HTML 卡片（可截图分享）。"""
from __future__ import annotations

import html
import string

# ---------- 毒舌点评 ----------


def build_roast(result):
    """基于真实数字的点评，毒舌但每句都有依据。最多输出 3 条。"""
    p = result["profile"]
    cards = {c["key"]: c for c in result["cards"]}
    b, g = cards.get("breakfast_dual"), cards.get("gold_month")
    cps = result.get("coupons", {})
    lines = []

    if p["total_orders"] == 0:
        return ["窗口内一笔订单都没有——你不是来回本的，你是来考古的。"]

    if p["breakfast_ratio"] < 0.05:
        lines.append(
            "早餐订单占比 %.0f%%，早餐卡对你就是一张精美的行为艺术门票。"
            % (p["breakfast_ratio"] * 100)
        )
    elif b and b["verdict"] == "yes":
        lines.append(
            "月均 %.1f 单早餐，按每单省 %.1f~%.1f 元算，早餐卡 %.1f 单就能回本——这是你离麦当劳财务自由最近的一次。"
            % (p["breakfast_per_month"], 5.0, 8.6, b["payback_orders_high"] or 0)
        )

    if p["delivery_per_month"] < 1:
        lines.append(
            "月均外送 %.1f 单，麦金卡最值钱的免配送费权益在你手里只能当收藏品。"
            % p["delivery_per_month"]
        )
    elif g and g["verdict"] == "yes" and g["payback_months"] is not None and g["payback_months"] < 1:
        lines.append(
            "麦金卡 %.1f 个月回本，四舍五入就是麦当劳倒贴你——不开卡建议列入年度遗憾清单。"
            % g["payback_months"]
        )

    if cps.get("expiring_3d", 0) > 0:
        lines.append(
            "你有 %d 张券 3 天内过期，总额度正在以肉眼可见的速度蒸发。券都不会用，先别惦记卡了。"
            % cps["expiring_3d"]
        )

    if p["monthly_spend"] > 0 and p["monthly_spend"] < 100:
        lines.append(
            "月均在麦当劳花 ¥%.0f，属于「偶尔想开」型用户。卡可以开，但别开出自责感。"
            % p["monthly_spend"]
        )

    if not lines:
        lines.append("你的消费画像平平无奇，两张卡的收益都刚过线——开不开都行，选了就别纠结。")
    return lines[:3]


# ---------- 终端报告 ----------

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"

_VERDICT_COLOR = {"yes": _GREEN, "no": _RED, "maybe": _YELLOW}


def _c(text, color, enabled=True):
    return color + text + _RESET if enabled else text


def _fmt_money(v):
    if v is None:
        return "—"
    return "¥%.1f" % v


def _fmt_months(v):
    if v is None:
        return "—"
    return "%.1f 个月" % v


def render_text(result, color=True):
    p = result["profile"]
    cards = {c["key"]: c for c in result["cards"]}
    b, g = cards.get("breakfast_dual"), cards.get("gold_month")
    cps = result.get("coupons", {})
    out = []
    w = out.append

    w("")
    w(_c("━" * 56, _CYAN, color))
    w(_c("  麦卡账房 · 麦当劳付费卡回本报告", _BOLD, color))
    w(_c("  生成 %s ｜ 数据窗口：近 %d 天 ｜ 非官方工具，数据来自你的账号"
         % (result["generated_at"], p["window_days"]), _DIM, color))
    w(_c("━" * 56, _CYAN, color))

    w("")
    w(_c("【你的消费画像】", _BOLD, color))
    w("  窗口内订单        %d 单%s" % (
        p["total_orders"],
        "（已跳过取消单 %d 单）" % p["skipped_cancelled"] if p["skipped_cancelled"] else ""))
    w("  月均订单          %.1f 单" % p["orders_per_month"])
    w("  早餐订单          %d 单（%.0f%%）  ← 早餐卡权益只在这段生效"
      % (p["breakfast_orders"], p["breakfast_ratio"] * 100))
    w("  麦乐送订单        %d 单（%.0f%%）  ← 免配送费权益的来源"
      % (p["delivery_orders"], p["delivery_ratio"] * 100))
    w("  客单价 / 月均花费  %s / %s"
      % (_fmt_money(p["avg_pay"]), _fmt_money(p["monthly_spend"])))
    if p["top_items"]:
        tops = "、".join("%s×%d" % (n, c) for n, c in p["top_items"])
        w("  常点 TOP3         %s" % tops)
    if p["no_timestamp"]:
        w(_c("  注意：%d 笔订单无时间戳，已保守计入" % p["no_timestamp"], _YELLOW, color))

    w("")
    w(_c("【%s】 %s / %d 天" % (b["display"], _fmt_money(b["price"]), b["period_days"]), _BOLD, color))
    w("  月摊卡费          %s" % _fmt_money(b["monthly_cost"]))
    w("  你的早餐频率      %.1f 单/月" % b["breakfast_per_month"])
    w("  月均可省          %s ~ %s（按每单省 5~8.6 元）"
      % (_fmt_money(b["monthly_save_low"]), _fmt_money(b["monthly_save_high"])))
    w("  回本所需早餐      %s ~ %s 单" % (b["payback_orders_low"], b["payback_orders_high"]))
    w("  预计回本周期      %s（保守）~ %s（乐观）"
      % (_fmt_months(b["payback_months_low"]), _fmt_months(b["payback_months_high"])))
    w("  月净收益          %s ~ %s"
      % (_fmt_money(b["net_monthly_low"]), _fmt_money(b["net_monthly_high"])))
    w("  %s %s" % (_c(b["verdict_label"], _VERDICT_COLOR.get(b["verdict"], ""), color),
                  _c("（%s）" % b["note"], _DIM, color)))

    w("")
    w(_c("【%s】 %s / %d 天" % (g["display"], _fmt_money(g["price"]), g["period_days"]), _BOLD, color))
    w("  月摊卡费          %s" % _fmt_money(g["monthly_cost"]))
    w("  配送费权益        %.1f 单/月 × ¥%.0f = %s/月"
      % (g["delivery_per_month"], 6.0, _fmt_money(g["delivery_value"])))
    w("  套餐专享权益      %.1f 单/月 × 30%% × ¥7 = %s/月（保守系数）"
      % (g["nonbreakfast_per_month"], _fmt_money(g["meal_value"])))
    w("  月权益价值        %s/月" % _fmt_money(g["monthly_value"]))
    w("  预计回本周期      %s" % _fmt_months(g["payback_months"]))
    w("  月净收益          %s/月" % _fmt_money(g["net_monthly"]))
    w("  %s %s" % (_c(g["verdict_label"], _VERDICT_COLOR.get(g["verdict"], ""), color),
                  _c("（%s）" % g["note"], _DIM, color)))

    w("")
    w(_c("【券资产盘点】", _BOLD, color))
    w("  未使用券          %d 张（合计面值 %s）"
      % (cps.get("unused_count", 0), _fmt_money(cps.get("unused_total_value", 0))))
    if cps.get("expiring_3d"):
        w(_c("  ⚠ %d 张 3 天内过期，优先用掉！" % cps["expiring_3d"], _RED, color))
    if cps.get("available_unclaimed"):
        w("  麦麦省可领未领    %d 张 → 先领券，再决定买卡" % cps["available_unclaimed"])

    w("")
    w(_c("【账房点评】", _BOLD, color))
    for line in build_roast(result):
        w("  · " + line)
    w("")
    w(_c("口径说明：权益折算均为保守估计，参数可在 config.json 调整；"
         "本工具与麦当劳官方无任何关联。", _DIM, color))
    w("")
    return "\n".join(out)


# ---------- HTML 卡片 ----------

_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: "PingFang SC", "Microsoft YaHei", "Helvetica Neue", sans-serif;
       background: #faf7f2; color: #2b2b2b; padding: 28px; }
.card { max-width: 860px; margin: 0 auto; background: #ffffff; border-radius: 16px;
        box-shadow: 0 4px 24px rgba(0,0,0,.08); overflow: hidden; }
.header { background: linear-gradient(135deg, #ffc72c 0%, #ffb000 100%);
          padding: 26px 32px; color: #3a2a00; }
.header h1 { font-size: 24px; letter-spacing: 1px; }
.header .sub { margin-top: 8px; font-size: 12px; opacity: .75; }
.section { padding: 22px 32px; border-bottom: 1px solid #f0ebe2; }
.section:last-child { border-bottom: none; }
.section h2 { font-size: 15px; color: #8a6d00; margin-bottom: 14px;
              letter-spacing: 2px; }
.stats { display: flex; gap: 14px; flex-wrap: wrap; }
.stat { flex: 1; min-width: 150px; background: #faf7f2; border-radius: 12px;
        padding: 14px 16px; }
.stat .num { font-size: 22px; font-weight: 700; color: #2b2b2b; }
.stat .lbl { font-size: 12px; color: #8b8b8b; margin-top: 4px; }
.cards { display: flex; gap: 16px; flex-wrap: wrap; }
.pcard { flex: 1; min-width: 300px; border: 1px solid #f0ebe2; border-radius: 12px;
         padding: 18px 20px; position: relative; }
.pcard .bar { position: absolute; top: 0; left: 0; right: 0; height: 4px;
              border-radius: 12px 12px 0 0; }
.pcard.yes .bar { background: #2e9e5b; }
.pcard.maybe .bar { background: #e8a13a; }
.pcard.no .bar { background: #d64545; }
.pcard h3 { font-size: 16px; margin: 6px 0 2px; }
.pcard .price { font-size: 12px; color: #8b8b8b; margin-bottom: 12px; }
.kv { display: flex; justify-content: space-between; font-size: 13px;
      padding: 5px 0; border-bottom: 1px dashed #f0ebe2; }
.kv:last-of-type { border-bottom: none; }
.kv .k { color: #8b8b8b; }
.kv .v { font-weight: 600; }
.verdict { margin-top: 12px; display: inline-block; font-size: 13px; font-weight: 700;
           padding: 4px 14px; border-radius: 999px; }
.pcard.yes .verdict { background: #e4f5ec; color: #2e9e5b; }
.pcard.maybe .verdict { background: #fdf3e0; color: #c07f10; }
.pcard.no .verdict { background: #fbe9e9; color: #d64545; }
.note { margin-top: 10px; font-size: 11px; color: #a8a8a8; }
.roast { background: #fff8e6; border-left: 4px solid #ffc72c; border-radius: 8px;
         padding: 14px 18px; font-size: 13px; line-height: 1.9; }
.roast li { margin-left: 18px; }
.footer { padding: 16px 32px; font-size: 11px; color: #a8a8a8; background: #faf7f2; }
.warn { color: #d64545; font-weight: 700; }
"""


def render_html(result, title="麦卡账房 · 麦当劳付费卡回本报告"):
    p = result["profile"]
    cards = {c["key"]: c for c in result["cards"]}
    b, g = cards.get("breakfast_dual"), cards.get("gold_month")
    cps = result.get("coupons", {})
    e = html.escape

    def money(v):
        return "—" if v is None else "¥%.1f" % v

    def months(v):
        return "—" if v is None else "%.1f 个月" % v

    def pcard(card, extra_rows):
        rows = "".join(
            '<div class="kv"><span class="k">%s</span><span class="v">%s</span></div>' % (e(k), e(v))
            for k, v in extra_rows
        )
        return """
<div class="pcard %(cls)s"><div class="bar"></div>
  <h3>%(title)s</h3>
  <div class="price">%(price)s / %(days)d 天 ｜ 月摊 %(cost)s</div>
  %(rows)s
  <span class="verdict">%(verdict)s</span>
  <div class="note">%(note)s</div>
</div>""" % {
            "cls": card["verdict"], "title": e(card["display"]),
            "price": money(card["price"]), "days": card["period_days"],
            "cost": money(card["monthly_cost"]), "rows": rows,
            "verdict": e(card["verdict_label"]), "note": e(card["note"]),
        }

    b_rows = [
        ("你的早餐频率", "%.1f 单/月" % b["breakfast_per_month"]),
        ("月均可省", "%s ~ %s" % (money(b["monthly_save_low"]), money(b["monthly_save_high"]))),
        ("回本所需", "%s ~ %s 单" % (b["payback_orders_low"], b["payback_orders_high"])),
        ("预计回本周期", "%s ~ %s" % (months(b["payback_months_low"]), months(b["payback_months_high"]))),
        ("月净收益", "%s ~ %s" % (money(b["net_monthly_low"]), money(b["net_monthly_high"]))),
    ]
    g_rows = [
        ("免配送费权益", "%s/月" % money(g["delivery_value"])),
        ("套餐专享权益", "%s/月" % money(g["meal_value"])),
        ("月权益价值", "%s/月" % money(g["monthly_value"])),
        ("预计回本周期", months(g["payback_months"])),
        ("月净收益", "%s/月" % money(g["net_monthly"])),
    ]

    roast_items = "".join("<li>%s</li>" % e(x) for x in build_roast(result))
    tops = "、".join("%s×%d" % (e(str(n)), c) for n, c in p["top_items"])
    expiring = ('<span class="warn">⚠ %d 张 3 天内过期，优先用掉！</span>'
                % cps["expiring_3d"]) if cps.get("expiring_3d") else ""

    return string.Template("""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title</title>
<style>$css</style>
</head>
<body>
<div class="card">
  <div class="header">
    <h1>🍔 麦卡账房 · 麦当劳付费卡回本报告</h1>
    <div class="sub">生成于 $generated_at ｜ 数据窗口：近 $window_days 天 ｜ 共 $total_orders 笔订单 ｜ 非官方工具</div>
  </div>

  <div class="section">
    <h2>你的消费画像</h2>
    <div class="stats">
      <div class="stat"><div class="num">$orders_pm</div><div class="lbl">月均订单（单）</div></div>
      <div class="stat"><div class="num">$bf_ratio</div><div class="lbl">早餐订单占比</div></div>
      <div class="stat"><div class="num">$dl_ratio</div><div class="lbl">麦乐送订单占比</div></div>
      <div class="stat"><div class="num">$monthly_spend</div><div class="lbl">月均花费</div></div>
    </div>
    $tops_line
  </div>

  <div class="section">
    <h2>两张卡的回本测算</h2>
    <div class="cards">$b_card$g_card</div>
  </div>

  <div class="section">
    <h2>券资产盘点</h2>
    <div class="kv"><span class="k">未使用券</span><span class="v">$unused_count 张（面值 $unused_value）</span></div>
    <div class="kv"><span class="k">麦麦省可领未领</span><span class="v">$available_count 张（先领券，再决定买卡）</span></div>
    $expiring
  </div>

  <div class="section">
    <h2>账房点评</h2>
    <div class="roast"><ul>$roast</ul></div>
  </div>

  <div class="footer">
    口径说明：权益折算均为保守估计（配送费 6 元/单、套餐权益 30% 命中率、早餐每单省 5~8.6 元），
    参数可在 config.json 中调整。本工具由 mcd-card-ledger 生成，与麦当劳官方无任何关联，
    数据仅来自你本人的麦当劳账号。
  </div>
</div>
</body>
</html>""").substitute({
        "title": e(title), "css": _CSS,
        "generated_at": e(result["generated_at"]),
        "window_days": p["window_days"], "total_orders": p["total_orders"],
        "orders_pm": "%.1f" % p["orders_per_month"],
        "bf_ratio": "%.0f%%" % (p["breakfast_ratio"] * 100),
        "dl_ratio": "%.0f%%" % (p["delivery_ratio"] * 100),
        "monthly_spend": money(p["monthly_spend"]),
        "tops_line": ('<div class="kv" style="margin-top:12px"><span class="k">常点 TOP3</span>'
                      '<span class="v">%s</span></div>' % tops) if tops else "",
        "b_card": pcard(b, b_rows), "g_card": pcard(g, g_rows),
        "unused_count": cps.get("unused_count", 0),
        "unused_value": money(cps.get("unused_total_value", 0)),
        "available_count": cps.get("available_unclaimed", 0),
        "expiring": expiring, "roast": roast_items,
    })
