# -*- coding: utf-8 -*-
"""物料原材料价格趋势库 —— 静态 HTML 生成器（零 JavaScript / 纯 CSS + 内联 SVG，兼容企微浏览器）
对齐供应链知识库设计体系：顶栏 + 悬停展开侧边栏 + 分析报告卡 + 走势点评 + 异动预警 + 历史走势 + 报价明细大表（radio 纯 CSS 筛选）
用法: python build_price_html.py [input.json] [output.html]
"""
import json
import re
import sys
import shutil
import html as H
from pathlib import Path

# ============================================================
# Schema 兼容层：v1.0 indicators 格式 → 旧 materials/groups 格式
# ============================================================
def is_v1_format(data):
    return data.get("schema_version") == "1.0" and "indicators" in data


def adapt_v1_to_old(data_v1):
    """把 Schema v1.0 转成旧格式，让 build() 无需改动即可使用"""
    meta = data_v1.get("meta", {})
    indicators = data_v1.get("indicators", [])
    groups_v1 = data_v1.get("groups", [])
    reports = data_v1.get("reports", {})
    trend_reports = data_v1.get("trend_reports", [])

    # 重建 materials（大类列表 + 大类指数 history）
    materials = []
    for g in groups_v1:
        mat_id = g["category_code"]
        mat_name = g["category_name"]
        icon = g.get("icon", "")

        # 找大类指数 indicator
        idx_code = f"{mat_id.upper()}_IDX"
        idx_ind = None
        for ind in indicators:
            if ind.get("is_index") and ind["indicator_code"].startswith(idx_code.split('_')[0]):
                # 简化匹配：找 is_index 且 category 匹配的
                if ind["definition"]["category"] == mat_name:
                    idx_ind = ind
                    break

        mat_entry = {"id": mat_id, "name": mat_name, "icon": icon}
        if idx_ind:
            hist_flat = idx_ind.get("history", [])
            # 按近1月/近1季度/近1年分组
            periods = _group_history_to_periods(hist_flat)
            calc = idx_ind.get("calculated", {})
            mat_entry["history"] = {
                "ref": idx_ind["name"],
                "unit": idx_ind["definition"]["unit"],
                "current": calc.get("center_price", 0),
                "periods": periods,
            }
        materials.append(mat_entry)

    # 重建 groups（细分品类 + items）
    groups = []
    ind_by_code = {ind["indicator_code"]: ind for ind in indicators}

    for g in groups_v1:
        mat_id = g["category_code"]
        for sg in g["subgroups"]:
            items = []
            group_history = None
            for i, code in enumerate(sg["indicator_codes"]):
                ind = ind_by_code.get(code)
                if not ind:
                    continue
                calc = ind.get("calculated", {})
                item = {
                    "name": ind["name"],
                    "spec": ind["definition"]["specification"],
                    "origin": ind["definition"]["market"],
                    "price": calc.get("center_price", 0),
                }
                if ind.get("focus"):
                    item["focus"] = True
                items.append(item)

                # 第一个 item 带 history（如果有）
                if i == 0 and ind.get("history"):
                    periods = _group_history_to_periods(ind["history"])
                    if periods:
                        group_history = {
                            "ref": ind["name"],
                            "unit": ind["definition"]["unit"],
                            "current": calc.get("center_price", 0),
                            "periods": periods,
                        }

            group_entry = {
                "material": mat_id,
                "name": sg["sub_name"],
                "unit": sg.get("unit", ""),
                "source": sg.get("source", ""),
                "items": items,
            }
            if group_history:
                group_entry["history"] = group_history
            groups.append(group_entry)

    # 重建 meta.trend（从 trend_reports 还原）
    meta_out = dict(meta)
    if trend_reports:
        meta_out["trend"] = [
            f"【{t['category']}】{t['content']}" for t in trend_reports
        ]

    return {
        "meta": meta_out,
        "materials": materials,
        "groups": groups,
        "reports": reports,
    }


def _group_history_to_periods(flat_hist):
    """扁平 history → 近1月/近1季度/近1年 periods（旧格式）"""
    if not flat_hist:
        return []

    # 取最新日期
    latest = flat_hist[-1]["date"]
    from datetime import datetime, timedelta
    latest_dt = datetime.strptime(latest, "%Y-%m-%d").date()

    def filter_days(days):
        cutoff = latest_dt - timedelta(days=days)
        result = []
        for h in flat_hist:
            hd = datetime.strptime(h["date"], "%Y-%m-%d").date()
            if hd >= cutoff:
                # 旧格式用 MM-DD
                label = h["date"][5:]
                result.append([label, h["center_price"]])
        return result

    periods = []
    for name, days in [("近1月", 30), ("近1季度", 90), ("近1年", 365)]:
        data = filter_days(days)
        if len(data) >= 2:
            periods.append({"name": name, "data": data})
    return periods

UP, DOWN, FLAT = "#DC2626", "#059669", "#2563EB"
TREND_ICONS = {
    "化纤": "🧪", "羽绒": "🪶", "棉·麻·丝": "🌿", "毛·特种动物纤维": "🐑",
    "皮毛草": "🐄", "五金·皮革": "🔩", "辅料·纱线·缝纫线": "🧶", "采购总建议": "🛒",
}
LVL_CLS = {"预警": "alert", "重点跟踪": "track", "关注": "watch", "低风险": "safe"}
FILL_CLS = lambda s: "high" if s >= 70 else ("mid" if s >= 40 else "low")
DIM_CLS = lambda s: "up" if s >= 70 else ("flat" if s >= 55 else "down")

# ---- 外部价格源（向外洞察 · 半月刷新，2026-09-25 核实） ----
EXT_REFRESH = "每月 10 日 / 25 日 09:00"
EXT_RHYTHM = [
    ("t-p0", "P0 · 每次必刷", "8 个核心指数源", "化纤 · 生丝 · 棉花(内外双锚) · 羽绒 · 羊毛 · 五金基价 —— 覆盖库内高权重四大组，10 分钟完成取数"),
    ("t-p1", "P1 · 半月轮刷", "10 个行情补充源", "按当期异动品类轮换刷取：聚酯链开工/库存、国际澳毛拍卖、期货联动、纱线指数 —— 与 P0 交叉验证"),
    ("t-macro", "宏观 · 每次必看", "3 个传导指标", "原油（化纤成本端）· USD/CNY 汇率（进口羊毛/皮革）· PPI（全链传导确认）—— 10 日刷新恰逢上月 PPI 发布"),
]
# (名称, URL, 覆盖, 关键指标, 频率, 免费程度cls, 库内引用, 是否新增)
EXT_SOURCES = {
    "P0": [
        ("生意社", "https://www.100ppi.com", "化纤/涤纶/PTA/生丝/粘胶/氨纶", "涤纶 POY/FDY/DTY 基准价", "每日", "b-part", "★ 12 次", 0),
        ("中国茧丝绸网", "https://www.esilk.net", "生丝/蚕丝", "CCSE 高品质生丝指数（每周五 16:30）", "每周五", "b-free", "丝类主源", 1),
        ("柯桥纺织指数", "http://www.kqindex.cn", "全产业链（商务部授权）", "总类/原料类/坯布类价格指数", "每周一", "b-free", "★ 11 次", 0),
        ("羽绒金网", "https://www.cn-down.com", "羽绒", "GB/T 14272 口径 90% 绒价", "每日", "b-free", "★ 6 次", 0),
        ("南京羊毛市场", "https://www.woolmarket.com.cn", "羊毛/羊绒/毛纺原料", "澳毛 EMI 指数、毛纺周报价", "日报+周报", "b-free", "★ 5 次", 0),
        ("中国棉花协会", "https://www.china-cotton.org", "棉花", "CCIndex 3128B、FC Index M", "每日/周/月", "b-free", "★ 7 次", 0),
        ("Cotlook A 指数", "https://www.cotlook.com", "国际棉花现货", "A Index（与 CCIndex 内外双锚）", "每日", "b-free", "国际锚", 1),
        ("长江有色金属网", "https://www.ccmn.cn", "五金金属基价", "铜/铝/锌现货价（首页直看）", "每日", "b-free", "五金 6 条", 1),
    ],
    "P1": [
        ("CCF 化纤信息网", "https://www.ccf.com.cn", "聚酯链 PX→PTA→长丝", "长丝均价、开工率、库存、利润", "每日", "b-part", "化纤补充", 0),
        ("CCF 英文站", "https://www.ccfgroup.com", "聚酯/锦纶/氨纶/粘胶", "各产品月度日历价格表", "月度", "b-part", "出口参考", 1),
        ("中纤网", "https://www.ccfei.com", "化纤", "涤纶/锦纶/粘胶/氨纶报价", "每日", "b-part", "化纤补充", 0),
        ("盛泽丝绸化纤指数", "http://index.168tex.com", "化纤面料/丝绸", "每日涨跌榜、盛泽 50 指数", "每日", "b-free", "2 次", 0),
        ("中国羽绒信息网", "https://cfd.com.cn", "羽绒", "多国标成品绒均价、下周预测", "每周", "b-free", "5 次", 0),
        ("AWEX 澳洲羊毛交易所", "https://awex.com.au", "澳毛拍卖（国际锚）", "EMI 东部市场指数、周度拍卖报告", "每周", "b-part", "羊毛国际锚", 1),
        ("上海有色网 SMM", "https://www.smm.cn", "铜/铝/锌", "SMM 1# 电解铜、A00 铝", "工作日", "b-part", "五金交叉", 1),
        ("中国纱线网", "https://www.chinayarn.com", "棉纱/混纺纱", "棉纱价格指数、采购行情", "不定期", "b-part", "纱线 5 条", 1),
        ("新浪财经·期货", "https://finance.sina.com.cn", "郑棉/PTA/短纤/原油期货", "主力合约实时行情（期现联动预警）", "实时", "b-free", "期现联动", 1),
        ("东方财富·期货", "https://data.eastmoney.com", "全品种期货", "实时行情、持仓结构（资金动向）", "每日", "b-free", "持仓验证", 1),
    ],
    "P2": [
        ("Mysteel 大宗板块", "https://www.mysteel.com", "织造开工率/坯布库存", "织造样本企业综合开工率", "每周", "b-part", "需求侧验证", 0),
        ("嘉兴茧丝绸市场", "http://www.eccse.net", "蚕丝/生丝/绸缎", "嘉兴指数、3A 20/22D 生丝", "每周", "b-free", "4 次", 0),
        ("郑州商品交易所", "http://www.czce.com.cn", "郑棉期货", "郑棉主力合约", "每日", "b-free", "期现联动", 0),
        ("全球纺织网", "https://www.tnc.com.cn", "化纤/面料行情汇总", "涤纶/锦纶长丝月内涨幅汇总", "每日", "b-free", "行情交叉", 0),
        ("中国麻纺织行业协会", "http://www.cblfta.org.cn", "苎麻/亚麻/黄麻", "麻原料进口量价（海关口径）", "月度/季度", "b-free", "麻类月报", 0),
        ("中国化学纤维工业协会", "https://www.ccfa.com.cn", "化纤全行业", "锦纶/涤纶利润、产量运行分析", "月度/年度", "b-free", "行业景气", 0),
        ("永康五金指数", "https://www.ykindex.com", "五金市场", "五金交易周价格总指数（零注册）", "每周", "b-free", "五金宏观", 1),
        ("IWTO 国际羊毛纺织组织", "https://www.iwto.org", "羊毛全球统计", "Statistics、Market Information", "半年", "b-part", "羊毛背景", 1),
        ("ICE 棉花期货", "https://www.ice.com", "国际棉花期货", "Cotton No.2（CT）合约", "每日", "b-part", "国际预期", 1),
    ],
    "POOL": [
        ("1688 批发行情", "https://s.1688.com", "拉链/纽扣/衬布/缝纫线/五金件", "按关键词搜索批发价区间，取中位数比价", "b-free", "辅料 26 条"),
        ("海宁皮革城", "https://www.haining.com", "皮革/皮草产业", "仅产业新闻入口，靠市场询价+生意社皮革频道交叉", "b-free", "皮毛草 8 条"),
        ("生意社皮革频道", "https://www.100ppi.com", "牛皮/PU/PVC", "皮革原料报价页，与海宁询价交叉", "b-part", "皮革 6 条"),
    ],
    "MACRO": [
        ("WTI / 布伦特原油", "https://finance.sina.com.cn/money/future/", "原油期货", "油价 ±5% 触发聚酯链预警（传导 2-4 周）", "实时", "b-free", "化纤 33 条", 0),
        ("USD/CNY 汇率", "https://www.chinamoney.com.cn/chinese/sddshl/", "外汇交易中心", "即期+中间价，贬值推高进口澳毛/原皮/五金成本", "工作日", "b-free", "羊毛/皮革/五金", 0),
        ("PPI 工业生产者价格", "https://www.stats.gov.cn/sj/zxfb/", "国家统计局", "每月 9 日左右发布上月值，10 日刷新第一时间解读", "月度", "b-free", "全链成本确认", 0),
    ],
}
# (色块, 链名+条数, [节点…]) 节点: ("src"|"dst"|"", 文本)
EXT_CHAINS = [
    ("#0B2E59", "化纤链 · 33 条", [("src", "原油 WTI/布伦特"), ("", "PX"), ("", "PTA / MEG"), ("", "涤纶长丝 POY/FDY/DTY"), ("dst", "缝纫线·里布·涤纶面料")]),
    ("#14489E", "羊毛链 · 5 条", [("src", "澳毛拍卖 EMI（AWEX）"), ("", "南京羊毛市场周报"), ("dst", "羊毛纱线·呢料"), ("src", "USD/CNY 汇率")]),
    ("#2563EB", "棉纱链 · 8 条", [("src", "Cotlook A + CCIndex"), ("", "郑棉期货预期"), ("", "棉纱价格指数"), ("dst", "棉布·棉辅料")]),
    ("#D97706", "五金链 · 6 条", [("src", "LME / 长江有色 / SMM 铜铝锌"), ("", "锌合金/铜合金/铝合金基价"), ("", "+加工费（1688 比价）"), ("dst", "拉链头·扣件·装饰件")]),
    ("#059669", "羽绒链 · 6 条", [("src", "羽绒金网 + 中国羽绒信息网"), ("", "90% 绒价（多国标交叉）"), ("dst", "白鸭绒·白鹅绒填充")]),
]
EXT_SOP = [
    ("1", "取数", "P0 八源全刷 + P1 按当期异动品类轮刷 + 宏观三项（油价/汇率/PPI）", "外部原始报价快照", "09:00–10:00"),
    ("2", "比价", "与库内 131 条报价逐一对比，计算价差 % 与方向", "内外价差清单", "10:00–10:30"),
    ("3", "异动识别", "±5% 异动分级（预警/重点跟踪/关注），结合传导链判断持续性", "异动预警清单", "10:30–11:00"),
    ("4", "数据更新", "更新 material_prices JSON（保留结构）→ 重跑 build_price_html.py", "刷新版趋势库页面", "11:00–11:30"),
    ("5", "洞察产出", "半月外部洞察简报：核心结论 / 内外价差 / 传导链异动 / 采购行动建议", "洞察简报 HTML", "11:30–12:00"),
    ("6", "发布分享", "部署 GitHub Pages → 企微分享（零 JS 页面直接转发）", "在线地址 + 企微推送", "当日中午前"),
]


def esc(s):
    return H.escape(str(s), quote=False)


def fmt_num(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(v - round(v)) < 1e-9:
        return f"{int(round(v)):,}"
    s = f"{v:,.2f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def fmt_price(v):
    return "¥" + fmt_num(v)


def parse_points(data):
    pts = []
    for d in data or []:
        if isinstance(d, (list, tuple)):
            pts.append((str(d[0]), float(d[1])))
        else:
            m = re.match(r"^\s*(\S+)\s+([\d.]+)\s*$", str(d))
            if m:
                pts.append((m.group(1), float(m.group(2))))
    return pts


def chg_pct(pts):
    if len(pts) < 2 or pts[0][1] == 0:
        return None
    return (pts[-1][1] - pts[0][1]) / pts[0][1] * 100.0


def period_chg(hist, name):
    for p in hist.get("periods") or []:
        if p.get("name") == name:
            return chg_pct(parse_points(p.get("data")))
    return None


def mom_of(hist):
    return period_chg(hist, "近1月")


def _stdev(vals):
    if len(vals) < 2:
        return 0.0
    mean = sum(vals) / len(vals)
    return (sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)) ** 0.5


