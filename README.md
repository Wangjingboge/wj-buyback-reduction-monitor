# 公司回购与大股东减仓监控（望京博格版）

> 统计最近五年（默认 60 个月）全 A 公司实际执行的股份回购金额与大股东二级市场减持金额，逐月对照沪深300，产出望京博格式单页 HTML 报告并导出 2160 宽高清长图。

`v1.1.0` `WorkBuddy Skill` `MIT`

## 功能说明

统计最近五年（默认 60 个月）全 A 公司实际执行的股份回购金额与大股东二级市场减持金额，逐月对照沪深300，产出望京博格式单页 HTML 报告并导出 2160 宽高清长图。内置十项数据准确性交叉校验。当用户提到「公司回购」「回购金额统计」「大股东减持」「重要股东减仓」「回购与减持对比」「产业资本增减持」时使用。

## 前置依赖

必须已装金融数据 MCP（Wind 系列），且支持「按月跨全市场聚合回购金额 / 重要股东减持金额」；沪深300 月线需要指数行情接口。安装与验证见 references/data-sourcing.md

## 安装

把整个仓库克隆或下载后，放到 WorkBuddy 的技能目录下：

```bash
git clone https://github.com/Wangjingboge/wj-buyback-reduction-monitor.git ~/.workbuddy/skills/wj-buyback-reduction-monitor
```

WorkBuddy 启动时会自动加载 `~/.workbuddy/skills/` 下的所有技能。

## 使用

触发方式为自然语言 —— 直接用中文描述需求即可，具体的触发词与执行流程见 [`SKILL.md`](SKILL.md)。

## 目录结构

- `SKILL.md`
  - `assets/page_template.html`
  - `data/buyback-reduction-history.json`
  - `data/pending.json`
  - `references/data-sourcing.md`
  - `references/rendering.md`
  - `scripts/build.py`
  - `scripts/check_env.py`
  - `scripts/config.py`
  - `scripts/export_long.js`
  - `scripts/fetch_plan.py`
  - `scripts/history.py`
  - `scripts/runtime.py`
  - `scripts/update.py`

## 作者

望京博格（[Wangjingboge](https://github.com/Wangjingboge)）

财经自媒体，前公募指数基金产品总监。写作风格与投研框架见 [wj-burger-write](https://github.com/Wangjingboge/wj-burger-write)。

## License

MIT © 2026 望京博格 (WJ Bogle)


> 本技能仅供研究与学习使用，不构成任何投资建议。所有数据须自行核实，据此操作风险自担。
