"""
旧版 material_prices_YYYYMMDD.json → Schema v1.0 迁移脚本

输入：旧格式 JSON（materials/groups/items 三层）
输出：新格式 JSON（indicators 指标体系 + calculated 自动计算）
"""
import json
import re
import statistics
from datetime import datetime, timedelta
from pathlib import Path

# ============================================================
# 1. 数据源字典
# ============================================================
SOURCE_MAP = {
    "中国棉花信息网":     {"code": "COTTON_CHINA", "grade": "A", "type": "行业协会", "confidence": 90},
    "中国棉花协会":       {"code": "COTTON_ASSN",  "grade": "A", "type": "行业协会", "confidence": 88},
    "国家棉花市场监测":   {"code": "COTTON_MON",   "grade": "A", "type": "行业协会", "confidence": 88},
    "中国茧丝绸交易市场": {"code": "SILK_EXCH",    "grade": "A", "type": "专业交易市场", "confidence": 88},
    "金蚕网":             {"code": "SILK_EXCH",    "grade": "A", "type": "专业交易市场", "confidence": 88},
    "南京羊毛市场":       {"code": "WOOL_NJ",      "grade": "A", "type": "专业交易市场", "confidence": 86},
    "国内绒毛监测":       {"code": "WOOL_MON",     "grade": "B", "type": "行业监测",   "confidence": 80},
    "羽绒金网":           {"code": "DOWN_GOLD",    "grade": "B", "type": "行业平台",   "confidence": 82},
    "中国羽绒信息网":     {"code": "DOWN_INFO",    "grade": "B", "type": "行业平台",   "confidence": 82},
    "中国化纤信息网":     {"code": "CCF",          "grade": "B", "type": "行业平台",   "confidence": 84},
    "中纤网":             {"code": "CCF",          "grade": "B", "type": "行业平台",   "confidence": 84},
    "隆众资讯":           {"code": "OILCHEM",      "grade": "B", "type": "产业链资讯", "confidence": 85},
    "石油化工纤维网":     {"code": "OILCHEM",      "grade": "B", "type": "产业链资讯", "confidence": 85},
    "金联创":             {"code": "JLC",          "grade": "B", "type": "产业链资讯", "confidence": 84},
    "生意社":             {"code": "RAWMEX",       "grade": "C", "type": "综合价格平台", "confidence": 80},
    "全球纺织网":         {"code": "GFTEX",        "grade": "C", "type": "产业平台",   "confidence": 75},
    "轻纺原料网":         {"code": "QINGFANG",     "grade": "C", "type": "产业带市场", "confidence": 76},
    "中国纺织原料网":     {"code": "SINOTEX",      "grade": "C", "type": "产业带市场", "confidence": 76},
    "柯桥指数":           {"code": "KEQIAO_IDX",   "grade": "B", "type": "行业指数",   "confidence": 86},
    "盛泽丝绸化纤指数":   {"code": "SHENGZE_IDX",  "grade": "B", "type": "行业指数",   "confidence": 84},
    "中国麻纺":           {"code": "CHINA_FLAX",   "grade": "B", "type": "行业协会",   "confidence": 78},
    "四川大竹产区":       {"code": "DAZHU",        "grade": "C", "type": "产地报价",   "confidence": 72},
    "绒毛交易市场":       {"code": "CASHMERE_MKT", "grade": "B", "type": "专业市场",   "confidence": 80},
    "鄂尔多斯羊绒指数":   {"code": "ERDOS_IDX",    "grade": "B", "type": "行业指数",   "confidence": 82},
    "马海毛行情":         {"code": "MOHAIR_MKT",   "grade": "C", "type": "市场调研",   "confidence": 72},
    "牦牛绒行情":         {"code": "YAK_MKT",      "grade": "C", "type": "市场调研",   "confidence": 72},
    "上海期货交易所":     {"code": "SHFE",         "grade": "A", "type": "期货交易所", "confidence": 92},
    "长江有色金属网":     {"code": "CCMN",         "grade": "B", "type": "金属资讯",   "confidence": 84},
    "温州皮革市场":       {"code": "WENLEATHER",   "grade": "C", "type": "产业带市场", "confidence": 72},
    "东莞皮革市场":       {"code": "DGLEATHER",    "grade": "C", "type": "产业带市场", "confidence": 72},
    "崇福皮草城":         {"code": "CHONGFU",      "grade": "C", "type": "产业带市场", "confidence": 72},
    "毛皮市场行情":       {"code": "FUR_MKT",      "grade": "C", "type": "市场调研",   "confidence": 70},
    "服装辅料市场行情":   {"code": "TRIM_MKT",     "grade": "C", "type": "市场调研",   "confidence": 72},
    "高端面料市场行情":   {"code": "PREMIUM_FAB",  "grade": "D", "type": "市场调研",   "confidence": 68},
    "棉纺/纱线市场行情":  {"code": "YARN_MKT",     "grade": "C", "type": "市场调研",   "confidence": 76},
    "缝制辅料市场行情":   {"code": "SEW_MKT",      "grade": "C", "type": "市场调研",   "confidence": 72},
    "五金市场行情":       {"code": "HW_MKT",       "grade": "C", "type": "市场调研",   "confidence": 72},
    "皮革市场行情":       {"code": "LEATHER_MKT",  "grade": "C", "type": "市场调研",   "confidence": 72},
    "辅料装饰市场行情":   {"code": "DECOR_MKT",    "grade": "D", "type": "市场调研",   "confidence": 68},
    "纸类塑料行情":       {"code": "PAPER_MKT",    "grade": "D", "type": "市场调研",   "confidence": 66},
    "中国·柯桥纺织指数":  {"code": "KEQIAO_IDX",   "grade": "B", "type": "行业指数",   "confidence": 86},
}

