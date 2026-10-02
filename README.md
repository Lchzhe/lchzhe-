# 中国宏观与 A 股信息雷达

GitHub Pages 静态站点入口：`index.html`。页面每 60 秒自动读取 `data/news.json` 和 `data/market.json`，无需手动刷新；GitHub Actions 每 5 分钟抓取公开网页、RSS/Atom 和行情接口，并为每条消息保留原文链接。

## 本地预览

直接打开 `index.html`，或使用任意静态文件服务器。

## GitHub Pages

将仓库发布目录设置为根目录 `/(root)`，并启用 HTTPS。

## 每日研报

`reports/YYYY-MM-DD.md` 和 `reports/latest.md` 由独立的 GitHub Actions 在北京时间 23:59 生成，包含当日重要信息、市场快照、专业分析、次日 A 股观察、长期投资研究框架和可追溯原文链接。

`scripts/sync-daily-report.ps1` 会把当天 23:59 生成的报告同步到 `D:/C/桌面/雷传喆的资料/每日金融信息研报`；可在 Windows 任务计划程序中设置每天 23:59 运行。