def _pearson(a, b):
    n = min(len(a), len(b))
    if n < 3:
        return None
    a, b = a[-n:], b[-n:]
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    va = sum((x - ma) ** 2 for x in a) ** 0.5
    vb = sum((y - mb) ** 2 for y in b) ** 0.5
    if va == 0 or vb == 0:
        return None
    return cov / (va * vb)


def _sig(x):
    return 1 if (x or 0) > 0.05 else (-1 if (x or 0) < -0.05 else 0)


def deep_analysis(materials):
    """三期动能 / 年内位置 / 波动率 / 品类联动（近1年收益率 Pearson）"""
    cats = []
    for m in materials:
        h = m.get("history") or {}
        y_pts = None
        for p in h.get("periods") or []:
            if p.get("name") == "近1年":
                y_pts = parse_points(p.get("data"))
        if not y_pts:
            continue
        vals = [v for _, v in y_pts]
        rets = [(vals[i] - vals[i - 1]) / vals[i - 1] * 100 for i in range(1, len(vals)) if vals[i - 1] > 0]
        lo, hi = min(vals), max(vals)
        mom, qoq, yoy = period_chg(h, "近1月"), period_chg(h, "近1季度"), chg_pct(y_pts)
        s1, s2, s3 = _sig(mom), _sig(qoq), _sig(yoy)
        cats.append({
            "id": m["id"], "name": m["name"], "icon": m.get("icon", ""),
            "mom": mom, "qoq": qoq, "yoy": yoy,
            "pos": (vals[-1] - lo) / (hi - lo) * 100 if hi > lo else 50.0,
            "vol": _stdev(rets), "lo": lo, "hi": hi, "rets": rets,
            "consist": s1 == s2 == s3 and s1 != 0, "sig": s3,
        })
    corr = {}
    for i, a in enumerate(cats):
        for b in cats[i:]:
            corr[(a["id"], b["id"])] = _pearson(a["rets"], b["rets"])
    return cats, corr


_SPARK_SEQ = [0]


def spark_svg(pts, color):
    w, h, pad = 260, 66, 8
    n = len(pts)
    if n < 2:
        return ""
    vals = [v for _, v in pts]
    lo, hi = min(vals), max(vals)
    if hi == lo:
        lo, hi = lo - 1, hi + 1
    span = hi - lo
    P = [(pad + (w - 2 * pad) * i / (n - 1), pad + (h - 2 * pad) * (1 - (v - lo) / span))
         for i, (_, v) in enumerate(pts)]
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in P)
    area = f"{poly} {P[-1][0]:.1f},{h - pad:.1f} {P[0][0]:.1f},{h - pad:.1f}"
    gid = f"sg{_SPARK_SEQ[0]}"
    _SPARK_SEQ[0] += 1
    ex, ey = P[-1]
    return (
        f'<svg viewBox="0 0 {w} {h}" height="{h}" preserveAspectRatio="none" role="img">'
        f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{color}" stop-opacity="0.28"/>'
        f'<stop offset="100%" stop-color="{color}" stop-opacity="0.02"/>'
        f'</linearGradient></defs>'
        f'<polygon points="{area}" fill="url(#{gid})"/>'
        f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="3" fill="{color}"/></svg>'
    )


def trend_color(pts):
    if not pts:
        return FLAT
    a, b = pts[0][1], pts[-1][1]
    return UP if b > a else (DOWN if b < a else FLAT)


def highlight(text):
    """走势点评数字高亮： signed% -> up/down， 元/单位 -> 中性蓝"""
    out = esc(text)
    out = re.sub(r"(\+\d+(?:\.\d+)?%)", r'<b class="trend-num up">\1</b>', out)
    out = re.sub(r"(-\d+(?:\.\d+)?%)", r'<b class="trend-num down">\1</b>', out)
    out = re.sub(r"(\d[\d.,]*~?\d*\s*元/(?:吨|公斤|kg|条|米|个|SF|平方英尺|张|m²))",
                 r'<b class="trend-num">\1</b>', out)
    return out


def split_trend(text):
    m = re.match(r"^【(.+?)】\s*", text)
    tag = m.group(1) if m else ""
    body = text[m.end():] if m else text
    if "采购建议：" in body:
        a, b = body.split("采购建议：", 1)
        return tag, a.strip(), b.strip()
    return tag, body.strip(), None


def chg_badge(pct, label):
    if pct is None:
        return ""
    cls = "up" if pct > 0.05 else ("down" if pct < -0.05 else "flat")
    arrow = "▲" if pct > 0.05 else ("▼" if pct < -0.05 else "—")
    sign = "+" if pct > 0 else ""
    return (f'<span class="chg {cls}" title="{esc(label)}变化"><span class="chg-label">{esc(label)}</span>'
            f"{arrow} {sign}{pct:.1f}%</span>")


def hist_card(data_mat, icon, title, hist):
    q = period_chg(hist, "近1季度")
    y = period_chg(hist, "近1年")
    sparks = []
    for p in hist.get("periods") or []:
        pts = parse_points(p.get("data"))
        if len(pts) < 2:
            continue
        sparks.append(
            f'<div class="spark-col"><div class="spark-ttl">{esc(p["name"])}</div>'
            f"{spark_svg(pts, trend_color(pts))}</div>"
        )
    if not sparks:
        return ""
    cur = hist.get("current")
    unit = hist.get("unit", "")
    yoy_html = f'<span class="yoy">{chg_badge(y, "近1年")}</span>' if y is not None else ""
    note = hist.get("note") or ""
    return (
        f'<div class="hist-card" data-mat="{esc(data_mat)}">'
        f'<div class="hist-head"><span class="hist-ico">{esc(icon)}</span><b>{esc(title)}</b>'
        f'<span class="hist-ref">{esc(hist.get("ref", ""))}</span></div>'
        f'<div class="hist-cur">{fmt_num(cur)} <i>{esc(unit)}</i>'
        f'{chg_badge(q, "近1季度")}{yoy_html}</div>'
        f'<div class="spark-row">{"".join(sparks)}</div>'
        f'<div class="hist-note">{esc(note)}</div></div>'
    )


def group_price(g):
    pts = None
    for p in (g.get("history") or {}).get("periods") or []:
        if p.get("name") == "近1月":
            pts = p.get("data") or []
    if pts and len(pts[-1]) >= 2:
        return pts[-1][1]
    return None


def update_archive(base, data, src_path=None):
    arch_dir = base / "archive"
    arch_dir.mkdir(exist_ok=True)
    date = (data.get("meta") or {}).get("updated", "")
    if not date:
        return []
    idx_path = arch_dir / "archive_index.json"
    periods = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.exists() else []
    entry = {
        "date": date,
        "index": ((data.get("meta") or {}).get("market") or {}).get("index"),
        "groups": {g["name"]: group_price(g) for g in data.get("groups", []) if group_price(g) is not None},
    }
    periods = [p for p in periods if p.get("date") != date] + [entry]
    periods.sort(key=lambda p: p.get("date", ""))
    idx_path.write_text(json.dumps(periods, ensure_ascii=False, indent=1), encoding="utf-8")
    if src_path is not None and src_path.exists():
        dst = arch_dir / f"material_prices_{date.replace('-', '')}.json"
        shutil.copy2(src_path, dst)
    return periods


def archive_section(periods, data):
    if len(periods) < 1:
        return ""
    shown = list(reversed(periods))[:10]
    dates = [p["date"][5:] for p in shown]
    mat_name = {m["id"]: (m.get("icon", "") + " " + m["name"]) for m in data.get("materials", [])}
    units = {g["name"]: g.get("unit", "") for g in data.get("groups", [])}
    idx_row = '<tr><td class="a-name">柯桥纺织品价格指数</td>' + "".join(
        f'<td class="a-val">{esc(fmt_num(p.get("index")))}</td>' for p in shown
    ) + "</tr>"
    rows = []
    cur_cat = None
    for g in data.get("groups", []):
        gname = g["name"]
        if gname not in units or all(gname not in p.get("groups", {}) for p in shown):
            continue
        cat = g["material"]
        if cat != cur_cat:
            cur_cat = cat
            rows.append(f'<tr class="group-row"><td colspan="{len(shown) + 1}">{esc(mat_name.get(cat, cat))} · {esc(cat)}</td></tr>')
        cells = []
        for i, p in enumerate(shown):
            v = p.get("groups", {}).get(gname)
            if v is None:
                cells.append('<td class="a-val" style="color:var(--ink-400)">—</td>')
                continue
            older = shown[i + 1].get("groups", {}).get(gname) if i + 1 < len(shown) else None
            if older is not None and older > 0:
                pct = (v - older) / older * 100
                if pct > 0.05:
                    cls, arrow = "var(--up)", "▲"
                elif pct < -0.05:
                    cls, arrow = "var(--down)", "▼"
                else:
                    cls, arrow = "var(--ink-700)", ""
                cells.append(f'<td class="a-val" style="color:{cls}">{esc(fmt_price(v))} {arrow}</td>')
            else:
                cells.append(f'<td class="a-val">{esc(fmt_price(v))}</td>')
        unit = units.get(gname, "")
        unit_html = f'<small>{esc(unit)}</small>' if unit else ""
        rows.append(f'<tr><td class="a-name">{esc(gname)}{unit_html}</td>{"".join(cells)}</tr>')
    span = f"{periods[0]['date']} ~ {periods[-1]['date']}" if len(periods) > 1 else periods[0]["date"]
    return (
        f'<details class="tbl-wrap section-target" id="archiveSection">\n'
        f'<summary class="ov-title ov-sum">🗄️ 往期价格档案 · 累计 {len(periods)} 期（{esc(span)}）<span class="rpt-chev">▾</span></summary>\n'
        f'<div class="sc-overview">'
        f'<div class="ov-title">📊 各细分品类 · 跨期价格对比矩阵（最新期在左，▲红涨 ▼绿跌）</div>'
        f'<div class="arch-wrap"><table class="arch">'
        f'<thead><tr><th>品类 / 期数</th>{"".join(f"<th>{esc(d)}</th>" for d in dates)}</tr></thead>'
        f"<tbody>{idx_row}{''.join(rows)}</tbody></table></div>"
        f'<div class="arch-note">注：价格取各期「近1月」末点报价；涨跌色为相邻两期环比（红涨绿跌）。完整期数超过10期时仅展示最近10期，历史明细见 archive/ 目录同名 JSON。每次运行脚本自动归档当期，无需手工维护。</div>'
        f"</div></details>"
    )