def parse_sources(source_str):
    """从自由文本中解析数据源列表，返回 [{source_code, source_name, grade}]"""
    results = []
    found_codes = set()
    for name, info in SOURCE_MAP.items():
        if name in source_str and info["code"] not in found_codes:
            results.append({
                "source_code": info["code"],
                "source_name": name,
                "grade": info["grade"],
            })
            found_codes.add(info["code"])
    return results


# ============================================================
# 2. 指标编码生成
# ============================================================
CATEGORY_PREFIX = {
    "huaxian": "CHEM",
    "mian": "COT",
    "ma": "FLAX",
    "si": "SILK",
    "mao": "WOOL",
    "rongyu": "DOWN",
    "piymc": "FUR",
    "fuliao": "TRIM",
    "shaxian": "YARN",
    "fengrenxian": "SEW",
    "wujin": "HW",
    "pige": "LEATHER",
}

def sanitize_code(name):
    """从品名提取规格特征生成代码后缀"""
    name = name.replace("（", "(").replace("）", ")")
    # 提取括号内外
    m = re.match(r"(.+?)\s*(?:[（(](.+?)[）)])?$", name)
    if m:
        base = m.group(1).strip()
    else:
        base = name.strip()

    # 常见规格关键词
    specs = []
    patterns = [
        (r"(\d+D)/?(\d+F)?", "D"),
        (r"(\d+\.?\d*μm)", "UM"),
        (r"(\d+Nm)/?(\d+)?", "NM"),
        (r"(\d+S)", "S"),
        (r"(\d+支)", "S"),
        (r"(\d+\.?\d*%)", "PCT"),
        (r"(\d+A)", "A"),
    ]
    for pat, tag in patterns:
        m2 = re.search(pat, base)
        if m2:
            specs.append(m2.group(0).replace("/", "_").replace(".", "p"))
            break

    # 如果没提取到数字规格，用拼音首字母
    if not specs:
        # 取前4个汉字拼音首字母（简化：直接取前4个非数字字符）
        clean = re.sub(r"[^\u4e00-\u9fa5a-zA-Z]", "", base)[:6]
        specs.append(clean)

    return "_".join(specs[:2]).upper()


