# AGENTS.md

## Quick Links

- [Design Language](DESIGN.md) — token 表、组件语言、零 JS 交互契约、每页检查清单
- [Frontend Design Skill](.agents/skills/frontend-design/SKILL.md) — 工艺准则与禁止清单

## 项目说明

物料价格趋势库：`build_price_html.py` 读取物料价格 JSON，生成零 JavaScript 的纯 CSS 静态页（飞书浏览器兼容），拆双子页面：

- `index.html` —— **价格趋势库**：走势点评、异动预警、历史走势、报价明细、往期归档
- `insight.html` —— **行业分析与建议**：数据采集、趋势诊断、节点预警、综合洞察、风险地图、价格体检、外部源地图、传导链监控、半月刷新SOP

顶栏有「📊 价格趋势 / 💡 行业分析」双子页切换 tab，零 JS 原生链接跳转。

```bash
# 刷新双页（拿到新一周 JSON 后，一条命令产出全部）
python build_price_html.py material_prices_YYYYMMDD.json
```

改设计只改 `build_price_html.py` 内的 `CSS` 常量与 HTML 模板，改完必须重新生成并自查 `DESIGN.md` 末尾清单。

## 往期价格归档（自动）

每次运行 `python build_price_html.py 新数据.json` 自动执行归档，无需手工维护：

- `archive/archive_index.json` —— 各期价格摘要索引（日期 + 柯桥指数 + 各细分品类「近1月」末点价），同期重跑覆盖更新
- `archive/material_prices_YYYYMMDD.json` —— 当期原始数据完整备份
- `index.html` 内「🗄️ 往期归档」模块 —— 跨期价格对比矩阵（行=细分品类按大类分组，列=期数最新在左，最多10期），涨跌色为相邻两期环比（红涨绿跌）
- `archive/物料价格档案_YYYYMMDD.xlsx` —— Excel 档案（`export_archive_xlsx.py` 生成，`build_price_html.py` 刷新时自动导出），三个 sheet：
  - **价格明细**（长表）：日期/大类/细分品类/品名规格档/规格说明/产地/单位/参考价/我司主力/来源，带筛选，可直接做透视表
  - **跨期对比**（宽表）：行=规格档，列=各期价格，末列「最新环比」为 Excel 公式（≥2 期自动生成），配合采购量可直接核算节约降本金额
  - **市场快照**：各期柯桥指数/环比/坯布库存/开机率/采样商户
- 同期重跑时 `archive/material_prices_YYYYMMDD.json` 备份会被最新版覆盖（数据修正后归档同步更新）

往期对比数据随 `index.html` 单文件分发（邮件附件自带历史），原始明细留在本机 `archive/` 目录。

## 规格档位约定（数据 JSON）

报价明细 item 支持 `"focus": true` 字段，渲染为「★ 我司主力」徽标。当前主力规格：

- **毛类（只有羊毛+羊绒主力）**：羊毛澳毛/国毛 21.5μm 前两档、羊绒 16Nm/2 + 18Nm/2；马海毛/牦牛绒/羊驼毛等小众品类不加主力标
- **羽绒（白鸭绒/灰鸭绒/白鹅绒/灰鹅绒）**：85绒 / 90绒 / 95绒（绒子含量 85/90/95%，GB/T 14272-2021 口径），50/60/70 绒已删除
- **铜（辅料大类）**：沪铜主力合约 + 黄铜带 H62 + 紫铜线 T2（拉链/四合扣等金属辅料原料基准）

后续新 JSON 刷新时必须保留这些规格档与 focus 标记；新增其他规格时视采购用量决定是否加 focus。

## 数据刷新通知 SOP（飞书邮件）

**渠道：飞书邮件（2026-09-25 起，公司已从企微切换飞书，不再走企微推送）。**

每次刷新数据重新生成 `index.html` 后，向以下 12 人发送通知邮件（正文含总判断/市场快照/异动预警/行动建议四段式 HTML，附件带 `index.html`）：

| 姓名 | 邮箱 |
|---|---|
| 陶衍敏 | ymtao@teenieweenie.com |
| 谢迎春 | xie_yingchun@vgrass.com |
| 张传宇 | zhang_chuanyu@vgrass.com |
| 汪思娇 | wang_sijiao@vgrass.com |
| 左群领 | qlzuo@teenieweenie.com |
| 何丽（TW童装生产代表部） | hel@teenieweenie.com |
| 袁海飞 | yuan_haifei@vgrass.com |
| 孙寒燕 | sun_hanyan@teenieweenie.com |
| 鲜伟 | xian_wei@teenieweenie.com |
| 张哲荣 | zhang_zherong@teenieweenie.com |
| 周佳慧（发件人本人） | zhou_jiahui@vgrass.com |
| 吴文菁 | wu_wenjing@vgrass.com |

发送命令（在项目目录下，正文写 `_mail_body.html`，重复 `--to` 12 次）：

```bash
lark-cli mail +send --as user --to 'ymtao@teenieweenie.com' --to 'xie_yingchun@vgrass.com' ... \
  --subject '【物料价格趋势库】YYYY-MM-DD期数据已刷新 · N项异动预警' \
  --body-file '_mail_body.html' --attach 'index.html' --format json
# 发送草稿（PowerShell 5 需反斜杠转义 JSON，且加 --yes 过高风险门禁）：
lark-cli mail user_mailbox.drafts send --as user --params '{\"user_mailbox_id\":\"me\",\"draft_id\":\"<draft_id>\"}' --yes
# 查投递状态（状态4=成功，3=退信）：
lark-cli mail user_mailbox.messages send_status --as user --params '{\"user_mailbox_id\":\"me\",\"message_id\":\"<id>\"}'
```

注意：「何丽」通讯录有 4 个同名，收件人固定为 TW童装生产代表部的何丽（hel@teenieweenie.com），勿误发零售门店同名人员。
