# DESIGN.md · 物料价格趋势库设计语言契约

> **一句话语言**：深蓝权威 × 白底浅灰卡面 × 等宽数字仪表感的企业数据页——品牌蓝五阶承载身份，ink灰阶承载正文，红涨/绿跌/琥珀观察三档语义色只落在数据与状态上；一切交互零 JavaScript（`<details>` 折叠、radio 纯 CSS 筛选、hover 展开侧边栏），动效预算只有 0.12–0.22s 的 transition，没有 keyframes 动画。页面必须兼容企微内置浏览器。

本仓库无前端框架。全部设计语言由 **`build_price_html.py`** 单文件承载（数据驱动生成 `index.html`）：Python 生成 HTML 结构，第 861 行起的 `CSS` 常量是唯一 token 层与组件层。改设计 = 改这个文件的 CSS，再运行 `python build_price_html.py <数据.json>` 重新生成。

## 1. 硬约束（违反即返工）

| 约束 | 原因 |
|---|---|
| 零 JavaScript | 企微浏览器分享场景，`<script>` 标签禁止出现 |
| 纯 CSS + 静态 SVG 交互 | 折叠用 `<details>/<summary>`，筛选用隐藏 radio + 兄弟选择器（`build_price_html.py:839-844`） |
| 配色四色系：深蓝/浅蓝/白/灰 | 集团高层汇报规范；语义色（红/绿/琥珀）仅用于数据涨跌与风险状态 |
| 紧凑密度 | 卡片间距 12px、模块内边距 14-18px，不留大留白 |
| Emoji 预算 | 仅限模块标题图标、页面标题、核心指标卡、风险提示；正文表格数据行禁用 |
| 数据可溯源 | 引用外部数据处带 `<a>` 原文链接 |

## 2. Design Tokens（`build_price_html.py:863-868`）

### 品牌蓝（身份与结构）
```css
--brand-900:#0B2E59  /* 页头渐变起点、卡片深蓝头、标题数字 */
--brand-700:#14489E  /* 页头渐变终点、模块标题、pill 标签底 */
--brand-600:#2563EB  /* 链接、选中态、左色条默认 */
--brand-500:#3B82F6  /* hover 边框、强调 */
--brand-100:#EFF4FF  /* 浅蓝底、行动条底色 */
```

### 墨色与中性（正文与结构线）
```css
--ink-900:#0F172A  /* 标题、重点数字、一级正文 */
--ink-800:#1E293B  /* 强强调 */
--ink-700:#334155  /* 正文主色、表格内容 */
--ink-600:#475569  /* 次级正文、说明文字、产地标签 */
--ink-500:#64748B  /* 辅助说明、注释、来源信息 */
--ink-400:#94A3B8  /* 边框辅助、最淡文字 */
--line:#E6EDF6     /* 全部边框 */
--bg:#F4F7FC       /* 页面底色 */
--surface:#FBFCFE  /* 卡片面 */
```

**灰阶使用规则**：正文 ink-700 起，辅助信息才用 ink-600；ink-500 仅限来源标注、次要元数据；ink-400 只用于边框和分割线，不出现在正文。

### 语义色三档（只用于涨跌与风险）
| 档 | 主色 | 深色(文字) | 浅色(底) | 边框 | 用途 |
|---|---|---|---|---|---|
| danger 红 | `#DC2626` | `#B91C1C`/`#991B1B` | `#FEE2E2`/`#FEF2F2` | `#FCA5A5` | 涨价(`--up`)、预警、立即行动 |
| warn 琥珀 | `#F59E0B`/`#D97706` | `#B45309`/`#92400E` | `#FEF3C7` | `#FDE68A` | 跟踪观察、关注级 |
| safe 绿 | `#059669` | `#047857` | `#D1FAE5` | `#A7F3D0` | 跌价(`--down`)、低风险 |

> 注意：**红涨绿跌**（中国财务惯例）。`--up:#DC2626;--down:#059669`。

### 形状 / 阴影 / 动效 / 排版
```css
--r-lg:16px   /* 大卡片（模块容器） */
--r-md:12px   /* 中卡片、内嵌面板 */
--r-pill:999px /* 标签、状态徽章、筛选按钮 */
--sh-sm:0 1px 3px rgba(15,23,42,.06)   /* 卡片静置 */
--sh-md:0 10px 28px rgba(15,23,42,.10) /* 悬浮层（侧边栏展开） */
--ease:cubic-bezier(.4,0,.2,1)
```

**字号体系**（6 档，全部 token 化，无硬编码）：
```css
--fs-xs:11px     /* 徽章、标签、来源标注、表内小字 */
--fs-sm:12.5px   /* 表格正文、卡片正文、辅助说明 */
--fs-base:15px   /* 页面基准字号、小节标题、卡片标题 */
--fs-md:17px     /* 模块内大标题 */
--fs-lg:20px     /* 核心指标数字 */
--fs-xl:26px     /* 页面级大数字 */
```

**行高三档**：
```css
--lh-tight:1.35    /* 紧凑标签、数字行 */
--lh-normal:1.55   /* 表格、列表 */
--lh-relaxed:1.7   /* 正文段落、长文本 */
```

## 3. Typography