def make_indicator_code(cat_id, item_name, idx=0):
    prefix = CATEGORY_PREFIX.get(cat_id, "MAT")
    spec = sanitize_code(item_name)
    code = f"{prefix}_{spec}"
    if idx > 0:
        code += f"_{idx+1}"
    return code


# ============================================================
# 3. 自动计算模块
# ============================================================
def compute_center_price(sources):
    """多源价 → 中位数（抗异常值）"""
    prices = [s["price"] for s in sources if s.get("price")]
    if not prices:
        return None
    if len(prices) == 1:
        return prices[0]
    return statistics.median(prices)


def compute_dispersion(sources, center_price):
    """价格离散度 = (max-min)/center_price * 100%"""
    prices = [s["price"] for s in sources if s.get("price")]
    if len(prices) < 2 or not center_price:
        return 0.0
    spread = max(prices) - min(prices)
    return round(spread / center_price * 100, 2)


def compute_confidence(sources, dispersion):
    """可信度 = 源等级加权 + 源数量 - 离散度惩罚
    high / medium / low
    """
    if not sources:
        return "low"

    grade_score = {"A": 35, "B": 28, "C": 20, "D": 12}
    count_score = min(len(sources) * 8, 24)  # 最多24分

    total = 0
    for s in sources:
        g = s.get("grade", "D")
        total += grade_score.get(g, 10)
    total = total / len(sources) + count_score

    # 离散度惩罚：>5% 扣10分，>10%扣20分
    if dispersion > 10:
        total -= 20
    elif dispersion > 5:
        total -= 10

    if total >= 55:
        return "high"
    elif total >= 35:
        return "medium"
    else:
        return "low"


def compute_changes(history):
    """从扁平history计算日/周/月/季/年涨跌幅
    history: [{date, center_price}, ...] 升序，date 为字符串 YYYY-MM-DD
    """
    if not history or len(history) < 2:
        return {}

    latest = history[-1]
    latest_price = latest["center_price"]
    latest_date = datetime.strptime(latest["date"], "%Y-%m-%d").date()

    def find_n_days_ago(n_days):
        target = latest_date - timedelta(days=n_days)
        # 找最接近且早于等于目标日期的
        best = None
        for h in history[:-1]:
            hd = datetime.strptime(h["date"], "%Y-%m-%d").date()
            if hd <= target:
                best = h
            else:
                break
        return best

    changes = {}
    windows = [
        ("day", 1),
        ("week", 7),
        ("month", 30),
        ("quarter", 90),
        ("year", 365),
    ]
    for key, days in windows:
        ref = find_n_days_ago(days)
        if ref and ref["center_price"]:
            pct = (latest_price - ref["center_price"]) / ref["center_price"] * 100
            changes[f"{key}_change_pct"] = round(pct, 2)

    return changes


def compute_moving_averages(history):
    """计算MA20 / MA60"""
    if len(history) < 5:
        return {}

    prices = [h["center_price"] for h in history if h.get("center_price")]
    if not prices:
        return {}

    ma = {}
    for period in [20, 60]:
        if len(prices) >= period:
            ma[f"ma{period}"] = round(sum(prices[-period:]) / period, 2)
        elif len(prices) >= 5:
            # 数据不足时用现有数据近似（标记为近似？暂时直接算）
            ma[f"ma{period}"] = round(sum(prices) / len(prices), 2)
    return {"moving_average": ma} if ma else {}


def compute_percentile(history):
    """12个月价格分位"""
    if len(history) < 5:
        return {}

    prices = sorted([h["center_price"] for h in history if h.get("center_price")])
    if not prices:
        return {}

    latest = history[-1]["center_price"]
    # 简单百分位：低于当前价的比例
    below = sum(1 for p in prices if p < latest)
    pct = round(below / len(prices) * 100)

    return {
        "high_12m": max(prices),
        "low_12m": min(prices),
        "percentile_12m": pct,
    }


