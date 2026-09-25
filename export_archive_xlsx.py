import json
import re
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

HDR_FILL = PatternFill("solid", fgColor="1A365D")
HDR_FONT = Font(name="Arial", bold=True, color="FFFFFF", size=10)
BODY_FONT = Font(name="Arial", size=10)
BOLD_FONT = Font(name="Arial", size=10, bold=True)
FOCUS_FILL = PatternFill("solid", fgColor="EAF2FF")
ZEBRA_FILL = PatternFill("solid", fgColor="F7F9FC")
THIN = Side(style="thin", color="D9DEE7")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center")


def load_periods(base):
    rows, snapshots, dates = [], [], []
    for fp in sorted(Path(base, "archive").glob("material_prices_*.json")):
        d = json.loads(fp.read_text(encoding="utf-8"))
        date = (d.get("meta") or {}).get("updated") or fp.stem.split("_")[-1]
        if date not in dates:
            dates.append(date)
        mk = (d.get("meta") or {}).get("market") or {}
        if mk.get("index") is not None:
            snapshots.append((date, mk))
        mat_name = {m["id"]: m["name"] for m in d.get("materials", [])}
        for g in d.get("groups", []):
            for it in g.get("items", []):
                rows.append({
                    "date": date, "cat": mat_name.get(g["material"], g["material"]),
                    "group": g["name"], "name": it["name"], "spec": it.get("spec") or "—",
                    "origin": it.get("origin") or "—", "unit": g.get("unit", ""),
                    "price": it.get("price"), "focus": bool(it.get("focus")),
                    "source": g.get("source") or "—",
                })
    return sorted(dates), rows, snapshots


def style_header(ws, ncols, height=22):
    for c in range(1, ncols + 1):
        cell = ws.cell(1, c)
        cell.fill, cell.font, cell.border, cell.alignment = HDR_FILL, HDR_FONT, BORDER, CENTER
    ws.row_dimensions[1].height = height


def set_widths(ws, widths):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def export(base):
    dates, rows, snapshots = load_periods(base)
    if not dates:
        return None
    wb = Workbook()

    ws = wb.active
    ws.title = "价格明细"
    cols = ["日期", "大类", "细分品类", "品名/规格档", "规格/说明", "产地", "单位", "参考价", "我司主力", "来源"]
    ws.append(cols)
    for r in sorted(rows, key=lambda x: (x["date"], x["cat"], x["group"])):
        ws.append([r["date"], r["cat"], r["group"], r["name"], r["spec"], r["origin"],
                   r["unit"], r["price"], "★" if r["focus"] else "", r["source"]])
    n = ws.max_row
    for row in ws.iter_rows(min_row=2, max_row=n, max_col=10):
        for cell in row:
            cell.border, cell.font = BORDER, BODY_FONT
            if cell.column == 8:
                cell.number_format = "#,##0"
            if cell.column in (1, 6, 9):
                cell.alignment = CENTER
        if (row[0].row % 2) == 1:
            for cell in row:
                cell.fill = ZEBRA_FILL
        if row[8].value == "★":
            for cell in row:
                cell.fill = FOCUS_FILL
    style_header(ws, 10)
    set_widths(ws, [11, 14, 12, 22, 30, 8, 9, 10, 9, 38])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:J{n}"

    ws2 = wb.create_sheet("跨期对比")
    ws2.append(["大类", "细分品类", "品名/规格档", "单位", "我司主力"] + dates + ["最新环比"])
    by_key = {}
    for r in rows:
        by_key.setdefault((r["cat"], r["group"], r["name"]), {})[r["date"]] = r
    order = sorted(by_key, key=lambda k: (k[0], k[1], k[2]))
    first_data, last_data = 2, 0
    for key in order:
        per = by_key[key]
        latest = per[dates[-1]] if dates[-1] in per else None
        ws2.append([
            key[0], key[1], key[2], latest["unit"] if latest else "",
            "★" if latest and latest["focus"] else "",
            *[per.get(dt, {}).get("price") for dt in dates], None,
        ])
    n2 = ws2.max_row
    p_first, p_last = 6, 5 + len(dates)
    for row in ws2.iter_rows(min_row=2, max_row=n2, max_col=p_last + 1):
        for cell in row:
            cell.border, cell.font = BORDER, BODY_FONT
            if p_first <= cell.column <= p_last:
                cell.number_format = "#,##0"
        if (row[0].row % 2) == 1:
            for cell in row:
                cell.fill = ZEBRA_FILL
        if row[4].value == "★":
            for cell in row:
                cell.fill = FOCUS_FILL
        c_new, c_old = get_column_letter(p_last), get_column_letter(p_last - 1)
        if len(dates) >= 2:
            row[p_last].value = f"=IF(OR({c_old}{row[0].row}=\"\",{c_new}{row[0].row}=\"\"),\"\",({c_new}{row[0].row}-{c_old}{row[0].row})/{c_old}{row[0].row})"
        row[p_last].number_format = "0.0%;-0.0%;\"-\""
    style_header(ws2, p_last + 1)
    set_widths(ws2, [14, 12, 22, 9, 9] + [11] * len(dates) + [10])
    ws2.freeze_panes = "F2"

    ws3 = wb.create_sheet("市场快照")
    ws3.append(["日期", "柯桥指数", "指数环比", "坯布库存(天)", "开机率(%)", "采样商户"])
    for date, mk in sorted(snapshots, key=lambda x: x[0]):
        ws3.append([date, mk.get("index"), mk.get("index_change"), mk.get("inventory_days"),
                    mk.get("operating_rate"), mk.get("sampled_shops")])
    for row in ws3.iter_rows(min_row=2, max_row=ws3.max_row, max_col=6):
        for cell in row:
            cell.border, cell.font = BORDER, BODY_FONT
            cell.alignment = CENTER
            if cell.column in (2, 4, 5, 6):
                cell.number_format = "0.00"
            if cell.column == 3:
                cell.number_format = "0.00\"%\""
        if (row[0].row % 2) == 1:
            for cell in row:
                cell.fill = ZEBRA_FILL
    style_header(ws3, 6)
    set_widths(ws3, [12, 10, 10, 12, 10, 10])

    out = Path(base, "archive", f"物料价格档案_{dates[-1].replace('-', '')}.xlsx")
    wb.save(out)
    return out


if __name__ == "__main__":
    import sys
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
    p = export(base)
    print(f"OK -> {p}" if p else "无归档数据，跳过导出")