- **正文**：系统中文栈 `-apple-system,"PingFang SC","Microsoft YaHei",sans-serif`（`build_price_html.py:1140`），基准 `--fs-base` (15px) / `--lh-relaxed` (1.7) 行高。不引入 webfont（飞书 + 离线约束）。
- **数字**：所有数值（分数、百分比、价格、指数）用 `ui-monospace,Menlo,Consolas,monospace` + `font-weight:700~800`，全局 `font-variant-numeric:tabular-nums` 保证列对齐。数字是本页面的第一公民。
- **层级尺寸**（严格使用 token，禁止硬编码 px/rem）：
  - `--fs-xl` (26px)：页面级核心大数字
  - `--fs-lg` (20px)：模块内指标数字
  - `--fs-base` (15px)：小节标题 / 卡片标题 / 基准正文
  - `--fs-sm` (12.5px)：表格正文 / 卡片正文 / 走势点评
  - `--fs-xs` (11px)：徽章 / 标签 / 来源标注 / 表内小字
- **行高三档**：`--lh-tight` (1.35) 紧凑标签 → `--lh-normal` (1.55) 表格列表 → `--lh-relaxed` (1.7) 正文段落
- **色阶使用规则**：
  - 标题 / 重点：`--ink-900`
  - 正文 / 表格内容：`--ink-700`
  - 次级说明 / 产地标签：`--ink-600`
  - 来源标注 / 辅助元数据：`--ink-500`
  - 边框 / 分割线：`--ink-400`（不用于正文）

## 4. 组件语言（六大件）

| 组件 | 类名 | 规格定义 | 出处 |
|---|---|---|---|
| 深蓝头模块卡 | `.rpt-section` + `.rpt-header` | 白底卡 + `linear-gradient(135deg,brand-900,brand-700)` 头条 12px/18px 内边距，白字 14px/700 | :908-910 |
| 浅灰面卡片 | `.trend-card`/`.rpt-take-card` 等 | `#FBFCFE` 底 + `--line` 边框 + `--r-md` 圆角 + `--sh-sm`，hover 边框转 `--brand-500` | :979 起 |
| 左色条状态卡 | `.rpt-take-card.lv-*` | `border-left:4px` 承载语义色（红=行动/琥珀=观察/蓝=常规） | :981-984 |
| Pill 标签 | `.rpt-take-tag`/`.rpt-badge`/`.kb-status` | `--r-pill`，白字彩底或浅底彩字，11px/700 | :986-992 |
| 折叠模块 | `<details>` + `.rpt-chev` | 原生折叠，`▾` 展开旋转 180°，核心模块 `open` 默认展开 | :918-924 |
| 等宽数字块 | `.rpt-score-val`/`.rs-num`/`.tk-num` | 22-28px/800 等宽，语义色仅落在数字上 | :940 等 |

**侧边栏**（`:893-914`）：52px 收起 → hover 214px 展开（负边距悬浮不挤压内容），transition .22s；图标 14px，展开文字 12.5px/600。

## 5. Motion 预算

- 只有 transition：`.12s`（微反馈）/ `.15s`（边框色彩）/ `.18s`（折叠箭头）/ `.22s`（侧边栏宽度）。
- **零 keyframes、零入场动画、零 parallax**。这是数据页，不是营销页。
- hover 反馈三板斧：边框变品牌蓝、阴影升一档、文字加深。不位移、不缩放（侧边栏箭头旋转除外）。

## 6. 质感精修记录（2026-09-25 美观度优化）

已偿还的债务：
1. 语义色三档全部 token 化——`:root` 新增 `--dg-*`（danger）/`--wn-*`（warn）/`--sf-*`（safe）三系变量，组件 CSS 零硬编码语义色
2. 卡面/浅蓝边/浅灰进 token：`--surface:#FBFCFE`、`--brand-200:#D6E4FB`、`--ink-100:#F1F5F9`、`--brand-650:#1D4ED8`
3. 表格统一：斑马纹（偶数行 `#F7FAFE`）+ 行 hover 品牌蓝 + 分组行收编 `--brand-100` + 表头内高光线

新增质感层：
- `body` 全局 `font-variant-numeric:tabular-nums`（数字列对齐）+ 顶部 340px 淡蓝渐变光晕
- `::selection` 品牌蓝、`::-webkit-scrollbar` 9px 圆角窄条
- 页头 `::after` 径向光斑（rgba 蓝 22%）+ 徽章 backdrop-blur
- `.rpt-header` 底部 1px 白色内高光线（inset box-shadow）

剩余 Open questions：
- SVG 图表内配色仍是脚本内联属性，未走 CSS 变量（SVG attribute 无法引用 var 的场景）
- 移动端 375px 下侧边栏交互（hover 不可用）依赖哪套降级，未明确验证

---

## 每页检查清单（agent 自查）

- [ ] `index.html` 中 `grep '<script'` 为 0 命中
- [ ] 所有交互仅用 `<details>`、radio+label、`:hover` 三种纯 CSS 机制
- [ ] 涨=红 `--up`、跌=绿 `--down`，无反转
- [ ] 语义色只出现在数字、标签、左色条；大面积底色仍是白/浅灰/浅蓝
- [ ] 新卡片：白或 `#FBFCFE` 底 + `--line` 边框 + 12px 圆角 + `--sh-sm`
- [ ] 所有数值使用等宽字体栈且 ≥700 字重
- [ ] 动效只有 transition 且 ≤.22s，无 keyframes
- [ ] 页面在 375px 宽（企微 iPhone）无横向滚动，网格降为单列
- [ ] 外部数据引用处有可点击原文链接