def compute_trend(month_change_pct=None):
    """趋势判断（P1简化版：按月涨跌判断方向）
    后续可升级为波动率自适应
    """
    if month_change_pct is None:
        return {"trend_direction": "flat", "trend_label": "→ 横盘"}

    if month_change_pct > 8:
        return {"trend_direction": "up_strong", "trend_label": "🚀 快速上涨"}
    elif month_change_pct > 2:
        return {"trend_direction": "up_mild", "trend_label": "↗ 温和上涨"}
    elif month_change_pct < -8:
        return {"trend_direction": "down_strong", "trend_label": "📉 快速下跌"}
    elif month_change_pct < -2:
        return {"trend_direction": "down_mild", "trend_label": "↘ 温和下跌"}
    else:
        return {"trend_direction": "flat", "trend_label": "→ 横盘"}


def compute_price_position(percentile_12m=None):
    if percentile_12m is None:
        return {"price_position": "未知"}
    if percentile_12m >= 80:
        return {"price_position": "高位"}
    elif percentile_12m >= 30:
        return {"price_position": "中位"}
    else:
        return {"price_position": "低位"}


def calculate_all(indicator):
    """主计算入口：给单个 indicator 填充 calculated"""
    sources = indicator.get("sources", [])
    history = indicator.get("history", [])

    calc = {}

    # 中枢价 + 价格区间
    center = compute_center_price(sources)
    if center:
        calc["center_price"] = round(center, 2)
        prices_list = [s["price"] for s in sources if s.get("price")]
        calc["source_price_range"] = {
            "min": min(prices_list),
            "max": max(prices_list),
        }
    calc["source_count"] = len(sources)

    # 离散度 + 可信度
    disp = compute_dispersion(sources, center) if center else 0
    calc["price_dispersion"] = disp
    calc["confidence"] = compute_confidence(sources, disp)

    # 涨跌幅
    changes = compute_changes(history)
    calc.update(changes)

    # 均线
    ma_result = compute_moving_averages(history)
    calc.update(ma_result)

    # 历史分位 + 高低
    pct_result = compute_percentile(history)
    calc.update(pct_result)

    # 趋势
    trend = compute_trend(calc.get("month_change_pct"))
    calc.update(trend)

    # 价格位置
    pos = compute_price_position(calc.get("percentile_12m"))
    calc.update(pos)

    indicator["calculated"] = calc
    return indicator


