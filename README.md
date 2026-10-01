# 中国宏观与 A 股信息雷达

GitHub Pages 静态站点入口：`index.html`。页面每 60 秒自动读取 `data/news.json`，不需要手动刷新；GitHub Actions 每 5 分钟抓取公开网页和 RSS/Atom feed，并为每条消息保留原文链接。

## 本地预览

直接打开 `index.html`，或使用任意静态文件服务器。

## GitHub Pages

将仓库发布目录设置为根目录 `/(root)`，并启用 HTTPS。自定义域名需要在仓库 Pages 设置及 DNS 中完成绑定。

## 每日研报

`reports/YYYY-MM-DD.md` 会由 GitHub Actions 在北京时间 20:00 生成研究底稿；`tools/daily-finance-report.ps1` 可在有权限的 Windows 账户下把底稿复制到本地资料文件夹。

