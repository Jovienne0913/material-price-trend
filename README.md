# 物料价格趋势库

锦泓集团供应链中心 · 物料价格趋势库，双子页面：

- **价格趋势库** (`index.html`)：走势点评、异动预警、历史走势、报价明细、往期归档
- **行业分析与建议** (`insight.html`)：数据采集、趋势诊断、节点预警、综合洞察、风险地图、价格体检、外部源地图

纯 CSS 零 JavaScript，兼容飞书浏览器。

## 在线地址

GitHub Pages: `https://Jovienne0913.github.io/material-price-trend/`

| 页面 | 地址 |
|---|---|
| 价格趋势库 | https://Jovienne0913.github.io/material-price-trend/ |
| 行业分析 | https://Jovienne0913.github.io/material-price-trend/insight.html |

## 本地刷新

```bash
python build_price_html.py material_prices_YYYYMMDD.json
```

自动产出：
- `index.html` / `insight.html` —— 双子页面
- `archive/物料价格档案_YYYYMMDD.xlsx` —— Excel 价格档案
- `archive/archive_index.json` —— 各期价格索引

## 数据更新

每次拿到新一期 JSON 后：
1. 替换 `material_prices_YYYYMMDD.json`
2. 运行 `python build_price_html.py material_prices_YYYYMMDD.json`
3. `git add . && git commit -m "update: YYYY-MM-DD 期数据"`
4. `git push`

GitHub Pages 自动更新，通常 1-2 分钟生效。

## 规格约定

- 毛类主力：羊毛（澳毛/国毛 21.5μm）、羊绒（16Nm/2、18Nm/2）
- 羽绒主力：85绒 / 90绒 / 95绒（绒子含量，GB/T 14272-2021）
- 铜：沪铜主力、黄铜带 H62、紫铜线 T2（辅料用铜基准）

---

供应链中心 · 战略BP