# ============================================================
# 4. 主迁移逻辑
# ============================================================
def migrate(old_file, new_file):
    with open(old_file, encoding="utf-8") as f:
        old = json.load(f)

    meta = old.get("meta", {})
    old_materials = old.get("materials", [])
    old_groups = old.get("groups", [])
    old_reports = old.get("reports", {})

    # 构建材料大类索引
    mat_index = {m["id"]: m for m in old_materials}

    # ---- 收集所有数据源 ----
    all_sources = {}  # code → info

    def register_source(name):
        if name in SOURCE_MAP:
            info = SOURCE_MAP[name]
            code = info["code"]
            if code not in all_sources:
                all_sources[code] = {
                    "code": code,
                    "name": name,
                    "type": info["type"],
                    "grade": info["grade"],
                    "base_url": "",
                    "coverage": "",
                    "update_freq": "",
                    "confidence": info["confidence"],
                }

    # 从 reports.collection.sources 收集
    for s in old_reports.get("collection", {}).get("sources", []):
        name = s.get("name", "")
        # 尝试匹配
        for known_name, info in SOURCE_MAP.items():
            if known_name in name:
                if info["code"] not in all_sources:
                    all_sources[info["code"]] = {
                        "code": info["code"],
                        "name": known_name,
                        "type": s.get("type", info["type"]),
                        "grade": info["grade"],
                        "base_url": "",
                        "coverage": s.get("coverage", ""),
                        "update_freq": s.get("update_freq", ""),
                        "confidence": s.get("confidence", info["confidence"]),
                    }
                break

    # ---- 构建 indicators ----
    indicators = []
    used_codes = set()
    groups_new = []  # 新结构的展示分组

    for mat in old_materials:
        mat_id = mat["id"]
        mat_name = mat["name"]
        icon = mat.get("icon", "")
        subgroups = []

        # 大类指数 indicator（如果有 history）
        if "history" in mat and mat["history"].get("periods"):
            h = mat["history"]
            # 扁平 history
            flat_hist = flatten_history(h["periods"])
            ref = h.get("ref", mat_name)
            unit = h.get("unit", "")
            current = h.get("current")

            ind_code = f"{CATEGORY_PREFIX.get(mat_id, 'MAT')}_IDX"
            sources_raw = parse_sources_from_index(mat_id, ref)
            # 给源填当前价
            sources = []
            for si, s in enumerate(sources_raw):
                if si == 0 and current is not None:
                    sources.append({
                        "source_code": s["source_code"],
                        "source_name": s["source_name"],
                        "grade": s["grade"],
                        "price": current,
                        "date": meta.get("updated", ""),
                        "price_caliber": ref,
                        "source_url": "",
                    })

            indicator = {
                "indicator_code": ind_code,
                "name": ref,
                "icon": icon,
                "definition": {
                    "category": mat_name,
                    "subcategory": mat_name + "指数",
                    "specification": "综合指数",
                    "market": "国内",
                    "unit": unit,
                    "price_type": "指数价",
                },
                "is_index": True,
                "sources": sources,
                "history": flat_hist,
            }
            calculate_all(indicator)
            indicators.append(indicator)
            used_codes.add(ind_code)

        # 找属于这个大类的 group
        mat_groups = [g for g in old_groups if g.get("material") == mat_id]

        for g in mat_groups:
            g_name = g["name"]
            g_unit = g.get("unit", "")
            g_source = g.get("source", "")
            g_items = g.get("items", [])
            g_history = g.get("history", {})

            # 解析 group 的数据源
            g_sources = parse_sources(g_source)

            # 如果 group 有 history，把它赋给第一个 item（代表品）
            rep_hist = flatten_history(g_history.get("periods", [])) if g_history.get("periods") else []

            item_codes = []
            for idx, item in enumerate(g_items):
                item_name = item["name"]
                spec = item.get("spec", "")
                origin = item.get("origin", "国内")
                price = item.get("price")
                focus = item.get("focus", False)

                # 生成 indicator_code
                code = make_indicator_code(mat_id, item_name, 0)
                # 去重
                base_code = code
                dup = 0
                while code in used_codes:
                    dup += 1
                    code = f"{base_code}_{dup}"
                used_codes.add(code)

                # 构建 sources：从 group 的源 + 当前价格
                item_sources = []
                if g_sources:
                    # 第一个源赋当前价格
                    for si, s in enumerate(g_sources):
                        src_price = price if si == 0 else None  # 只有第一个源有明确价格
                        if src_price is not None:
                            item_sources.append({
                                "source_code": s["source_code"],
                                "source_name": s["source_name"],
                                "grade": s["grade"],
                                "price": src_price,
                                "date": meta.get("updated", ""),
                                "price_caliber": g_source[:80],
                                "source_url": "",
                            })
                else:
                    # 没识别到源，用占位
                    item_sources.append({
                        "source_code": "MARKET",
                        "source_name": "市场综合",
                        "grade": "D",
                        "price": price,
                        "date": meta.get("updated", ""),
                        "price_caliber": g_source[:60],
                        "source_url": "",
                    })

                # history：第一个 item 用 group history，其余空或简化
                hist = rep_hist if idx == 0 and rep_hist else []

                indicator = {
                    "indicator_code": code,
                    "name": item_name,
                    "icon": icon,
                    "focus": focus,
                    "definition": {
                        "category": mat_name,
                        "subcategory": g_name,
                        "specification": spec or item_name,
                        "market": origin,
                        "unit": g_unit or "",
                        "price_type": "市场价",
                    },
                    "sources": item_sources,
                    "history": hist,
                }
                calculate_all(indicator)
                indicators.append(indicator)
                item_codes.append(code)

            subgroups.append({
                "sub_name": g_name,
                "unit": g_unit,
                "source": g_source,
                "indicator_codes": item_codes,
            })

        groups_new.append({
            "category_code": mat_id,
            "category_name": mat_name,
            "icon": icon,
            "subgroups": subgroups,
        })

    # ---- 构建 trend_reports ----
    trend_reports = []
    for t in meta.get("trend", []):
        # 提取分类名
        m = re.match(r"【(.+?)】(.+)", t, re.S)
        if m:
            category = m.group(1)
            content = m.group(2).strip()
            trend_reports.append({"category": category, "content": content})
        else:
            trend_reports.append({"category": "总览", "content": t.strip()})

    # ---- 组装新结构 ----
    new_data = {
        "schema_version": "1.0",
        "meta": {
            "title": meta.get("title", ""),
            "subtitle": meta.get("subtitle", ""),
            "updated": meta.get("updated", ""),
            "market": meta.get("market", {}),
        },
        "data_sources": list(all_sources.values()),
        "indicators": indicators,
        "groups": groups_new,
        "trend_reports": trend_reports,
        "reports": old_reports,  # 保留原 reports（diagnosis/risk_map 等）
    }

    with open(new_file, "w", encoding="utf-8") as f:
        json.dump(new_data, f, ensure_ascii=False, indent=1)

    print(f"迁移完成：{new_file}")
    print(f"  指标数：{len(indicators)}")
    print(f"  数据源：{len(all_sources)}")
    print(f"  展示分组：{len(groups_new)} 大类 / {sum(len(g['subgroups']) for g in groups_new)} 细分")
    return new_data