def build(data, periods=None, mode="trend"):
    meta = data["meta"]
    rep = data["reports"]
    materials = data["materials"]
    groups = data["groups"]
    market = (meta.get("market") or {})
    date = meta.get("updated", "")
    trends = meta.get("trend", [])
    srcs = rep["collection"]["sources"]

    mat_icon = {m["id"]: m.get("icon", "📦") for m in materials}
    mat_name = {m["id"]: m["name"] for m in materials}
    mat_count = {m["id"]: sum(len(g.get("items") or []) for g in groups if g.get("material") == m["id"])
                 for m in materials}
    total_items = sum(mat_count.values())
    live_groups = [g for g in groups if g.get("items")]

    # ---- 异动预警（近1月环比 |mom|>=5%）：物料大类 + 含 history 的细分群组 ----
    risk_items = []
    for m in materials:
        if m.get("history"):
            mom = mom_of(m["history"])
            if mom is not None and abs(mom) >= 5:
                risk_items.append({"key": (m["id"], m["name"]), "mat": m["id"], "icon": m.get("icon", ""),
                                   "title": m["name"], "mom": mom, "ref": m["history"].get("ref", ""),
                                   "unit": m["history"].get("unit", ""), "current": m["history"].get("current")})
    for g in groups:
        if g.get("history"):
            mom = mom_of(g["history"])
            if mom is not None and abs(mom) >= 5:
                risk_items.append({"key": (g["material"], g["name"]), "mat": g["material"],
                                   "icon": mat_icon.get(g["material"], ""), "title": g["name"], "mom": mom,
                                   "ref": g["history"].get("ref", ""), "unit": g["history"].get("unit", ""),
                                   "current": g["history"].get("current")})
    risk_items.sort(key=lambda r: -abs(r["mom"]))
    risk_key = {r["key"]: r for r in risk_items}

    # ---- 隐形 radio（纯 CSS 筛选） ----
    radios = ['<input type="radio" name="matf" id="mf-all" class="mf-radio" checked>']
    for m in materials:
        radios.append(f'<input type="radio" name="matf" id="mf-{esc(m["id"])}" class="mf-radio">')

    # ---- 顶栏 / 页头 ----
    sub_suffix = "价格趋势库" if mode == "trend" else "行业分析与建议"
    sub_home = "index.html" if mode == "insight" else "index.html"
    sub_other = "insight.html" if mode == "trend" else "index.html"
    sub_other_label = "行业分析" if mode == "trend" else "价格趋势"
    topbar = f"""<header class="kb-topbar"><div class="kb-topbar-in">
<a class="kb-home" href="{sub_home}"><span class="kb-home-logo">💱</span> 物料价格趋势库</a>
<div class="kb-top-right">
<div class="kb-subnav">
<a class="kb-subnav-item {'active' if mode == 'trend' else ''}" href="index.html">📊 价格趋势</a>
<a class="kb-subnav-item {'active' if mode == 'insight' else ''}" href="insight.html">💡 行业分析</a>
</div>
<span class="kb-status">📅 {esc(meta.get('updated', ''))}</span>
<a class="kb-back" href="/"><span class="arrow">←</span> 返回门户</a></div>
</div></header>"""

    header = f"""<header class="header">
<div class="header-in">
<h1>{esc(meta.get('title', ''))} · {sub_suffix}</h1>
<p class="subtitle">{esc(meta.get('subtitle', ''))}</p>
<span class="badge">💱 物料价格趋势库 · {len(materials)} 大类 · {len(live_groups)} 细分品类 · {total_items} 条报价 · 持续刷新</span>
</div>
</header>"""

    # ---- 侧边栏 ----
    sb_report = "".join(
        f'<li><a href="#{i}"><span class="sb-ico">{ic}</span><span class="sb-label">{t}</span></a></li>'
        for i, ic, t in [
            ("rptCollection", "📥", "数据采集汇总"), ("rptDiagnosis", "🔬", "趋势诊断"),
            ("rptDeep", "📊", "价格体检"), ("rptAlert", "🚨", "节点预警"),
            ("rptInsight", "💡", "综合洞察"), ("rptRiskMap", "🗺️", "风险地图"),
            ("futuresMgmt", "📈", "期货管理体系"), ("priceMgmt", "🎯", "价格管理体系"),
        ]
    )
    sb_module = "".join(
        f'<li><a href="#{i}"><span class="sb-ico">{ic}</span><span class="sb-label">{t}</span></a></li>'
        for i, ic, t in [
            ("trendSection", "🔍", "走势点评"), ("riskPanel", "⚠️", "异动预警"),
            ("histSection", "📉", "历史走势"), ("priceTable", "💰", "报价明细"),
            ("archiveSection", "🗄️", "往期归档"),
        ]
    )
    sb_external = "".join(
        f'<li><a href="#{i}"><span class="sb-ico">{ic}</span><span class="sb-label">{t}</span></a></li>'
        for i, ic, t in [
            ("extSection", "🌐", "外部源地图"), ("chainSection", "🔗", "传导链监控"), ("sopSection", "⏱️", "半月刷新SOP"),
        ]
    )
    sb_mats = "".join(
        f'<li><label class="sb-mat" for="mf-{esc(m["id"])}" title="筛选{esc(m["name"])}报价">'
        f'<span class="sb-ico">{esc(m.get("icon", ""))}</span><span class="sb-label">{esc(m["name"])}</span>'
        f'<span class="sb-count">{mat_count[m["id"]]}</span></label></li>'
        for m in materials
    )
    sb_archive = '<li><a href="#archiveSection"><span class="sb-ico">🗄️</span><span class="sb-label">往期价格档案</span></a></li>'
    if mode == "trend":
        sb_html = f"""<nav class="sb-nav">
<div class="sb-group"><div class="sb-group-title">价格数据</div><ul class="sb-list">{sb_module}</ul></div>
<div class="sb-group"><div class="sb-group-title">往期档案</div><ul class="sb-list">{sb_archive}</ul></div>
<div class="sb-group"><div class="sb-group-title">物料分类 · 点击筛选</div><ul class="sb-list">{sb_mats}</ul></div>
</nav>"""
    else:
        sb_html = f"""<nav class="sb-nav">
<div class="sb-group"><div class="sb-group-title">分析研判</div><ul class="sb-list">{sb_report}</ul></div>
<div class="sb-group"><div class="sb-group-title">外部洞察 · 半月刷新</div><ul class="sb-list">{sb_external}</ul></div>
</nav>"""
    sidebar = f"""<aside class="sidebar">
<div class="sb-toggle"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="11 17 6 12 11 7"></polyline><polyline points="18 17 13 12 18 7"></polyline></svg><span>页面导航</span></div>
{sb_html}
</aside>"""

    # ---- 01 采集汇总 ----
    conf = rep["collection"].get("confidence", 0)
    src_rows = "".join(
        f'<tr><td>{esc(s["name"])}</td><td>{esc(s.get("type", ""))}</td><td>{esc(s.get("coverage", ""))}</td>'
        f'<td>{s.get("items", "")}</td><td class="td-conf {"high" if s.get("confidence", 0) >= 80 else "mid"}">{s.get("confidence", "")}</td>'
        f'<td>{esc(s.get("update_freq", ""))}</td></tr>'
        for s in srcs
    )
    sec_collection = f"""<details class="rpt-section section-target" id="rptCollection">
<summary class="rpt-header"><span class="rpt-ico">📥</span><span class="rpt-title">外部数据采集汇总</span><span class="rpt-badge">置信度 {conf} / 100</span><span class="rpt-chev">▾</span></summary>
<div class="rpt-body">
<div class="rpt-summary">{esc(rep['collection'].get('summary', ''))}</div>
<div class="rpt-score-card"><div class="rpt-score-val high">{conf}</div>
<div class="rpt-score-bar-wrap"><div class="rpt-score-bar-label">综合采集置信度</div>
<div class="rpt-score-bar"><div class="rpt-score-bar-fill high" style="width:{conf}%"></div></div></div></div>
<table class="rpt-table"><thead><tr><th>数据来源</th><th>类型</th><th>覆盖类别</th><th>报价条数</th><th>置信度</th><th>更新频率</th></tr></thead>
<tbody>{src_rows}</tbody></table>
</div></details>"""

    # ---- 02 趋势诊断 ----
    dims = rep["diagnosis"].get("dimensions", [])
    d_score = round(sum(d["score"] for d in dims) / len(dims)) if dims else 0
    dim_cards = "".join(
        f'<div class="rpt-dim-card"><div class="rpt-dim-head"><span class="rpt-dim-name">{esc(d["name"])}</span>'
        f'<span class="rpt-dim-label {DIM_CLS(d["score"])}">{esc(d["label"])}</span></div>'
        f'<div class="rpt-dim-score-row"><span class="rpt-dim-score">{d["score"]}</span>'
        f'<div class="rpt-dim-bar"><div class="rpt-dim-bar-fill {FILL_CLS(d["score"])}" style="width:{d["score"]}%"></div></div></div>'
        f'<div class="rpt-dim-detail">{esc(d["detail"])}</div></div>'
        for d in dims
    )
    sec_diagnosis = f"""<details class="rpt-section section-target" id="rptDiagnosis">
<summary class="rpt-header"><span class="rpt-ico">🔬</span><span class="rpt-title">趋势诊断（五维评估）</span><span class="rpt-badge">综合评分 {d_score} / 100</span><span class="rpt-chev">▾</span></summary>
<div class="rpt-body">
<div class="rpt-summary">{esc(rep['diagnosis'].get('summary', ''))}</div>
<div class="rpt-score-card"><div class="rpt-score-val {FILL_CLS(d_score)}">{d_score}</div>
<div class="rpt-score-bar-wrap"><div class="rpt-score-bar-label">五维综合趋势评分（越高=上行压力越大）</div>
<div class="rpt-score-bar"><div class="rpt-score-bar-fill {FILL_CLS(d_score)}" style="width:{d_score}%"></div></div></div></div>
<div class="rpt-dim-grid">{dim_cards}</div>
</div></details>"""

    # ---- 03 节点预警 ----
    factors = rep["alert"].get("factors", [])
    lvl_cnt = {}
    for f in factors:
        lvl_cnt[f["level"]] = lvl_cnt.get(f["level"], 0) + 1
    badge_parts = []
    for k, ico, lb in (("预警", "⛔", "预警"), ("重点跟踪", "🔶", "跟踪"), ("关注", "⚠️", "关注")):
        if lvl_cnt.get(k):
            badge_parts.append(f"{ico} {lvl_cnt[k]} {lb}")
    badge_txt = " · ".join(badge_parts)
    f_cards = "".join(
        f'<div class="rpt-dim-card"><div class="rpt-dim-head"><span class="rpt-dim-name">{esc(f["name"])}</span>'
        f'<span class="rpt-dim-label {LVL_CLS.get(f["level"], "safe")}">{esc(f["level"])}</span></div>'
        f'<div class="rpt-dim-score-row"><span class="rpt-dim-score">{f["score"]}</span>'
        f'<div class="rpt-dim-bar"><div class="rpt-dim-bar-fill {FILL_CLS(f["score"])}" style="width:{f["score"]}%"></div></div></div>'
        f'<div class="rpt-dim-detail">{esc(f.get("detail", ""))}</div></div>'
        for f in factors
    )
    sec_alert = f"""<details class="rpt-section section-target" id="rptAlert">
<summary class="rpt-header"><span class="rpt-ico">🚨</span><span class="rpt-title">节点预警（五因子评估）</span><span class="rpt-badge">{badge_txt}</span><span class="rpt-chev">▾</span></summary>
<div class="rpt-body">
<div class="rpt-summary">{esc(rep['alert'].get('summary', ''))}</div>
<div class="rpt-dim-grid">{f_cards}</div>
</div></details>"""

    # ---- 04 综合洞察 ----
    ins = rep["insight"]
    ACT_SPLIT = re.compile(r"[，,。；;]\s*(?=[^，,。；;]*(?:建议|宜|应|需|优先|可考虑|关注|警惕)[^，,。；;]{2,})")
    ACT_VERBS = ("锁价", "锁量", "前置", "分批", "对冲", "按单", "备货", "采购", "避免")
    def _take_card(t):
        text = t.get("text", "")
        parts = ACT_SPLIT.split(text, 1)
        judge, act = (parts[0], parts[1]) if len(parts) == 2 else (text, "")
        if act:
            act = re.sub(r"^(建议|宜|应|需|可考虑|优先|关注|警惕)", "", act)
        else:
            judge, act = text, ""
        if not act:
            lv, lv_cls, ico = "纳入观察", "lv-watch", "🔍"
        elif any(v in act for v in ACT_VERBS):
            lv, lv_cls, ico = "立即行动", "lv-act", "✅"
        else:
            lv, lv_cls, ico = "跟踪观察", "lv-track", "🔍"
        judge_h = re.sub(r"([+-]?\d+(?:\.\d+)?\s*%)", r'<b class="tk-num">\1</b>', esc(judge))
        act_html = (
            f'<div class="rpt-take-act"><span class="ta-ico">{ico}</span><span>{esc(act)}</span></div>' if act else ""
        )
        return (
            f'<div class="rpt-take-card {lv_cls}"><div class="rpt-take-head">'
            f'<span class="rpt-take-tag">{esc(t["tag"])}</span>'
            f'<span class="rpt-take-lv">{lv}</span></div>'
            f'<div class="rpt-take-text">{judge_h}</div>{act_html}</div>'
        )
    take_cards = "".join(_take_card(t) for t in ins.get("takeaways", []))
    sec_insight = f"""<details class="rpt-section section-target" id="rptInsight" open>
<summary class="rpt-header"><span class="rpt-ico">💡</span><span class="rpt-title">综合洞察（分析与研判）</span><span class="rpt-badge">综合置信度 {conf} / 100</span><span class="rpt-chev">▾</span></summary>
<div class="rpt-body">
<div class="rpt-insight-callout"><span class="ic-ico">🎯</span><span class="ic-text">{esc(ins.get('summary', ''))}</span></div>
<div class="rpt-sub-title">关键洞察与行动建议</div>
<div class="rpt-takeaways">{take_cards}</div>
</div></details>"""

    # ---- 05 风险地图 ----
    nodes = rep["riskMap"].get("nodes", [])
    stat_cards = "".join(
        f'<div class="risk-stat {LVL_CLS.get(k, "safe")}"><div class="rs-num">{lvl_cnt.get(k, 0)}</div><div class="rs-label">{k}</div></div>'
        for k in ("预警", "重点跟踪", "关注", "低风险")
    )
    r_rows = "".join(
        f'<div class="risk-row{" top" if nd["name"] == rep["riskMap"].get("topRisk") else ""}">'
        f'<span class="rr-level {LVL_CLS.get(nd["level"], "safe")}">{esc(nd["level"])}</span>'
        f'<span class="rr-name">{esc(nd["name"])}</span>'
        f'<div class="rr-bar-wrap"><div class="rr-bar"><div class="rr-bar-fill {LVL_CLS.get(nd["level"], "safe")}" style="width:{nd["score"]}%"></div></div></div>'
        f'<span class="rr-score">{nd["score"]}</span>'
        f'<span class="rr-action">{esc(nd.get("action", ""))}</span></div>'
        for nd in nodes
    )
    sec_riskmap = f"""<details class="rpt-section section-target" id="rptRiskMap">
<summary class="rpt-header"><span class="rpt-ico">🗺️</span><span class="rpt-title">风险地图（节点风险全景）</span><span class="rpt-badge">{badge_txt}</span><span class="rpt-chev">▾</span></summary>
<div class="rpt-body">
<div class="rpt-summary">{esc(rep['riskMap'].get('summary', ''))}</div>
<div class="risk-stats">{stat_cards}</div>
<div class="risk-rows">{r_rows}</div>
</div></details>"""

    # ---- 05b 价格体检（三期动能 × 年内位置 × 品类联动） ----
    da_cats, da_corr = deep_analysis(materials)
    fmt_pct = lambda x: "—" if x is None else f"{x:+.1f}%"
    up_cats = [c for c in da_cats if _sig(c["mom"]) > 0]
    down_cats = [c for c in da_cats if _sig(c["mom"]) < 0]
    consist_up = [c for c in da_cats if c["consist"] and c["sig"] > 0]
    consist_dn = [c for c in da_cats if c["consist"] and c["sig"] < 0]
    hi_pos = [c for c in da_cats if c["pos"] >= 70]
    lo_pos = [c for c in da_cats if c["pos"] <= 30]
    join_n = lambda lst: "、".join(c["name"].split("·")[0] for c in lst) or "—"

    kpi_tiles = "".join([
        f'<div class="kpi-tile up"><div class="k-num">{len(up_cats)}</div><div class="k-label">环比上涨</div><div class="k-sub">{join_n(up_cats)}</div></div>',
        f'<div class="kpi-tile down"><div class="k-num">{len(down_cats)}</div><div class="k-label">环比下跌</div><div class="k-sub">{join_n(down_cats)}</div></div>',
        f'<div class="kpi-tile warn"><div class="k-num">{len(consist_up) + len(consist_dn)}</div><div class="k-label">三期动能一致</div><div class="k-sub">↑{len(consist_up)}（{join_n(consist_up)}）· ↓{len(consist_dn)}（{join_n(consist_dn)}）</div></div>',
        f'<div class="kpi-tile up"><div class="k-num">{len(hi_pos)}</div><div class="k-label">年内高位 ≥70%</div><div class="k-sub">{join_n(hi_pos)}</div></div>',
        f'<div class="kpi-tile down"><div class="k-num">{len(lo_pos)}</div><div class="k-label">年内低位 ≤30%</div><div class="k-sub">{join_n(lo_pos)}</div></div>',
    ])

    def _m_cell(x):
        s = _sig(x)
        if x is None:
            return '<td class="m-val dim">—</td>'
        cls = "m-up" if s > 0 else ("m-dn" if s < 0 else "m-flat")
        arrow = "▲" if s > 0 else ("▼" if s < 0 else "—")
        return f'<td class="m-val {cls}">{arrow} {x:+.1f}%</td>'

    BADGE_UP = '<span class="ext-b" style="background:#FEE2E2;color:#B91C1C">三期连涨</span>'
    BADGE_DN = '<span class="ext-b" style="background:#D1FAE5;color:#047857">三期连跌</span>'
    BADGE_MIX = '<span class="ext-b" style="background:#F1F5F9;color:#64748B">走势分歧</span>'

    def _mom_badge(c):
        if c["consist"] and c["sig"] > 0:
            return BADGE_UP
        if c["consist"] and c["sig"] < 0:
            return BADGE_DN
        return BADGE_MIX

    mom_rows = "".join(
        f'<tr><td class="m-name">{esc(c["icon"])} {esc(c["name"])}</td>'
        f'{_m_cell(c["mom"])}{_m_cell(c["qoq"])}{_m_cell(c["yoy"])}'
        f'<td>{_mom_badge(c)}</td></tr>'
        for c in sorted(da_cats, key=lambda x: -(x["mom"] or 0))
    )

    pos_cards = "".join(
        f'<div class="pos-card"><div class="pos-head"><span class="pos-name">{esc(c["icon"])} {esc(c["name"].split("·")[0])}</span>'
        f'<span class="pos-pct{" hi" if c["pos"] >= 70 else (" lo" if c["pos"] <= 30 else "")}">{c["pos"]:.0f}%</span></div>'
        f'<div class="pos-track"><span class="pos-dot" style="left:{c["pos"]:.0f}%;{"background:#DC2626" if c["pos"] >= 70 else ("background:#059669" if c["pos"] <= 30 else "background:#2563EB")}"></span></div>'
        f'<div class="pos-meta"><span>低 {fmt_num(c["lo"])}</span><span>σ波动 {c["vol"]:.1f}%</span><span>高 {fmt_num(c["hi"])}</span></div></div>'
        for c in sorted(da_cats, key=lambda x: -x["pos"])
    )

    short = {c["id"]: c["name"].split("·")[0] for c in da_cats}
    corr_head = "".join(f'<th>{esc(short[c["id"]])}</th>' for c in da_cats)
    corr_body_rows = []
    for ra in da_cats:
        cells = [f'<th class="corr-row-h">{esc(ra["icon"])} {esc(short[ra["id"]])}</th>']
        for rb in da_cats:
            if ra["id"] == rb["id"]:
                cells.append('<td class="corr-cell diag">—</td>')
                continue
            key = (ra["id"], rb["id"]) if (ra["id"], rb["id"]) in da_corr else (rb["id"], ra["id"])
            r = da_corr.get(key)
            if r is None:
                cells.append('<td class="corr-cell dim">n/a</td>')
            else:
                color = "220,38,38" if r > 0 else "5,150,105"
                cells.append(
                    f'<td class="corr-cell{" strong" if abs(r) >= 0.6 else ""}" style="background:rgba({color},{abs(r) * 0.5:.2f})">{r:+.2f}</td>'
                )
        corr_body_rows.append("<tr>" + "".join(cells) + "</tr>")

    actions = []
    for c in da_cats:
        if c["consist"] and c["sig"] > 0 and c["pos"] >= 70:
            actions.append(f'<b>{esc(c["name"])}</b>：年内 {c["pos"]:.0f}% 高位 + 三期动能一致上行 → 相关物料<b>提前锁价</b>，避免追高')
        elif c["consist"] and c["sig"] > 0:
            actions.append(f'<b>{esc(c["name"])}</b>：三期动能一致上行（年内 {c["pos"]:.0f}%）→ 关注成本传导，锁定长单价格')
    for c in da_cats:
        if c["pos"] <= 30:
            actions.append(f'<b>{esc(c["name"])}</b>：年内 {c["pos"]:.0f}% 低位 → <b>逢低分批建仓</b>窗口，评估冬装填充料备货节奏')
    for (aid, bid), r in da_corr.items():
        if aid != bid and r is not None and r >= 0.6:
            a2, b2 = short.get(aid, aid), short.get(bid, bid)
            actions.append(f'<b>{a2} × {b2}</b>：联动系数 {r:+.2f}（同涨同跌）→ 组合谈判、替代评估时视为一组敞口')
    action_html = "".join(f'<div class="act-row">📌 {t}</div>' for t in actions[:6])

    sec_deep = f"""<details class="rpt-section section-target" id="rptDeep" open>
<summary class="rpt-header"><span class="rpt-ico">📊</span><span class="rpt-title">价格体检 · 三期动能 × 年内位置 × 品类联动</span><span class="rpt-badge">覆盖 {len(da_cats)} 大类 · 近1年口径</span><span class="rpt-chev">▾</span></summary>
<div class="rpt-body">
<div class="rpt-summary"><b>体检逻辑：</b>动能看「近1月 / 近1季度 / 近1年」三期方向是否一致（一致 = 趋势确认）；位置看现价处于近1年区间的百分位（≥70% 高位承压、≤30% 低位机会）；联动看品类间收益率相关系数（≥0.6 视为同组敞口）。三者交叉 → 锁价 / 观望 / 建仓动作建议。</div>
<div class="kpi-grid">{kpi_tiles}</div>
<div class="rpt-sub-title">① 三期动能（按环比涨幅排序）</div>
<table class="rpt-table mom-tbl"><thead><tr><th>品类</th><th>近1月</th><th>近1季度</th><th>近1年</th><th>动能判定</th></tr></thead>
<tbody>{mom_rows}</tbody></table>
<div class="rpt-sub-title">② 年内位置（现价处于近1年区间百分位）</div>
<div class="pos-grid">{pos_cards}</div>
<div class="pos-legend"><span class="lg lg-lo">≤30% 低位</span><span class="lg lg-mid">30–70% 中位</span><span class="lg lg-hi">≥70% 高位</span><span class="lg">σ = 近1年收益率标准差（波动）</span></div>
<div class="rpt-sub-title">③ 品类联动矩阵（近1年收益率 Pearson 相关系数）</div>
<div class="corr-wrap"><table class="rpt-table corr-tbl"><thead><tr><th></th>{corr_head}</tr></thead>
<tbody>{''.join(corr_body_rows)}</tbody></table></div>
<div class="rpt-sub-title">④ 交叉结论 → 采购动作</div>
<div class="act-list">{action_html}</div>
</div></details>"""

    # ---- 走势点评 ----
    t_cards = []
    for t in trends:
        tag, body, advice = split_trend(t)
        icon = TREND_ICONS.get(tag, "📌")
        adv_html = f'<div class="trend-advice"><div class="ta-label">💡 采购建议</div>{highlight(advice)}</div>' if advice else ""
        t_cards.append(
            f'<div class="trend-card"><div class="trend-card-head"><span class="trend-card-ico">{icon}</span>'
            f'<span class="trend-card-title">{esc(tag)}</span></div>'
            f'<div class="trend-card-body">{highlight(body)}</div>{adv_html}</div>'
        )
    sec_trend = f"""<details class="trend section-target" id="trendSection" open>
<summary class="ov-title ov-sum">🔍 走势点评与采购建议<span class="rpt-chev">▾</span></summary>
<div class="trend-cards">{"".join(t_cards)}</div></details>"""

    # ---- 价格异动预警 ----
    if risk_items:
        ri_html = "".join(
            f'<div class="risk-item { "alert" if abs(r["mom"]) >= 10 else "watch" }">'
            f'<span class="ri-name">{esc(r["icon"])} {esc(r["title"])}</span>'
            f'<span class="risk-tag {"alert" if abs(r["mom"]) >= 10 else "watch"}">{"⛔ 预警" if abs(r["mom"]) >= 10 else "⚠️ 关注"}</span>'
            f'<span class="ri-pct">{"▲" if r["mom"] > 0 else "▼"} {r["mom"]:+.1f}%</span>'
            f'<span class="ri-note">{esc("环比上行，关注成本传导与前置锁价窗口" if r["mom"] > 0 else "环比回落，关注企稳 / 备货信号，逢低分批建仓")}</span></div>'
            for r in risk_items
        )
    else:
        ri_html = f'<div class="risk-empty">✅ 本期（{esc(meta.get("updated", ""))}）无环比上月 ±5% 以上异动项。</div>'
    sec_riskpanel = f"""<details class="risk-panel section-target" id="riskPanel" open>
<summary class="ov-title ov-sum">⚠️ 价格异动预警（近1月环比）<span class="rpt-chev">▾</span></summary>
<div class="risk-sub">环比上月变动 ≥5% 触发「关注」、≥10% 触发「预警」；仅列异动项。</div>
<div class="risk-list">{ri_html}</div></details>"""

    # ---- 历史走势 ----
    h_cards = []
    for m in materials:
        if m.get("history"):
            h_cards.append(hist_card(m["id"], m.get("icon", "📦"), m["name"], m["history"]))
    for g in groups:
        if g.get("history"):
            h_cards.append(hist_card(g["material"], mat_icon.get(g["material"], "📦"), g["name"], g["history"]))
    sec_hist = f"""<details class="hist-section section-target" id="histSection" open>
<summary class="hist-title ov-sum">📉 历史价格走势（近1月 / 近1季度 / 近1年）· 曲线为基于公开行情的走势示意，供趋势研判参考<span class="rpt-chev">▾</span></summary>
<div class="hist-grid">{"".join(h_cards)}</div></details>"""

    # ---- 报价明细 ----
    idx_note = market.get("index_note", "")
    m_yoy = re.search(r"同比\s*\+?([\d.]+)%", idx_note)
    yoy = f"+{m_yoy.group(1)}%" if m_yoy else ""
    op_note = market.get("operating_note", "")
    m_op = re.search(r"(\d+/\d+-\d+\s*周)[，,]\s*环比\s*([+-]?[\d.]+)\s*pct", op_note)
    op_sub = f"（{m_op.group(1)} · 环比 {m_op.group(2)}pct）" if m_op else ""
    idx_chg = market.get("index_change", 0)
    idx_sub = f"柯桥纺织品价格指数（环比 {idx_chg:+.2f}%" + (f" · 同比 {yoy}）" if yoy else "）")
    ov_stats = "".join(
        f'<div class="sc-ov-stat"><b class="{cls}">{v}</b><span>{lb}</span></div>'
        for cls, v, lb in [
            ("up", fmt_num(market.get("index")), idx_sub),
            ("", fmt_num(market.get("inventory_days")), "坯布库存（天）"),
            ("", fmt_num(market.get("operating_rate")) + "%", f"织机开机率{op_sub}"),
            ("", fmt_num(market.get("sampled_shops")), "采样商户"),
            ("", str(len(materials)), "物料大类"),
            ("", str(len(live_groups)), "细分品类"),
            ("", str(total_items), "报价条数"),
            ("", esc(meta.get("updated", "")), "最近更新"),
        ]
    )
    notes = "".join(
        f'<div class="note-card"><h4>{ic} {t}</h4><p>{esc(txt)}</p></div>'
        for ic, t, txt in [
            ("📈", "价格指数", idx_note),
            ("📦", "坯布库存", market.get("inventory_note", "")),
            ("⚙️", "织机开机率", op_note),
        ]
    )
    pills = ['<label class="mat-btn" for="mf-all">全部</label>']
    for m in materials:
        pills.append(f'<label class="mat-btn" for="mf-{esc(m["id"])}">{esc(m.get("icon", ""))} {esc(m["name"])}</label>')
    finds = [f'<span class="find find-all">显示全部 · {total_items} 条</span>']
    for m in materials:
        finds.append(f'<span class="find find-{esc(m["id"])}">已筛选 {esc(m.get("icon", ""))} {esc(m["name"])} · {mat_count[m["id"]]} 条</span>')

    tbody = []
    for g in live_groups:
        items = g.get("items") or []
        prices = [float(i["price"]) for i in items]
        rng = f"¥{fmt_num(min(prices))} ~ ¥{fmt_num(max(prices))}"
        rk = risk_key.get((g["material"], g["name"]))
        rb = (f' <span class="risk-badge {"up" if rk["mom"] > 0 else "down"}">'
              f'{"🔺" if rk["mom"] > 0 else "🔻"} {rk["mom"]:+.1f}%</span>') if rk else ""
        unit = (g.get("unit") or "").strip()
        unit_html = f'<span class="unit">{esc(unit)}</span>' if unit else ""
        tbody.append(
            f'<tr class="group-row" data-mat="{esc(g["material"])}"><td colspan="5">'
            f'{esc(mat_icon.get(g["material"], ""))} <b>{esc(g["name"])}</b>{rb}{unit_html}'
            f'<span class="rng">{rng}</span><span class="gsrc">{esc(g.get("source", ""))}</span></td></tr>'
        )
        for it in items:
            focus = ' <span class="focus-badge">★ 我司主力</span>' if it.get("focus") else ""
            tbody.append(
                f'<tr data-mat="{esc(g["material"])}"><td>{esc(g["name"])}</td>'
                f'<td>{esc(it["name"])}{focus}</td><td>{esc(it.get("spec") or "—")}</td>'
                f'<td class="origin">{esc(it.get("origin") or "—")}</td>'
                f'<td class="price">{fmt_price(it["price"])}</td></tr>'
            )
    sec_table = f"""<details class="tbl-wrap section-target" id="priceTable" open>
<summary class="ov-title ov-sum">💰 报价明细大表 · {total_items} 条报价 · {len(live_groups)} 细分品类<span class="rpt-chev">▾</span></summary>
<div class="sc-overview">
<div class="ov-title">📊 市场快照（柯桥纺织指数 · {esc(market.get('date', ''))}）</div>
<div class="sc-ov-stats">{ov_stats}</div>
<div class="notes">{notes}</div>
</div>
<div class="mat-filter">{"".join(pills)}</div>
<div class="tbl-ctrl">
<span class="count">{"".join(finds)}</span>
<span class="hint">🔎 纯静态页 · 检索请用浏览器页面内查找（Ctrl+F / 企微右上角菜单「搜索页面内容」）</span>
</div>
<table class="mp">
<thead><tr><th>细分品类</th><th>品名 / 规格档</th><th>规格 / 说明</th><th>产地</th><th>参考价</th></tr></thead>
<tbody>{"".join(tbody)}</tbody>
</table>
</details>"""

    footer = f"""<footer class="footer">
<div class="update-info">数据日期：<strong>{esc(meta.get('updated', ''))}</strong> ｜ 来源：<strong>{esc(meta.get('source', ''))}</strong></div>
<div class="copyright">物料价格趋势库 · 供应链中心 · 纯静态零 JS 版（兼容企业微信浏览器，报价仅供参考，以实际成交为准）</div>
</footer>"""

    # ---- 外部洞察：外部源地图 + 传导链 + 半月刷新SOP ----
    rh_cards = "".join(
        f'<div class="rh-card{" hl" if cls == "t-p0" else ""}"><div class="rh-tag {cls}">{tag}</div>'
        f'<h3>{title}</h3><p>{desc}</p></div>'
        for cls, tag, title, desc in EXT_RHYTHM
    )
    FREE_LBL = {"b-free": "完全免费", "b-part": "部分免费"}
    NEW_B = '<span class="ext-b new">新</span>'

    def _ext_rows(lst, with_freq=True):
        rows = []
        for row in lst:
            if with_freq:
                name, url, cov, ind, freq, fcls, ref, is_new = row
                rows.append(
                    f'<tr><td class="ext-src"><a href="{url}" target="_blank">{esc(name)}</a>'
                    f'{NEW_B if is_new else ""}</td>'
                    f'<td>{esc(cov)}</td><td>{esc(ind)}</td><td class="ext-dim">{esc(freq)}</td>'
                    f'<td><span class="ext-b {fcls}">{FREE_LBL[fcls]}</span></td>'
                    f'<td class="ext-ref">{esc(ref)}</td></tr>'
                )
            else:
                name, url, cov, ind, fcls, ref = row
                rows.append(
                    f'<tr><td class="ext-src"><a href="{url}" target="_blank">{esc(name)}</a></td>'
                    f'<td>{esc(cov)}</td><td>{esc(ind)}</td>'
                    f'<td><span class="ext-b {fcls}">{FREE_LBL[fcls]}</span></td>'
                    f'<td class="ext-ref">{esc(ref)}</td></tr>'
                )
        return "".join(rows)

    ext_hdr = ('<tr><th style="width:170px">数据源</th><th style="width:150px">覆盖品类</th><th>关键指标</th>'
               '<th style="width:80px">频率</th><th style="width:80px">免费程度</th><th style="width:90px">库内引用</th></tr>')
    ext_hdr_pool = ('<tr><th style="width:170px">渠道</th><th style="width:150px">覆盖品类</th><th>取数方式</th>'
                    '<th style="width:80px">免费程度</th><th style="width:90px">库内条数</th></tr>')
    grp_meta = [
        ("g0", "P0 · 每次必刷", "异动监测核心，覆盖库内引用最多的四大高权重组", "P0", ext_hdr, True),
        ("g1", "P1 · 半月轮刷", "按当期异动品类轮换刷取，与 P0 交叉验证", "P1", ext_hdr, True),
        ("g2", "P2 · 月度低频", "月报与深度分析用，非半月必刷项", "P2", ext_hdr, True),
        ("g3", "低置信源比价池", "辅料/皮毛草/五金/缝纫线等「市场调研」报价的校准渠道", "POOL", ext_hdr_pool, False),
        ("g3", "宏观传导监控", "每次刷新必看，判断成本传导方向与力度", "MACRO", ext_hdr, True),
    ]
    ext_blocks = []
    for dot, gtitle, hint, key, hdr, with_freq in grp_meta:
        rows = _ext_rows(EXT_SOURCES[key], with_freq)
        ext_blocks.append(
            f'<div class="ext-grp"><span class="ext-dot {dot}"></span>{gtitle}<span class="ext-hint">{hint}</span></div>'
            f'<table class="rpt-table ext-tbl"><thead>{hdr}</thead><tbody>{rows}</tbody></table>'
        )

    # ===== 期货管理体系 =====
    fut_categories = [
        ("棉类", "ICE美棉 / 郑棉", "棉纺全链成本锚点，传导 1-2 个月", "直接相关 · 采购周期长",
         ["买入套保锁定远期成本", "基差定价模式替代一口价", "关注储备棉轮出节奏与滑准税政策"]),
        ("羊毛", "澳毛拍卖指数 / 羊毛期货", "澳毛占进口羊毛主体，拍卖价即现货基准", "直接相关 · 季度采购",
         ["跟踪澳元汇率+拍卖指数双因子", "旺季前分批建仓，避免集中采购", "与核心供应商签价格联动条款"]),
        ("化纤", "PTA / MEG / 原油", "原油→PTA→聚酯→化纤，成本传导链清晰", "间接相关 · 供应商传导",
         ["油价±10% 触发化纤价格评审", "关注PTA开工率与库存周期", "低位时建议供应商提前备货锁价"]),
        ("铜", "沪铜主力 / 伦铜", "拉链、四合扣等金属辅料原料基准", "间接相关 · 辅料成本",
         ["铜价高位签铜价联动条款（锁量不锁价）", "低位窗口可考虑 3-6 个月备货锁价", "关注美联储政策与国内地产链信号"]),
        ("羽绒", "无直接期货", "供需季节性强，依赖现货渠道信息", "不适用 · 现货市场",
         ["建立羽绒供应商周报价机制", "8/9月旺季前提前 1-2 个月锁量", "跟踪鹅鸭存栏与疫病数据"]),
    ]
    fut_rows = "".join(
        f'<tr><td class="fut-cat"><b>{esc(cat)}</b></td><td class="fut-mkt">{esc(mkt)}</td>'
        f'<td class="fut-rel">{esc(rel)}</td><td class="fut-exp">{esc(exp)}</td>'
        f'<td class="fut-act"><ul class="fut-act-list">{"".join(f"<li>{esc(a)}</li>" for a in acts)}</ul></td></tr>'
        for cat, mkt, rel, exp, acts in fut_categories
    )
    fut_strategy = f"""<div class="rpt-sub-title">套保策略矩阵（按价格位置 × 波动率）</div>
<table class="rpt-table fut-mat">
<thead><tr><th style="width:18%">价格位置</th><th style="width:27%">低波动（&lt;2%/月）</th><th style="width:27%">中波动（2-5%/月）</th><th style="width:28%">高波动（&gt;5%/月）</th></tr></thead>
<tbody>
<tr><td class="fut-pos up"><b>价格高位（80分位以上）</b></td><td>观望 · 按需采购，不追高</td><td>卖出套保锁定库存价值 · 控制采购节奏</td><td><b>减仓避险 · 缩短采购周期</b>，禁止囤货</td></tr>
<tr><td class="fut-pos mid"><b>价格中位（40-80分位）</b></td><td>正常节奏 · 按计划采购</td><td><b>基差采购 · 分批建仓</b>，锁定30-50%远期</td><td>加快周转 · 小批量多频次</td></tr>
<tr><td class="fut-pos dn"><b>价格低位（40分位以下）</b></td><td>分批建仓 · 锁定3-6个月用量</td><td><b>买入套保 · 锁定60-80%</b>远期成本</td><td>逆向布局 · 分3-5次抄底，总仓位不超9个月</td></tr>
</tbody>
</table>
<div class="rpt-sub-title">品牌运营商的三种期货参与模式</div>
<div class="mode-grid">
<div class="mode-card">
<div class="mode-ico">📦</div><div class="mode-name">模式一 · 供应商传导</div>
<div class="mode-desc">不直接参与期货，要求核心供应商提供期货套保能力，在采购合同中约定价格联动公式。<b>适用：我司当前阶段</b>，风险低、落地快。</div>
</div>
<div class="mode-card">
<div class="mode-ico">📊</div><div class="mode-name">模式二 · 基差采购</div>
<div class="mode-desc">以期货价格+基差的方式定价，取代传统一口价。采购方选择点价时机，供应商负责套保。<b>适用：棉、羊毛等标准化大宗品</b>。</div>
</div>
<div class="mode-card">
<div class="mode-ico">🏦</div><div class="mode-name">模式三 · 自营套保</div>
<div class="mode-desc">设立期货交易岗，直接参与套保业务。需独立风控体系、专业团队、制度流程。<b>适用：年采购额超5亿且价格波动剧烈</b>的战略品类。</div>
</div>
</div>
<div class="rpt-sub-title">风控与组织保障</div>
<div class="risk-safeguard">
<div class="rs-item"><span class="rs-ico">🎯</span><div><b>敞口管理</b>：按品类计算价格风险敞口（月度用量×单价波动×敏感度系数），设定单品类最大敞口头寸</div></div>
<div class="rs-item"><span class="rs-ico">🛡️</span><div><b>止损机制</b>：单品类浮亏超过年度采购预算 3% 强制减仓，超过 5% 启动应急评审</div></div>
<div class="rs-item"><span class="rs-ico">📋</span><div><b>组织架构</b>：价格管理小组（供应链+财务+品牌+法务）月度评审，季度策略会决定下季度套保比例与方向</div></div>
<div class="rs-item"><span class="rs-ico">🔍</span><div><b>制度流程</b>：《套保业务管理办法》《价格风险预警与响应SOP》《供应商价格联动条款模板》三件套先行</div></div>
</div>"""

    sec_futures = f"""<details class="rpt-section section-target" id="futuresMgmt" open>
<summary class="rpt-header"><span class="rpt-ico">📈</span><span class="rpt-title">期货管理体系 · 套保策略与价格风险管理</span><span class="rpt-badge">5 大品类 · 3 种参与模式</span><span class="rpt-chev">▾</span></summary>
<div class="rpt-body">
<div class="rpt-insight-callout"><span class="ic-ico">💡</span><span class="ic-text">品牌运营商不一定要自己做期货，但必须懂期货价格逻辑——通过供应商传导、基差采购、价格联动条款，同样能管理原材料价格波动风险。</span></div>
<div class="rpt-sub-title">品类覆盖与策略</div>
<table class="rpt-table fut-tbl">
<thead><tr><th style="width:11%">品类</th><th style="width:17%">对标市场</th><th style="width:20%">相关性与传导</th><th style="width:14%">我司敞口</th><th>核心策略</th></tr></thead>
<tbody>{fut_rows}</tbody>
</table>
{fut_strategy}
</div></details>"""

    # ===== 重点原材料价格管理体系 =====
    pm_abc = f"""<div class="rpt-sub-title">原材料分级管理（ABC 分类）</div>
<table class="rpt-table pm-tbl">
<thead><tr><th style="width:12%">等级</th><th style="width:16%">定义</th><th style="width:28%">包含品类</th><th style="width:16%">管理密度</th><th>管理目标</th></tr></thead>
<tbody>
<tr><td class="pm-a"><b>A 类 · 战略级</b></td><td>年采购额占比 ≥ 10%<br>价格波动影响毛利率</td><td>羊毛（澳毛/国毛）、羊绒、羽绒、棉花</td><td><b>周度跟踪 · 月度评审</b></td><td>价格波动控制在 ±5% 以内，锁定核心供应</td></tr>
<tr><td class="pm-b"><b>B 类 · 重要级</b></td><td>年采购额 3-10%<br>有一定替代空间</td><td>涤纶/锦纶/腈纶等化纤、马海毛/牦牛绒等特纤、铜（辅料用）</td><td><b>双周跟踪 · 双月评审</b></td><td>价格波动控制在 ±8% 以内，保持供应弹性</td></tr>
<tr><td class="pm-c"><b>C 类 · 常规级</b></td><td>年采购额 &lt; 3%<br>替代容易 / 单价低</td><td>粘胶、亚麻、苎麻、五金辅料（除铜）、衬料、拉链布带等</td><td><b>月度跟踪 · 季度评审</b></td><td>保障供应，价格随市场</td></tr>
</tbody>
</table>"""

    pm_warn = f"""<div class="rpt-sub-title">价格预警阈值与响应机制</div>
<div class="warn-ladder">
<div class="warn-item wn-blue">
<div class="wn-head"><span class="wn-lvl">Level 1 · 关注</span><span class="wn-thresh">单月波动 ± 3%</span></div>
<div class="wn-body">
<ul><li><b>触发动作：</b>价格管理小组书面通报，纳入下周跟踪重点</li>
<li><b>输出物：</b>异动原因分析（供需面 / 政策面 / 资金面）、影响测算</li>
<li><b>决策权限：</b>品类经理</li></ul>
</div></div>
<div class="warn-item wn-amber">
<div class="wn-head"><span class="wn-lvl">Level 2 · 应对</span><span class="wn-thresh">单月波动 ± 5% 或 连续2月同向</span></div>
<div class="wn-body">
<ul><li><b>触发动作：</b>启动采购策略调整评估，供应商价格沟通</li>
<li><b>输出物：</b>替代方案评估、采购节奏调整建议、成本影响测算</li>
<li><b>决策权限：</b>采购经理 + 品类负责人</li></ul>
</div></div>
<div class="warn-item wn-red">
<div class="wn-head"><span class="wn-lvl">Level 3 · 升级</span><span class="wn-thresh">单月波动 ± 8% 或 季度超 12%</span></div>
<div class="wn-body">
<ul><li><b>触发动作：</b>价格管理小组紧急会议，调整季度采购策略</li>
<li><b>输出物：</b>应急采购方案、产品成本重算、品牌端定价建议</li>
<li><b>决策权限：</b>供应链总监 + 财务总监 + 品牌总</li></ul>
</div></div>
</div>"""

    pm_strategy = f"""<div class="rpt-sub-title">采购策略矩阵（价格位置 × ABC 等级）</div>
<table class="rpt-table strat-mat">
<thead><tr><th style="width:15%">价格位置</th><th style="width:28%">A 类（战略级）</th><th style="width:28%">B 类（重要级）</th><th style="width:29%">C 类（常规级）</th></tr></thead>
<tbody>
<tr><td class="pos-up"><b>价格高位</b></td><td><b>按需采购 + 锁量不锁价</b><br>缩短周期，避免高点囤货；启动替代方案评估</td><td>按需采购，加快周转<br>寻找替代供应商压价</td><td>正常采购<br>年度协议价保护</td></tr>
<tr><td class="pos-mid"><b>价格中位</b></td><td><b>分批建仓 30-50%</b><br>基差采购模式，锁定部分远期用量</td><td>正常节奏 + 部分锁价<br>3-4 个月用量</td><td>正常采购</td></tr>
<tr><td class="pos-dn"><b>价格低位</b></td><td><b>逆向布局 60-80%</b><br>分 3-5 批抄底，锁定 6-9 个月用量</td><td>提前备货 3-6 个月<br>分批锁价</td><td>年度框架协议<br>一次性锁价</td></tr>
</tbody>
</table>"""

    pm_cost = f"""<div class="rpt-sub-title">降本核算方法与考核口径</div>
<div class="cost-methods">
<div class="cm-card">
<div class="cm-name">📐 基准价对比法</div>
<div class="cm-body">
<b>公式：</b>节约金额 = （基准价 − 实际采购价）× 采购数量<br>
<b>基准价设定：</b>上年度同期均价 / 年初预算价 / 市场公开指数价，三者取高<br>
<b>适用：</b>A 类战略物料，月度核算
</div></div>
<div class="cm-card">
<div class="cm-name">📊 累计节约率</div>
<div class="cm-body">
<b>公式：</b>累计节约率 = 累计节约金额 ÷ 累计采购额 × 100%<br>
<b>目标值：</b>A 类 ≥ 3% / 年，B 类 ≥ 5% / 年，C 类 ≥ 2% / 年<br>
<b>适用：</b>采购团队 KPI 考核口径
</div></div>
<div class="cm-card">
<div class="cm-name">📈 毛利影响系数</div>
<div class="cm-body">
<b>公式：</b>毛利率影响 = 材料价格变动率 × 材料成本占比 × （1 − 成本传导率）<br>
<b>核心指标：</b>成本传导率——即价格向下游产品/定价传导的能力比例<br>
<b>适用：</b>品牌端定价决策，判断是否需要调整零售价
</div></div>
</div>"""

    sec_pm = f"""<details class="rpt-section section-target" id="priceMgmt" open>
<summary class="rpt-header"><span class="rpt-ico">🎯</span><span class="rpt-title">重点原材料价格管理体系 · ABC分级 + 预警 + 降本核算</span><span class="rpt-badge">ABC 三级 · 三级预警 · 三套核算</span><span class="rpt-chev">▾</span></summary>
<div class="rpt-body">
<div class="rpt-insight-callout"><span class="ic-ico">🎯</span><span class="ic-text">价格管理不是"买在最低点"，而是通过分级管理、预警响应、策略矩阵，将价格波动控制在可承受范围内，保障毛利率稳定。</span></div>
{pm_abc}
{pm_warn}
{pm_strategy}
{pm_cost}
</div></details>"""

    sec_external = f"""<details class="rpt-section section-target" id="extSection">
<summary class="rpt-header"><span class="rpt-ico">🌐</span><span class="rpt-title">外部价格源地图 · 向外洞察</span><span class="rpt-badge">27 个数据源 · 链接 2026-09-25 核实</span><span class="rpt-chev">▾</span></summary>
<div class="rpt-body">
<div class="rpt-summary"><b>半月刷新节奏：</b>{EXT_REFRESH} 上半月刷（上月 PPI 刚发布，第一时间解读成本传导）+ 下半月刷（可与行业追踪合并月度综述）。数据源从 16 个拓展至 <b>27 个</b>，新增国际锚点（Cotlook A / AWEX / ICE）、期货联动（新浪/东财）、五金基价（长江有色 / SMM / 永康指数）与宏观传导指标（原油 / 汇率 / PPI）。</div>
<div class="rh-grid">{rh_cards}</div>
{''.join(ext_blocks)}
</div></details>"""

    ch_rows = "".join(
        f'<div class="ch-row"><div class="ch-label" style="background:{color}">{esc(name)}</div>'
        f'<div class="ch-flow">'
        + "".join(
            (f'<span class="ch-arrow">→</span>' if i else "")
            + f'<span class="ch-node{"" if not k else " " + k}">{esc(txt)}</span>'
            for i, (k, txt) in enumerate(nodes)
        )
        + "</div></div>"
        for color, name, nodes in EXT_CHAINS
    )
    sec_chain = f"""<details class="rpt-section section-target" id="chainSection">
<summary class="rpt-header"><span class="rpt-ico">🔗</span><span class="rpt-title">成本传导链监控</span><span class="rpt-badge">上游异动 → 库内品类预警映射</span><span class="rpt-chev">▾</span></summary>
<div class="rpt-body">
<div class="chain">{ch_rows}</div>
<div class="rpt-summary" style="margin:12px 0 0"><b>预警规则：</b>上游节点（原油 / EMI / Cotlook A / 铜铝锌）单期波动 ≥5% → 对应下游库内品类列入<b>重点跟踪</b>；两项及以上上游同向异动 → 升级<b>预警</b>级，触发采购策略建议（提前锁价 / 推迟下单 / 替代料评估）。</div>
</div></details>"""

    sop_rows = "".join(
        f'<tr><td class="sop-step">{s}</td><td><b>{esc(a)}</b></td><td>{esc(d)}</td>'
        f'<td class="sop-out">{esc(o)}</td><td class="ext-dim">{esc(t)}</td></tr>'
        for s, a, d, o, t in EXT_SOP
    )
    sec_sop = f"""<details class="rpt-section section-target" id="sopSection">
<summary class="rpt-header"><span class="rpt-ico">⏱️</span><span class="rpt-title">半月刷新 SOP</span><span class="rpt-badge">{EXT_REFRESH} · D 日中午前交付</span><span class="rpt-chev">▾</span></summary>
<div class="rpt-body">
<table class="rpt-table sop-tbl"><thead><tr><th style="width:46px">步骤</th><th style="width:120px">动作</th><th>操作要点</th><th style="width:170px">输出成果</th><th style="width:110px">时限</th></tr></thead>
<tbody>{sop_rows}</tbody></table>
<div class="rpt-summary" style="margin:12px 0 0"><b>更新纪律：</b>刷新连分组明细一起改，勿只改 meta；低置信源（辅料/皮毛草/五金）每次以 1688 比价校准，连续 3 期验证后升级置信度标注；引用数据一律链接原文来源（可溯源）。</div>
</div></details>"""

    # ---- 纯 CSS 筛选规则 ----
    sec_archive = archive_section(periods or [], data)
    rc = [".page-wrap tr[data-mat],.page-wrap .hist-card{display:none}",
          "#mf-all:checked~.page-wrap tr[data-mat]{display:table-row}",
          "#mf-all:checked~.page-wrap .hist-card{display:block}",
          '#mf-all:checked~.page-wrap .mat-filter label[for="mf-all"]{background:var(--ink-900);border-color:var(--ink-900);color:#fff;box-shadow:none}']
    for m in materials:
        mid = m["id"]
        rc.append(f'#mf-{mid}:checked~.page-wrap tr[data-mat="{mid}"]{{display:table-row}}')
        rc.append(f'#mf-{mid}:checked~.page-wrap .hist-card[data-mat="{mid}"]{{display:block}}')
        rc.append(f'#mf-{mid}:checked~.page-wrap .mat-filter label[for="mf-{mid}"]{{background:var(--ink-900);border-color:var(--ink-900);color:#fff;box-shadow:none}}')
        rc.append(f'#mf-{mid}:checked~.page-wrap .sb-mat[for="mf-{mid}"]{{background:var(--ink-900);color:#fff}}')
        rc.append(f'#mf-{mid}:checked~.page-wrap .sb-mat[for="mf-{mid}"] .sb-ico{{color:#fff}}')
        rc.append(f'.find-{mid}{{display:none!important}}')
        rc.append(f'#mf-{mid}:checked~.page-wrap .find-{mid}{{display:inline!important}}')
    rc.append('.find{display:none}')
    rc.append('#mf-all:checked~.page-wrap .find-all{display:inline!important}')
    filter_css = "\n".join(rc)

    html = (
        "<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n<meta charset=\"UTF-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
        "<meta http-equiv=\"Cache-Control\" content=\"no-cache, no-store, must-revalidate\">\n"
        f"<title>{esc(meta.get('title', ''))} · {sub_suffix}</title>\n"
        f"<style>{CSS}{filter_css if mode == 'trend' else ''}</style>\n</head>\n<body>\n"
        f"{''.join(radios) if mode == 'trend' else ''}\n{topbar}\n{header}\n<div class=\"page-wrap\">\n{sidebar}\n"
        f'<main class="main-content">\n<div class="container">\n'
    )
    if mode == "trend":
        body = (
            f"{sec_trend}\n{sec_riskpanel}\n{sec_hist}\n{sec_table}\n{sec_archive}\n"
            f"</div>\n{footer}\n</main>\n</div>\n</body>\n</html>\n"
        )
    else:
        body = (
            f"{sec_collection}\n{sec_diagnosis}\n{sec_alert}\n{sec_insight}\n{sec_riskmap}\n{sec_deep}\n"
            f"{sec_futures}\n{sec_pm}\n"
            f"{sec_external}\n{sec_chain}\n{sec_sop}\n"
            f"</div>\n{footer}\n</main>\n</div>\n</body>\n</html>\n"
        )
    return html + body