def flatten_history(periods):
    """把 periods 数组（近1月/近1季度/近1年）合并为扁平 history[]
    取最新一期的每个日期点，去重
    """
    date_map = {}
    for p in periods:
        pname = p.get("name", "")
        data = p.get("data", [])
        for d_point in data:
            if len(d_point) < 2:
                continue
            date_str = d_point[0]
            price = d_point[1]
            # 规范化日期格式
            date_obj = normalize_date(date_str)
            if date_obj:
                date_map[date_obj] = price

    # 按日期升序
    sorted_dates = sorted(date_map.keys())
    result = []
    for d in sorted_dates:
        result.append({
            "date": d,
            "prices": {},  # 旧数据没有多源历史，留空
            "center_price": date_map[d],
        })
    return result


def normalize_date(date_str):
    """把 '08-24' 或 '2026-08-24' 等格式统一为 YYYY-MM-DD"""
    date_str = str(date_str).strip()
    # 已经是 YYYY-MM-DD
    if re.match(r"\d{4}-\d{2}-\d{2}", date_str):
        return date_str[:10]
    # MM-DD 格式，补年份（假设是当前年份）
    m = re.match(r"(\d{1,2})-(\d{1,2})", date_str)
    if m:
        month = int(m.group(1))
        day = int(m.group(2))
        # 假设当前年份
        return f"2026-{month:02d}-{day:02d}"
    return None


def parse_sources_from_index(mat_id, ref):
    """从大类指数名推断源"""
    sources_map = {
        "huaxian": [{"source_code": "SHENGZE_IDX", "source_name": "盛泽丝绸化纤指数", "grade": "B"}],
        "mian":    [{"source_code": "COTTON_CHINA", "source_name": "中国棉花信息网", "grade": "A"}],
        "ma":      [{"source_code": "CHINA_FLAX", "source_name": "中国麻纺", "grade": "B"}],
        "si":      [{"source_code": "SILK_EXCH", "source_name": "中国茧丝绸交易市场", "grade": "A"}],
        "mao":     [{"source_code": "WOOL_NJ", "source_name": "南京羊毛市场", "grade": "A"}],
        "rongyu":  [{"source_code": "DOWN_GOLD", "source_name": "羽绒金网", "grade": "B"}],
        "piymc":   [{"source_code": "WENLEATHER", "source_name": "温州皮革市场", "grade": "C"}],
    }
    return sources_map.get(mat_id, [{"source_code": "MARKET", "source_name": "市场综合", "grade": "C"}])


# ============================================================
# 运行
# ============================================================
if __name__ == "__main__":
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else "material_prices_20260922.json"
    dst = Path(src).stem.replace("material_prices_", "indicators_") + ".json"
    migrate(src, dst)