CSS = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
--accent-900:#2B4C7E;--accent-700:#3D6394;--accent-600:#4A78B0;--accent-500:#5E8BC4;--accent-100:#EEF3F9;--accent-200:#D9E4F1;
--ink-900:#181818;--ink-800:#2A2A2A;--ink-700:#4A4A4A;--ink-600:#6B6B6B;--ink-500:#8A8A8A;--ink-400:#B0B0B0;--ink-100:#F5F5F3;
--line:#E9E9E5;--bg:#F3F3F1;--surface:#FFFFFF;--surface-soft:#F8F8F6;
--r-xl:16px;--r-xl:14px;--r-lg:12px;--r-sm:10px;--r-xs:8px;
--sh-sm:0 1px 2px rgba(24,24,24,.04);--sh-lg:0 4px 16px rgba(24,24,24,.05);--sh-lg:0 8px 24px rgba(24,24,24,.07);
--ease:cubic-bezier(.4,0,.2,1);--up:#9A4C46;--down:#477A54;
--fs-xs:11px;--fs-sm:12.5px;--fs-base:14.5px;--fs-md:16px;--fs-lg:19px;--fs-xl:25px;
--lh-tight:1.35;--lh-normal:1.55;--lh-relaxed:1.7;
--st-danger-bg:#FBEFEE;--st-danger-fg:#9A4C46;--st-danger-bd:#F2DDDB;
--st-warn-bg:#FBF6E8;--st-warn-fg:#8A6D2F;--st-warn-bd:#EFE1BF;
--st-safe-bg:#EEF7F0;--st-safe-fg:#477A54;--st-safe-bd:#CFE3D4;
--st-info-bg:#EEF3F9;--st-info-fg:#3D6394;--st-info-bd:#D0DCEC;
}
html{scroll-behavior:smooth}
body{font-family:Inter,"Noto Sans SC","PingFang SC","Hiragino Sans GB","Microsoft YaHei",system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
background:var(--bg);
color:var(--ink-700);line-height:var(--lh-relaxed);min-height:100vh;font-size:var(--fs-base);font-variant-numeric:tabular-nums;-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale}
::selection{background:var(--accent-200);color:var(--accent-900)}
::-webkit-scrollbar{width:9px;height:9px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:#C3D2EA;border-radius:999px;border:2px solid var(--bg)}
::-webkit-scrollbar-thumb:hover{background:var(--accent-500)}
a{color:var(--accent-600);text-decoration:none}
a:hover{text-decoration:underline}
svg text{font-family:inherit}
.mf-radio{position:absolute;opacity:0;pointer-events:none;width:0;height:0}
/* ---- 顶栏 ---- */
.kb-topbar{position:sticky;top:0;z-index:50;background:rgba(255,255,255,.9);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);border-bottom:1px solid var(--line)}
.kb-topbar-in{max-width:1180px;margin:0 auto;padding:11px 16px;display:flex;align-items:center;justify-content:space-between}
.kb-home{display:flex;align-items:center;gap:10px;font-weight:600;color:var(--ink-900);font-size:14.5px}
.kb-home:hover{text-decoration:none;opacity:.75}
.kb-home-logo{width:30px;height:30px;border-radius:8px;background:var(--ink-900);display:flex;align-items:center;justify-content:center;font-size:15px;box-shadow:none}
.kb-top-right{display:flex;align-items:center;gap:10px}
.kb-subnav{display:flex;gap:2px;background:var(--surface-soft);border:1px solid var(--line);border-radius:var(--r-sm);padding:3px}
.kb-subnav-item{display:inline-flex;align-items:center;padding:6px 14px;border-radius:6px;color:var(--ink-500);text-decoration:none;font-weight:500;font-size:12.5px;transition:all .15s;white-space:nowrap}
.kb-subnav-item:hover{color:var(--ink-800)}
.kb-subnav-item.active{background:var(--surface);color:var(--ink-900);font-weight:600;box-shadow:0 1px 2px rgba(24,24,24,.06);border:1px solid var(--line)}
.kb-status{font-size:11.5px;font-weight:500;color:var(--ink-600);background:var(--surface-soft);border:1px solid var(--line);border-radius:var(--r-xs);padding:5px 12px;white-space:nowrap}
.kb-back{display:inline-flex;align-items:center;gap:6px;font-size:12.5px;font-weight:500;color:var(--ink-600);background:var(--surface-soft);border:1px solid var(--line);border-radius:var(--r-xs);padding:6px 14px;transition:all .15s}
.kb-back:hover{color:var(--ink-900);border-color:var(--ink-400);text-decoration:none}
.kb-back .arrow{font-size:14px;line-height:1}
/* ---- 页头 ---- */
.header{background:var(--surface);border-bottom:1px solid var(--line);color:var(--ink-900);padding:28px 16px 24px;text-align:left;position:relative}
.header .header-in{max-width:1180px;margin:0 auto}
.header h1{font-size:1.5rem;font-weight:700;margin-bottom:.5rem;letter-spacing:-.01em}
.header .subtitle{font-size:.88rem;color:var(--ink-500);max-width:720px;line-height:1.65}
.header .badge{display:inline-block;background:var(--surface-soft);border:1px solid var(--line);border-radius:var(--r-xs);padding:.25rem .75rem;font-size:.72rem;color:var(--ink-500);margin-top:.7rem;font-weight:500}
/* ---- 侧边栏（悬停展开，负边距悬浮不挤压内容） ---- */
.page-wrap{display:flex;align-items:flex-start}
.sidebar{position:sticky;top:53px;height:calc(100vh - 53px);width:52px;flex-shrink:0;background:var(--surface);border-right:1px solid var(--line);overflow:hidden;transition:width .22s var(--ease),margin-right .22s var(--ease);z-index:40}
.sidebar:hover{width:220px;margin-right:-168px;box-shadow:var(--sh-md);background:var(--surface)}
.sb-toggle{display:flex;align-items:center;justify-content:center;width:100%;height:42px;border-bottom:1px solid var(--line);background:var(--surface);color:var(--ink-500)}
.sb-toggle svg{width:17px;height:17px;flex-shrink:0;transform:rotate(180deg);transition:transform .22s var(--ease)}
.sidebar:hover .sb-toggle svg{transform:rotate(0deg)}
.sb-toggle span{margin-left:8px;font-size:12px;font-weight:500;color:var(--ink-600);white-space:nowrap;opacity:0;transition:opacity .12s}
.sidebar:hover .sb-toggle span{opacity:1;transition-delay:.1s}
.sb-nav{padding:10px 8px 20px}
.sb-group{margin-bottom:16px}
.sb-group-title{font-size:10.5px;font-weight:600;color:var(--ink-400);letter-spacing:.06em;padding:0 10px 6px;white-space:nowrap;opacity:0;transition:opacity .12s;text-transform:uppercase}
.sidebar:hover .sb-group-title{opacity:1;transition-delay:.1s}
.sb-list{list-style:none}
.sb-list li{margin:1px 0}
.sb-list a,.sb-mat{display:flex;align-items:center;gap:10px;padding:7px 10px;border-radius:var(--r-sm);font-size:12.5px;font-weight:500;color:var(--ink-600);white-space:nowrap;cursor:pointer;transition:all .15s}
.sb-list a:hover,.sb-mat:hover{background:var(--surface-soft);color:var(--ink-900);text-decoration:none}
.sb-ico{width:18px;text-align:center;font-size:14px;flex-shrink:0;color:var(--ink-500)}
.sb-list a:hover .sb-ico,.sb-mat:hover .sb-ico{color:var(--ink-800)}
.sb-label{opacity:0;transition:opacity .12s}
.sidebar:hover .sb-label{opacity:1;transition-delay:.1s}
.sb-count{margin-left:auto;font-size:10.5px;font-weight:500;color:var(--ink-400);background:var(--surface-soft);border:1px solid var(--line);border-radius:var(--r-xs);padding:1px 6px;opacity:0;transition:opacity .12s}
.sidebar:hover .sb-count{opacity:1;transition-delay:.1s}
.main-content{flex:1;min-width:0}
.main-content .container{max-width:1180px;margin:0 auto;padding:0 16px 28px}
.section-target{scroll-margin-top:64px}
/* ---- 模块折叠（details/summary 纯CSS，企微兼容） ---- */
summary{list-style:none;cursor:pointer;-webkit-user-select:none;user-select:none}
summary::-webkit-details-marker{display:none}
summary:focus{outline:none}
.rpt-chev{display:inline-flex;align-items:center;margin-left:8px;font-size:11px;font-weight:500;color:var(--ink-500);transition:transform .18s;flex-shrink:0}
details[open]>summary>.rpt-chev{transform:rotate(180deg)}
.ov-sum{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.ov-sum:hover{color:var(--accent-700)}
details:not([open])>summary{margin-bottom:0}
details.rpt-section>summary.rpt-header:hover{background:#EFEFEC}
details.tbl-wrap:not([open]){padding-bottom:14px}
details.risk-panel:not([open])>summary{margin-bottom:0}
/* ---- 分析报告卡 ---- */
.rpt-section{margin:0 0 14px;background:var(--surface);border:1px solid var(--line);border-radius:var(--r-xl);box-shadow:var(--sh-sm);overflow:hidden;transition:box-shadow .2s}
.rpt-section:hover{box-shadow:var(--sh-lg)}
.rpt-header{display:flex;align-items:center;gap:10px;padding:14px 20px;background:var(--surface-soft);color:var(--ink-900);border-bottom:1px solid var(--line);cursor:pointer;list-style:none}
.rpt-header::-webkit-details-marker{display:none}
.rpt-header .rpt-ico{font-size:17px}
.rpt-header .rpt-title{font-size:var(--fs-base);font-weight:600;letter-spacing:.005em}
.rpt-header .rpt-badge{margin-left:auto;font-size:var(--fs-xs);font-weight:500;color:var(--ink-500);background:var(--surface);border:1px solid var(--line);border-radius:var(--r-xs);padding:3px 10px;white-space:nowrap}
.rpt-body{padding:18px 22px 20px}
.rpt-summary{background:var(--st-info-bg);border:1px solid var(--st-info-bd);border-radius:var(--r-xl);padding:14px 18px;margin-bottom:16px;font-size:var(--fs-sm);color:var(--ink-700);line-height:var(--lh-relaxed)}
.rpt-summary b{color:var(--accent-700)}
.rpt-score-card{display:flex;align-items:center;gap:16px;padding:12px 16px;border:1px solid var(--line);border-radius:var(--r-xl);margin-bottom:12px;background:var(--surface-soft)}
.rpt-score-val{font-size:26px;font-weight:700;color:var(--ink-900);font-family:ui-monospace,Menlo,Consolas,monospace;min-width:56px;text-align:center}
.rpt-score-val.low{color:var(--down)}.rpt-score-val.mid{color:var(--st-warn-fg)}.rpt-score-val.high{color:var(--up)}
.rpt-score-bar-wrap{flex:1}
.rpt-score-bar-label{font-size:var(--fs-xs);font-weight:600;color:var(--ink-600);margin-bottom:6px}
.rpt-score-bar{height:8px;border-radius:999px;background:#E6EDF6;overflow:hidden}
.rpt-score-bar-fill{height:100%;border-radius:999px}
.rpt-score-bar-fill.low{background:linear-gradient(90deg,var(--st-safe-fg),var(--st-safe-bd))}
.rpt-score-bar-fill.mid{background:linear-gradient(90deg,var(--st-warn-fg),var(--st-warn-bd))}
.rpt-score-bar-fill.high{background:linear-gradient(90deg,var(--st-danger-fg),var(--st-danger-bd))}
.rpt-dim-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}
.rpt-dim-card{border:1px solid var(--line);border-radius:var(--r-lg);padding:12px 14px;background:var(--surface);transition:border-color .15s,box-shadow .15s}
.rpt-dim-card:hover{border-color:var(--accent-500);box-shadow:var(--sh-sm)}
.rpt-dim-head{display:flex;align-items:center;justify-content:space-between;gap:6px;margin-bottom:8px}
.rpt-dim-name{font-size:var(--fs-sm);font-weight:700;color:var(--accent-900)}
.rpt-dim-label{font-size:10.5px;font-weight:700;padding:2px 8px;border-radius:999px;white-space:nowrap}
.rpt-dim-label.up,.rpt-dim-label.alert{background:var(--st-danger-bg);color:var(--st-danger-fg)}
.rpt-dim-label.flat,.rpt-dim-label.watch{background:var(--st-warn-bg);color:var(--st-warn-fg)}
.rpt-dim-label.down,.rpt-dim-label.safe{background:var(--st-safe-bg);color:var(--st-safe-fg)}
.rpt-dim-label.track{background:#FFEDD5;color:#C2410C}
.rpt-dim-score-row{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.rpt-dim-score{font-size:18px;font-weight:800;color:var(--accent-900);min-width:32px;font-family:ui-monospace,Menlo,Consolas,monospace}
.rpt-dim-bar{flex:1;height:6px;border-radius:999px;background:#E6EDF6;overflow:hidden}
.rpt-dim-bar-fill{height:100%;border-radius:999px}
.rpt-dim-bar-fill.low{background:linear-gradient(90deg,var(--st-safe-fg),var(--st-safe-bd))}
.rpt-dim-bar-fill.mid{background:linear-gradient(90deg,var(--st-warn-fg),var(--st-warn-bd))}
.rpt-dim-bar-fill.high{background:linear-gradient(90deg,var(--st-danger-fg),var(--st-danger-bd))}
.rpt-dim-detail{font-size:var(--fs-xs);color:var(--ink-600);line-height:var(--lh-normal)}
.rpt-table{width:100%;border-collapse:collapse;font-size:var(--fs-sm);margin-top:6px}
.rpt-table th{padding:10px 14px;text-align:left;background:var(--surface-soft);color:var(--ink-500);font-weight:600;font-size:var(--fs-xs);border-bottom:1px solid var(--line);letter-spacing:.02em}
.rpt-table td{padding:10px 14px;border-bottom:1px solid var(--line);color:var(--ink-700)}
.rpt-table tbody tr:hover{background:var(--surface-soft)}
.rpt-table .td-conf{font-weight:700;font-family:ui-monospace,Menlo,Consolas,monospace}
.rpt-table .td-conf.high{color:var(--down)}
.rpt-table .td-conf.mid{color:var(--st-warn-fg)}
.rpt-sub-title{font-size:var(--fs-base);font-weight:700;color:var(--accent-900);margin:20px 0 12px;letter-spacing:.01em}
.rpt-insight-callout{display:flex;gap:12px;align-items:flex-start;background:linear-gradient(135deg,#EFF5FF,#F7FAFF);border:1px solid #C7DBFB;border-left:4px solid var(--accent-700);border-radius:var(--r-lg);padding:12px 15px;margin-bottom:12px}
.rpt-insight-callout .ic-ico{font-size:20px;line-height:1}
.rpt-insight-callout .ic-text{font-size:.88rem;font-weight:600;color:var(--accent-900);line-height:1.6}
.rpt-takeaways{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}
.rpt-take-card{border:1px solid var(--line);border-left:4px solid var(--accent-600);border-radius:var(--r-lg);padding:11px 13px;background:var(--surface);display:flex;flex-direction:column;gap:8px;transition:box-shadow .15s,border-color .15s}
.rpt-take-card:hover{box-shadow:var(--sh-sm);border-color:var(--accent-500);border-left-color:var(--accent-600)}
.rpt-take-card.lv-act{border-left-color:var(--st-danger-fg);background:#FFF9F9}
.rpt-take-card.lv-act:hover{border-color:var(--st-danger-bd);border-left-color:var(--st-danger-fg)}
.rpt-take-card.lv-track{border-left-color:var(--st-warn-fg);background:#FFFCF5}
.rpt-take-card.lv-track:hover{border-color:#FCD34D;border-left-color:var(--st-warn-fg)}
.rpt-take-head{display:flex;align-items:center;gap:8px}
.rpt-take-tag{font-size:var(--fs-xs);font-weight:700;color:#fff;background:var(--accent-700);border-radius:999px;padding:3px 11px;white-space:nowrap}
.lv-act .rpt-take-tag{background:var(--st-danger-fg)}
.lv-track .rpt-take-tag{background:var(--st-warn-fg)}
.lv-watch .rpt-take-tag{background:var(--accent-600)}
.rpt-take-lv{margin-left:auto;font-size:10.5px;font-weight:700;padding:1px 8px;border-radius:999px;white-space:nowrap;background:var(--accent-100);color:var(--accent-700)}
.lv-act .rpt-take-lv{background:var(--st-danger-bg);color:var(--st-danger-fg)}
.lv-track .rpt-take-lv{background:var(--st-warn-bg);color:var(--st-warn-fg)}
.rpt-take-text{font-size:var(--fs-sm);color:var(--ink-700);line-height:var(--lh-relaxed);flex:1}
.rpt-take-text b.tk-num{font-weight:800;color:var(--accent-900);font-family:ui-monospace,Menlo,Consolas,monospace;font-size:calc(var(--fs-sm) + 1px)}
.rpt-take-act{display:flex;gap:8px;align-items:flex-start;background:var(--accent-100);border:1px solid var(--accent-200);border-radius:8px;padding:9px 12px;font-size:var(--fs-sm);font-weight:700;color:var(--accent-900);line-height:var(--lh-normal)}
.rpt-take-act .ta-ico{flex-shrink:0;font-size:13px;line-height:1.6}
.lv-act .rpt-take-act{background:var(--st-danger-bg);border-color:var(--st-danger-bd);color:var(--st-danger-fg)}
.lv-track .rpt-take-act{background:var(--st-warn-bg);border-color:var(--st-warn-bd);color:var(--st-warn-fg)}
@media(max-width:640px){.rpt-takeaways{grid-template-columns:1fr}}
/* ---- 风险地图 ---- */
.risk-stats{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:12px}
.risk-stat{flex:1;min-width:110px;border:1px solid var(--line);border-radius:var(--r-lg);padding:9px 12px;background:var(--surface);text-align:center}
.risk-stat .rs-num{font-size:22px;font-weight:800;font-family:ui-monospace,Menlo,Consolas,monospace}
.risk-stat .rs-label{font-size:11px;color:var(--ink-500);margin-top:2px}
.risk-stat.alert .rs-num{color:var(--st-danger-fg)}
.risk-stat.track .rs-num{color:#EA580C}
.risk-stat.watch .rs-num{color:var(--st-warn-fg)}
.risk-stat.safe .rs-num{color:var(--st-safe-fg)}
.risk-rows{display:flex;flex-direction:column;gap:8px}
.risk-row{display:flex;align-items:center;gap:12px;padding:9px 14px;border:1px solid var(--line);border-radius:var(--r-lg);background:#fff;flex-wrap:wrap}
.risk-row.top{border-color:var(--accent-500);box-shadow:var(--sh-sm);background:linear-gradient(135deg,#FFF7ED,#FFFBF5)}
.risk-row .rr-level{font-size:10.5px;font-weight:700;padding:2px 9px;border-radius:999px;white-space:nowrap;min-width:60px;text-align:center}
.risk-row .rr-level.alert{background:var(--st-danger-bg);color:var(--st-danger-fg)}
.risk-row .rr-level.track{background:#FFEDD5;color:#C2410C}
.risk-row .rr-level.watch{background:var(--st-warn-bg);color:var(--st-warn-fg)}
.risk-row .rr-level.safe{background:var(--st-safe-bg);color:var(--st-safe-fg)}
.risk-row .rr-name{font-size:13px;font-weight:700;color:var(--accent-900);min-width:160px}
.risk-row .rr-bar-wrap{flex:1;min-width:120px}
.risk-row .rr-bar{height:8px;border-radius:999px;background:#E6EDF6;overflow:hidden}
.risk-row .rr-bar-fill{height:100%;border-radius:999px}
.risk-row .rr-bar-fill.alert{background:linear-gradient(90deg,var(--st-danger-fg),var(--st-danger-bd))}
.risk-row .rr-bar-fill.track{background:linear-gradient(90deg,#EA580C,#FB923C)}
.risk-row .rr-bar-fill.watch{background:linear-gradient(90deg,var(--st-warn-fg),var(--st-warn-bd))}
.risk-row .rr-bar-fill.safe{background:linear-gradient(90deg,var(--st-safe-fg),var(--st-safe-bd))}
.risk-row .rr-score{font-size:15px;font-weight:800;font-family:ui-monospace,Menlo,Consolas,monospace;min-width:28px;text-align:right;color:var(--accent-900)}
.risk-row .rr-action{font-size:.76rem;color:var(--ink-500);flex:2;min-width:180px;line-height:1.45}
/* ---- 走势点评 ---- */
.trend{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-xl);padding:16px 20px;margin:0 0 14px;box-shadow:var(--sh-sm)}
.ov-title{font-size:12.5px;font-weight:600;color:var(--ink-500);letter-spacing:.04em;margin-bottom:14px;text-transform:uppercase}
.trend-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px}
.trend-card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-xl);padding:15px 17px;box-shadow:var(--sh-sm);transition:all .2s}
.trend-card:hover{box-shadow:var(--sh-md);border-color:var(--ink-400)}
.trend-card-head{display:flex;align-items:center;gap:10px;margin-bottom:10px}
.trend-card-ico{width:32px;height:32px;border-radius:var(--r-sm);background:var(--surface-soft);border:1px solid var(--line);display:flex;align-items:center;justify-content:center;font-size:15px}
.trend-card-title{font-size:var(--fs-base);font-weight:600;color:var(--ink-900)}
.trend-card-body{font-size:var(--fs-sm);color:var(--ink-600);line-height:var(--lh-relaxed);margin-bottom:12px}
.trend-card-body b.trend-num{font-weight:600;color:var(--ink-800)}
.trend-card-body b.trend-num.up{color:var(--st-danger-fg)}
.trend-card-body b.trend-num.down{color:var(--st-safe-fg)}
.trend-advice{background:var(--st-safe-bg);border:1px solid var(--st-safe-bd);border-radius:var(--r-lg);padding:11px 14px;font-size:.78rem;color:var(--st-safe-fg);line-height:1.6}
.trend-advice .ta-label{display:inline-flex;align-items:center;gap:4px;font-weight:600;color:var(--st-safe-fg);margin-bottom:4px;font-size:.76rem}
.trend-advice b.trend-num{font-weight:600;color:var(--st-safe-fg)}
.trend-advice b.trend-num.up{color:var(--st-danger-fg)}
/* ---- 异动预警 ---- */
.risk-panel{background:var(--surface);border:1px solid var(--st-danger-bd);border-radius:var(--r-xl);padding:16px 20px;margin:0 0 14px;box-shadow:var(--sh-sm)}
.risk-panel .ov-title{color:var(--st-danger-fg);margin-bottom:4px}
.risk-sub{font-size:12px;color:var(--ink-500);margin-bottom:12px}
.risk-list{display:flex;flex-direction:column;gap:8px}
.risk-item{display:flex;align-items:center;gap:10px;padding:10px 14px;border-radius:var(--r-lg);background:var(--st-warn-bg);border:1px solid var(--st-warn-bd);font-size:.82rem;flex-wrap:wrap}
.risk-item.alert{background:var(--st-danger-bg);border-color:var(--st-danger-bd)}
.risk-item .ri-name{font-weight:600;color:var(--ink-800);white-space:nowrap}
.risk-item .ri-pct{font-weight:600;font-family:ui-monospace,Menlo,Consolas,monospace;white-space:nowrap;font-variant-numeric:tabular-nums}
.risk-item .ri-note{color:var(--ink-500);margin-left:auto;text-align:right;font-size:.78rem}
.risk-tag{font-size:.7rem;font-weight:500;padding:2px 9px;border-radius:var(--r-xs);white-space:nowrap;border:1px solid transparent}
.risk-tag.watch{background:var(--st-warn-bg);color:var(--st-warn-fg);border-color:var(--st-warn-bd)}
.risk-tag.alert{background:var(--st-danger-bg);color:var(--st-danger-fg);border-color:var(--st-danger-bd)}
.risk-empty{font-size:.84rem;color:var(--down)}
/* ---- 历史走势 ---- */
.hist-section{margin:0 0 12px}
.hist-title{font-size:13px;font-weight:700;color:var(--accent-700);margin-bottom:11px}
.hist-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.hist-card{background:#fff;border:1px solid var(--line);border-radius:var(--r-lg);padding:12px 14px 14px;box-shadow:var(--sh-sm)}
.hist-head{display:flex;align-items:center;gap:7px;margin-bottom:8px}
.hist-ico{font-size:17px}
.hist-head b{font-size:.95rem;color:var(--accent-900)}
.hist-ref{font-size:.7rem;color:var(--ink-400);margin-left:auto;text-align:right}
.hist-cur{font-size:1.02rem;font-weight:800;color:var(--accent-900);margin-bottom:9px;font-family:ui-monospace,Menlo,Consolas,monospace;display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.hist-cur i{font-style:normal;font-size:.72rem;font-weight:500;color:var(--ink-500)}
.hist-cur .chg{font-size:.7rem;font-weight:700;padding:2px 8px;border-radius:var(--r-xs);background:var(--ink-100);display:inline-flex;align-items:center;gap:4px}
.hist-cur .chg.up{color:var(--up);background:var(--st-danger-bg)}
.hist-cur .chg.down{color:var(--down);background:#F0FDF4}
.hist-cur .chg.flat{color:var(--accent-700);background:var(--accent-100)}
.hist-cur .chg-label{font-size:.62rem;font-weight:600;color:var(--ink-500)}
.spark-row{display:flex;gap:12px}
.spark-col{flex:1;min-width:0}
.spark-ttl{font-size:.7rem;color:var(--ink-500);margin-bottom:3px}
.spark-col svg{display:block;width:100%}
.hist-note{font-size:.72rem;color:var(--ink-700);margin-top:9px;line-height:1.55;border-top:1px dashed var(--line);padding-top:8px}
/* ---- 报价明细 ---- */
.tbl-wrap{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-xl);padding:16px 18px 18px;box-shadow:var(--sh-sm);margin-bottom:14px}
.sc-overview{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-xl);padding:16px 20px;margin-bottom:14px;box-shadow:var(--sh-sm)}
.sc-overview .ov-title{margin-bottom:14px}
.sc-ov-stats{display:flex;flex-wrap:wrap;gap:16px 28px}
.sc-ov-stat{display:flex;flex-direction:column;background:var(--surface-soft);border:1px solid var(--line);border-radius:var(--r-lg);padding:12px 16px;min-width:110px}
.sc-ov-stat b{font-size:20px;font-weight:700;color:var(--ink-900);line-height:1.2;font-family:ui-monospace,Menlo,Consolas,monospace;font-variant-numeric:tabular-nums}
.sc-ov-stat b.up{color:var(--st-danger-fg)}
.sc-ov-stat b.down{color:var(--st-safe-fg)}
.sc-ov-stat span{font-size:11.5px;color:var(--ink-500);margin-top:4px}
.notes{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin-top:12px}
.note-card{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-lg);padding:12px 15px;box-shadow:var(--sh-sm)}
.note-card h4{font-size:.86rem;color:var(--ink-900);margin-bottom:6px;font-weight:600}
.note-card p{font-size:.76rem;color:var(--ink-500);line-height:1.6}
.mat-filter{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}
.mat-btn{padding:7px 14px;border:1px solid var(--line);background:var(--surface);border-radius:var(--r-sm);font-size:12.5px;font-weight:500;color:var(--ink-600);cursor:pointer;transition:all .15s;font-family:inherit}
.mat-btn:hover{border-color:var(--ink-400);color:var(--ink-900);background:var(--surface-soft)}
.tbl-ctrl{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:12px}
.tbl-ctrl .count{font-size:12px;color:var(--ink-500);font-weight:500}
.tbl-ctrl .hint{font-size:11.5px;color:var(--ink-400);margin-left:auto}
table.mp{width:100%;border-collapse:collapse;font-size:var(--fs-sm);line-height:var(--lh-normal)}
table.mp th,table.mp td{padding:11px 14px;text-align:left;border-bottom:1px solid var(--line)}
table.mp thead th{position:sticky;top:53px;background:var(--surface-soft);color:var(--ink-500);font-weight:600;font-size:12px;letter-spacing:.02em;border-bottom:1px solid var(--line);z-index:5}
table.mp tbody tr:nth-child(even):not(.group-row):not(:hover){background:var(--surface-soft)}
table.mp tbody tr:hover{background:#FAFAF8}
table.mp td.price{font-weight:600;color:var(--ink-900);font-family:ui-monospace,Menlo,Consolas,monospace;white-space:nowrap;font-size:var(--fs-sm);font-variant-numeric:tabular-nums}
table.mp tr.group-row td{background:var(--surface-soft);font-weight:600;color:var(--ink-800);font-size:var(--fs-sm);padding:12px 14px}
table.mp tr.group-row .unit{font-weight:500;color:var(--ink-500);background:var(--surface);border:1px solid var(--line);border-radius:var(--r-xs);padding:2px 8px;font-size:var(--fs-xs);margin-left:8px;white-space:nowrap}
table.mp tr.group-row .rng{font-weight:500;color:var(--ink-500);font-size:var(--fs-xs);margin-left:8px;white-space:nowrap}
table.mp tr.group-row .gsrc{font-weight:400;color:var(--ink-400);font-size:var(--fs-xs);margin-left:10px}
table.mp td.origin{color:var(--ink-500);font-size:var(--fs-xs);white-space:nowrap}
.risk-badge{font-size:.7rem;font-weight:500;padding:2px 8px;border-radius:var(--r-xs);margin-left:8px;white-space:nowrap;border:1px solid transparent}
.risk-badge.up{background:var(--st-danger-bg);color:var(--st-danger-fg);border-color:var(--st-danger-bd)}
.risk-badge.down{background:var(--st-safe-bg);color:var(--st-safe-fg);border-color:var(--st-safe-bd)}
/* ---- 期货管理 / 价格管理 模块 ---- */
.fut-tbl .fut-cat{color:var(--accent-900);font-weight:700}
.fut-tbl .fut-mkt{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.84rem;color:var(--ink-700)}
.fut-tbl .fut-rel{color:var(--ink-600);font-size:.86rem}
.fut-tbl .fut-exp{color:var(--accent-700);font-weight:600;font-size:.84rem}
.fut-act-list{margin:0;padding-left:16px;font-size:var(--fs-sm);color:var(--ink-700);line-height:var(--lh-relaxed)}
.fut-act-list li{margin-bottom:4px}
.fut-mat td{text-align:center;font-size:.86rem;vertical-align:middle}
.fut-mat .fut-pos{font-weight:700;text-align:left}
.fut-mat .fut-pos.up{color:var(--st-danger-fg)}
.fut-mat .fut-pos.mid{color:var(--st-warn-fg)}
.fut-mat .fut-pos.dn{color:var(--st-safe-fg)}
.mode-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:8px}
.mode-card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px;transition:all .2s}
.mode-card:hover{border-color:var(--accent-200);box-shadow:var(--sh-sm);transform:translateY(-1px)}
.mode-ico{font-size:22px;margin-bottom:8px}
.mode-name{font-weight:700;color:var(--accent-900);font-size:var(--fs-base);margin-bottom:8px}
.mode-desc{font-size:var(--fs-sm);color:var(--ink-600);line-height:var(--lh-relaxed)}
.risk-safeguard{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
.rs-item{display:flex;gap:10px;background:var(--accent-100,#F0F7FF);border:1px solid var(--accent-100);border-radius:10px;padding:13px 15px;font-size:var(--fs-sm);line-height:var(--lh-normal);color:var(--ink-700)}
.rs-ico{font-size:18px;flex-shrink:0;margin-top:1px}
.rs-item b{color:var(--accent-900)}
.pm-tbl .pm-a{background:var(--st-danger-bg,#FEF2F2);color:var(--st-danger-fg);font-weight:700}
.pm-tbl .pm-b{background:var(--st-warn-bg,#FFFBEB);color:var(--st-warn-fg);font-weight:700}
.pm-tbl .pm-c{background:var(--accent-100,#EFF6FF);color:var(--accent-700);font-weight:700}
.warn-ladder{display:flex;flex-direction:column;gap:10px;margin-bottom:8px}
.warn-item{border-radius:12px;overflow:hidden;border:1px solid var(--line)}
.wn-head{padding:11px 15px;display:flex;justify-content:space-between;align-items:center;font-weight:700;font-size:var(--fs-base)}
.wn-body{padding:12px 15px;background:var(--surface);font-size:var(--fs-sm);color:var(--ink-700);line-height:var(--lh-relaxed)}
.wn-body ul{margin:0;padding-left:20px}
.wn-body li{margin-bottom:3px}
.wn-blue .wn-head{background:var(--accent-100);color:var(--accent-900)}
.wn-amber .wn-head{background:var(--st-warn-bg);color:var(--st-warn-fg)}
.wn-red .wn-head{background:var(--st-danger-bg);color:var(--st-danger-fg)}
.wn-thresh{font-family:ui-monospace,Menlo,Consolas,monospace;font-weight:600;font-size:.82rem;opacity:.9}
.strat-mat td{text-align:center;font-size:.84rem;vertical-align:middle;line-height:1.6}
.strat-mat .pos-up{color:var(--st-danger-fg);font-weight:700;text-align:left}
.strat-mat .pos-mid{color:var(--st-warn-fg);font-weight:700;text-align:left}
.strat-mat .pos-dn{color:var(--st-safe-fg);font-weight:700;text-align:left}
.cost-methods{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.cm-card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px;transition:all .2s}
.cm-card:hover{border-color:var(--accent-200);box-shadow:var(--sh-sm)}
.cm-name{font-weight:700;color:var(--accent-900);font-size:var(--fs-base);margin-bottom:10px}
.cm-body{font-size:var(--fs-sm);color:var(--ink-700);line-height:var(--lh-relaxed)}
.cm-body b{color:var(--accent-700)}
/* ---- 页脚 ---- */
.footer{text-align:center;padding:22px 16px 26px;border-top:1px solid var(--line);background:#fff}
.footer .update-info{font-size:.82rem;color:var(--ink-400)}
.footer .update-info strong{color:var(--ink-700)}
.footer .copyright{font-size:.74rem;color:#CBD5E0;margin-top:.4rem}
/* ---- 价格体检（KPI / 动能 / 位置 / 联动） ---- */
.kpi-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:14px}
.kpi-tile{border:1px solid var(--line);border-radius:var(--r-lg);padding:10px 12px;background:var(--surface);text-align:center}
.kpi-tile .k-num{font-size:24px;font-weight:800;font-family:ui-monospace,Menlo,Consolas,monospace;line-height:1.15}
.kpi-tile .k-label{font-size:11px;font-weight:700;color:var(--ink-500);margin-top:2px}
.kpi-tile .k-sub{font-size:10.5px;color:var(--ink-400);margin-top:3px;line-height:1.45;min-height:15px}
.kpi-tile.up .k-num{color:var(--up)}
.kpi-tile.down .k-num{color:var(--down)}
.kpi-tile.warn .k-num{color:var(--st-warn-fg)}
.mom-tbl .m-name{font-weight:700;color:var(--accent-900);white-space:nowrap}
.mom-tbl .m-val{font-weight:700;font-family:ui-monospace,Menlo,Consolas,monospace;white-space:nowrap}
.mom-tbl .m-val.m-up{color:var(--up)}
.mom-tbl .m-val.m-dn{color:var(--down)}
.mom-tbl .m-val.m-flat{color:var(--ink-500)}
.mom-tbl .m-val.dim{color:var(--ink-400)}
.pos-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(215px,1fr));gap:10px}
.pos-card{border:1px solid var(--line);border-radius:var(--r-lg);padding:10px 12px;background:var(--surface)}
.pos-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:7px}
.pos-name{font-size:12.5px;font-weight:700;color:var(--accent-900)}
.pos-pct{font-size:15px;font-weight:800;font-family:ui-monospace,Menlo,Consolas,monospace;color:var(--ink-700)}
.pos-pct.hi{color:var(--up)}
.pos-pct.lo{color:var(--down)}
.pos-track{position:relative;height:10px;border-radius:999px;background:linear-gradient(90deg,var(--st-safe-bg) 0%,var(--st-safe-bg) 30%,#E6EDF6 30%,#E6EDF6 70%,var(--st-danger-bg) 70%,var(--st-danger-bg) 100%)}
.pos-dot{position:absolute;top:50%;transform:translate(-50%,-50%);width:14px;height:14px;border-radius:50%;border:2.5px solid #fff;box-shadow:0 1px 4px rgba(15,23,42,.35)}
.pos-meta{display:flex;justify-content:space-between;font-size:10.5px;color:var(--ink-400);margin-top:6px}
.pos-legend{display:flex;flex-wrap:wrap;gap:12px;margin-top:10px;font-size:10.5px;color:var(--ink-500)}
.pos-legend .lg{display:inline-flex;align-items:center;gap:5px}
.pos-legend .lg-lo::before{content:"";width:10px;height:10px;border-radius:3px;background:var(--st-safe-bg)}
.pos-legend .lg-mid::before{content:"";width:10px;height:10px;border-radius:3px;background:#E6EDF6}
.pos-legend .lg-hi::before{content:"";width:10px;height:10px;border-radius:3px;background:var(--st-danger-bg)}
.corr-wrap{overflow-x:auto}
/* ---- 往期价格档案 ---- */
.arch-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
table.arch{width:100%;border-collapse:collapse;font-size:.8rem}
table.arch th,table.arch td{padding:8px 12px;border-bottom:1px solid var(--line);white-space:nowrap}
table.arch thead th{position:sticky;top:53px;background:var(--surface-soft);color:var(--ink-500);font-weight:600;font-size:.78rem;border-bottom:1px solid var(--line);z-index:5}
table.arch thead th:first-child{text-align:left}
table.arch tbody tr:nth-child(even):not(.group-row):not(:hover){background:var(--surface-soft)}
table.arch tbody tr:hover{background:#FAFAF8}
table.arch td.a-name{font-weight:600;color:var(--ink-800)}
table.arch td.a-name small{color:var(--ink-400);font-weight:400;margin-left:4px}
table.arch td.a-val{font-family:ui-monospace,Menlo,Consolas,monospace;font-weight:600;font-variant-numeric:tabular-nums;text-align:right;color:var(--ink-800)}
table.arch tr.group-row td{background:var(--surface-soft);font-weight:600;color:var(--ink-700);font-size:.82rem;padding:9px 12px}
.arch-note{margin-top:8px;font-size:.72rem;color:var(--ink-400);line-height:1.55}
.focus-badge{display:inline-block;font-size:10px;font-weight:500;color:var(--accent-700);background:var(--st-info-bg);border:1px solid var(--st-info-bd);border-radius:var(--r-xs);padding:1px 7px;margin-left:6px;white-space:nowrap;vertical-align:1px}
.corr-tbl{table-layout:fixed;text-align:center}
.corr-tbl th{text-align:center;white-space:nowrap}
.corr-tbl .corr-row-h{text-align:left;white-space:nowrap}
.corr-tbl .corr-cell{text-align:center;font-family:ui-monospace,Menlo,Consolas,monospace;font-weight:700;font-size:.76rem;padding:6px 4px}
.corr-tbl .corr-cell.diag{background:var(--ink-100)!important;color:#CBD5E1}
.corr-tbl .corr-cell.dim{color:var(--ink-400)}
.corr-tbl .corr-cell.strong{outline:1.5px solid var(--accent-600);outline-offset:-1.5px}
.act-list{display:flex;flex-direction:column;gap:8px}
.act-row{border:1px solid var(--line);border-left:4px solid var(--accent-600);border-radius:var(--r-lg);padding:9px 13px;font-size:.82rem;color:var(--ink-700);background:var(--surface);line-height:1.6}
.act-row b{color:var(--accent-900)}
/* ---- 外部洞察（源地图 / 节奏 / 传导链 / SOP） ---- */
.rh-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:14px}
.rh-card{border:1px solid var(--line);border-radius:var(--r-lg);padding:11px 13px;background:var(--surface)}
.rh-card.hl{background:var(--accent-100);border-color:var(--accent-200)}
.rh-tag{display:inline-block;font-size:10.5px;font-weight:700;border-radius:var(--r-xs);padding:2px 9px;margin-bottom:6px}
.rh-tag.t-p0{background:var(--accent-900);color:#fff}
.rh-tag.t-p1{background:var(--accent-200);color:var(--accent-700)}
.rh-tag.t-macro{background:var(--st-warn-bg);color:var(--st-warn-fg)}
.rh-card h3{font-size:13.5px;font-weight:800;color:var(--accent-900);margin-bottom:4px}
.rh-card p{font-size:11.5px;color:var(--ink-500);line-height:1.55}
.ext-grp{display:flex;align-items:center;gap:8px;margin:14px 0 6px;font-size:13px;font-weight:800;color:var(--accent-900)}
.ext-grp:first-of-type{margin-top:0}
.ext-dot{width:9px;height:9px;border-radius:3px;flex-shrink:0}
.ext-dot.g0{background:var(--accent-900)}.ext-dot.g1{background:var(--accent-500)}.ext-dot.g2{background:#94A3B8}.ext-dot.g3{background:var(--st-warn-fg)}
.ext-hint{font-size:10.5px;font-weight:500;color:var(--ink-500)}
.ext-tbl{table-layout:fixed}
.ext-tbl td{word-break:break-word}
.ext-src{font-weight:700;white-space:nowrap}
.ext-src a{color:var(--accent-900);border-bottom:1px dashed #B7CBE8}
.ext-src a:hover{color:var(--accent-600)}
.ext-dim{color:var(--ink-400)}
.ext-ref{font-weight:700;color:var(--accent-700);white-space:nowrap}
.ext-b{display:inline-block;font-size:10px;font-weight:700;border-radius:var(--r-xs);padding:1px 7px;vertical-align:1px;white-space:nowrap}
.ext-b.new{background:var(--st-warn-bg);color:var(--st-warn-fg);border:1px solid var(--st-warn-bd)}
.ext-b.b-free{background:#ECFDF5;color:var(--st-safe-fg);border:1px solid var(--st-safe-bd)}
.ext-b.b-part{background:#EFF6FF;color:var(--accent-700);border:1px solid #BFDBFE}
.chain{display:flex;flex-direction:column;gap:9px}
.ch-row{display:flex;align-items:stretch;gap:8px;flex-wrap:wrap}
.ch-label{flex:0 0 100px;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:800;color:#fff;border-radius:var(--r-lg);padding:6px 8px;text-align:center;line-height:1.4}
.ch-flow{flex:1;display:flex;align-items:center;gap:5px;flex-wrap:wrap;border:1px dashed #CBD9EE;border-radius:var(--r-lg);padding:7px 10px;background:var(--surface)}
.ch-node{font-size:11px;font-weight:700;color:var(--ink-700);background:#fff;border:1px solid var(--line);border-radius:var(--r-xs);padding:3.5px 10px;white-space:nowrap}
.ch-node.src{border-color:#BFDBFE;background:var(--accent-100);color:var(--accent-700)}
.ch-node.dst{border-color:var(--st-warn-bd);background:#FFFBEB;color:var(--st-warn-fg)}
.ch-arrow{color:var(--ink-400);font-size:11px;font-weight:700}
.sop-tbl .sop-step{font-weight:800;color:var(--accent-700);font-size:13px;font-family:ui-monospace,Menlo,Consolas,monospace}
.sop-tbl .sop-out{color:var(--down);font-weight:700}
/* ---- 移动端 ---- */
@media (max-width:900px){
.page-wrap{display:block}
.sidebar{position:static;width:100%;height:auto;margin-right:0;border-right:none;border-bottom:1px solid var(--line);box-shadow:none;overflow:visible}
.sidebar:hover{width:100%;margin-right:0;box-shadow:none}
.sb-toggle{display:none}
.sb-nav{display:flex;flex-wrap:wrap;gap:4px;padding:10px 12px}
.sb-group{margin:0 4px 6px 0;width:100%}
.sb-group-title{display:block;opacity:1;padding:4px 0 4px}
.sb-list{display:flex;flex-wrap:wrap;gap:4px}
.sb-list a,.sb-mat{padding:5px 10px;background:var(--surface);border:1px solid var(--line);border-radius:999px;font-size:12px}
.sb-label,.sb-count{opacity:1}
.sb-label{display:inline}
.main-content{margin-left:0}
table.mp thead th{position:static}
.tbl-ctrl .hint{margin-left:0;width:100%}
.risk-item .ri-note{margin-left:0;text-align:left}
.rh-grid{grid-template-columns:1fr}
.kpi-grid{grid-template-columns:repeat(2,1fr)}
.ext-tbl,.ext-tbl th,.ext-tbl td{white-space:normal}
.ext-ref,.ext-dim{white-space:normal}
.ch-label{flex:1 1 100%}
}
"""


def main():
    base = Path(__file__).parent
    inp = sys.argv[1] if len(sys.argv) > 1 else None
    if not inp:
        cands = sorted(base.glob("material_prices_*.json"))
        if not cands:
            print("ERROR: no material_prices_*.json found")
            sys.exit(1)
        inp = cands[-1]
    outp = sys.argv[2] if len(sys.argv) > 2 else base / "index.html"
    data = json.loads(Path(inp).read_text(encoding="utf-8"))
    # Schema v1.0 兼容：新指标体系 → 旧格式
    if is_v1_format(data):
        print("检测到 Schema v1.0 (indicators 格式)，自动适配...")
        data = adapt_v1_to_old(data)
    periods = update_archive(base, data, Path(inp))
    # 价格趋势库
    doc_trend = build(data, periods, mode="trend")
    Path(outp).write_text(doc_trend, encoding="utf-8")
    print("OK -> %s (%d KB) · 趋势库" % (outp, len(doc_trend.encode("utf-8")) // 1024))
    # 行业分析建议
    insight_path = Path(outp).parent / "insight.html"
    doc_ins = build(data, periods, mode="insight")
    insight_path.write_text(doc_ins, encoding="utf-8")
    print("OK -> %s (%d KB) · 分析页" % (insight_path, len(doc_ins.encode("utf-8")) // 1024))
    print("   归档 %d 期" % len(periods))
    if Path(outp).name == "index.html":
        import export_archive_xlsx
        xlsx = export_archive_xlsx.export(base)
        if xlsx:
            print("OK -> %s" % xlsx)


if __name__ == "__main__":
    main()
