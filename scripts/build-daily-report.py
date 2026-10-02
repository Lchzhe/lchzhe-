"""Build a traceable daily finance report from the latest public snapshots."""
import argparse
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

BEIJING = timezone(timedelta(hours=8))


def now_bj():
    return datetime.now(timezone.utc).astimezone(BEIJING)


def load_json(path, fallback):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def pct(value):
    value = number(value)
    return "—" if value is None else f"{value:+.2f}%"


def price(value):
    value = number(value)
    return "—" if value is None else f"{value:,.2f}"


def title_key(title):
    return re.sub(r"\s+", "", title or "").lower()


def safe_md(text):
    return str(text or "").replace("[", "\\[").replace("]", "\\]").replace("|", "\\|").strip()


def date_in_item(item):
    value = str(item.get("published_at") or "")
    match = re.search(r"(20\d{2})[-/]?(\d{2})[-/]?(\d{2})", value)
    return "-".join(match.groups()) if match else ""


def source_link(item):
    url = item.get("url") or ""
    return f"[{safe_md(item.get('source') or '公开来源')}]({url})" if url else safe_md(item.get("source") or "公开来源")


def select_items(news, report_date, categories, limit=8):
    chosen, seen = [], set()
    filtered = [item for item in news if date_in_item(item) in (report_date, "")]
    if not filtered:
        filtered = news
    for item in filtered:
        if item.get("category") not in categories:
            continue
        key = title_key(item.get("title"))
        if not key or key in seen or any(word in key for word in ("englishversion", "查看")):
            continue
        seen.add(key)
        chosen.append(item)
        if len(chosen) >= limit:
            break
    return chosen


def market_analysis(market):
    indexes = market.get("indices") or []
    pcts = [number(item.get("pct")) for item in indexes if number(item.get("pct")) is not None]
    avg = number(market.get("average_index_pct"))
    up = sum(1 for value in pcts if value > 0)
    down = sum(1 for value in pcts if value < 0)
    breadth = market.get("breadth") or {}
    ratio = number(breadth.get("ratio"))
    strongest = sorted((item for item in indexes if number(item.get("pct")) is not None), key=lambda item: number(item.get("pct")), reverse=True)
    weakest = list(reversed(strongest))
    if avg is not None and ratio is not None and avg < 0 and ratio < 50:
        stance = "震荡偏谨慎"
        tone = "指数平均表现偏弱，市场宽度不足，短线更适合等待确认而不是追涨。"
    elif avg is not None and avg > 0 and ratio is not None and ratio >= 55:
        stance = "震荡偏暖"
        tone = "指数与市场宽度形成正向配合，但仍需要成交和领涨方向延续确认。"
    else:
        stance = "结构性震荡"
        tone = "指数、宽度或跨市场信号未完全同向，建议按条件触发和分散配置执行。"
    return {
        "avg": avg,
        "up": up,
        "down": down,
        "ratio": ratio,
        "stance": stance,
        "tone": tone,
        "strongest": strongest[:3],
        "weakest": weakest[:3],
    }


def build_report(report_date, data_dir="data", output_dir="reports"):
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    news_payload = load_json(data_dir / "news.json", {})
    market = load_json(data_dir / "market.json", {})
    statuses = load_json(data_dir / "source-status.json", {}).get("sources", news_payload.get("sources", []))
    news = news_payload.get("news", [])
    analysis = market_analysis(market)
    advanced = market.get("advanced_analysis") or {}
    generated = now_bj()
    lines = [
        "# 雷传喆 · 每日金融信息研报",
        "",
        f"**报告日期：{report_date}**　**生成时间（北京时间）：{generated:%Y-%m-%d %H:%M}**",
        "",
        "> 本报告把公开信息、行情快照和条件化研究判断分开呈现。建议先核对原文，再结合自己的风险承受能力决策；内容不构成个性化投资建议或收益承诺。",
        "",
        "## 一、当日重要信息概括汇总",
        "",
        "### 1. 中国宏观与政策",
        "",
    ]
    macro = select_items(news, report_date, {"中国宏观", "政策", "财政", "外贸", "外汇"}, 10)
    if macro:
        lines += [f"- **{safe_md(item.get('title'))}**（{source_link(item)}，{safe_md(item.get('published_at') or '时间待补充')}）：公开页面标题显示该项发布，建议打开原文核对政策对象、金额、期限和执行口径。" for item in macro]
    else:
        lines.append("- 当日未获取到可按日期确认的宏观政策条目，需打开来源入口复核。")
    lines += ["", "### 2. A 股披露与监管", ""]
    equities = select_items(news, report_date, {"A股披露", "监管"}, 10)
    if equities:
        lines += [f"- **{safe_md(item.get('title'))}**（{source_link(item)}，{safe_md(item.get('published_at') or '时间待补充')}）：先判断公告是否改变盈利预测、资产负债表、治理结构或交易约束，再决定是否进入研究清单。" for item in equities]
    else:
        lines.append("- 当日未获取到可按日期确认的 A 股披露条目。")
    lines += ["", "### 3. 全球宏观与跨市场", ""]
    global_news = select_items(news, report_date, {"全球宏观", "全球监管"}, 10)
    if global_news:
        lines += [f"- **{safe_md(item.get('title'))}**（{source_link(item)}，{safe_md(item.get('published_at') or '时间待补充')}）：作为外部变量观察，重点核对其对利率、美元、能源和风险偏好的传导路径。" for item in global_news]
    else:
        lines.append("- 当日未获取到可按日期确认的全球宏观条目。")
    lines += ["", "### 4. 当日市场快照", "", "| 资产 | 收盘/最新 | 涨跌幅 | 数据来源 |", "|---|---:|---:|---|"]
    for item in (market.get("indices") or []):
        lines.append(f"| [{safe_md(item.get('name'))}]({item.get('url','')}) | {price(item.get('price'))} | {pct(item.get('pct'))} | {safe_md(item.get('source') or market.get('provider'))} |")
    lines += ["", "**市场宽度：**"]
    breadth = market.get("breadth") or {}
    if breadth.get("available"):
        lines.append(f"上涨 {breadth.get('up', '—')} 家、下跌 {breadth.get('down', '—')} 家、平盘 {breadth.get('flat', '—')} 家，上涨占比 {number(breadth.get('ratio')):.1f}%；口径为{safe_md(breadth.get('label'))}。")
    else:
        lines.append("市场宽度接口当日不可用，不能据此推断涨跌家数；请打开行情中心核对。")
    for heading, key in (("海外指数", "global"), ("大宗商品", "commodities")):
        lines += ["", f"**{heading}：**"]
        assets = market.get(key) or []
        lines.append("；".join(f"{item.get('name')} {price(item.get('price'))}（{pct(item.get('pct'))}）" for item in assets) if assets else "当日未获取到该组报价。")
    regime = advanced.get("regime") or {}
    lines += [
        "", "## 二、现代金融理论分析框架", "",
        "本节采用证据优先的状态识别、因子归因和风险约束框架。它不对单只股票给出无数据支撑的确定性预测；缺少基本面或历史序列时明确标记为待补充。", "",
        "### 1. 市场状态与证据强度", "",
        f"- 当前状态：**{safe_md(regime.get('label') or '数据不足')}**；证据分数 {regime.get('score', '—')}/100；置信度 {safe_md(regime.get('confidence_label') or '待评估')}。",
    ]
    for signal in advanced.get("signals", []):
        lines.append(f"- {safe_md(signal.get('name'))}：{safe_md(signal.get('value'))}；{safe_md(signal.get('interpretation'))}（限制：{safe_md(signal.get('caveat'))}）")
    lines += ["", "### 2. 多因子透视", ""]
    for factor in advanced.get("factor_lens", []):
        score = factor.get("score")
        score_text = f"，代理分数 {score}" if score is not None else "，暂不可评分"
        lines.append(f"- **{safe_md(factor.get('name'))}**（{safe_md(factor.get('model'))}）：{safe_md(factor.get('signal'))}{score_text}。{safe_md(factor.get('note'))}")
    lines += ["", "### 3. 情景与行动条件", ""]
    for scenario in advanced.get("scenarios", []):
        lines.append(f"- **{safe_md(scenario.get('name'))}**：触发条件为{safe_md(scenario.get('trigger'))}；对应动作是{safe_md(scenario.get('action'))}。")
    risk = advanced.get("risk_metrics") or {}
    lines += ["", "### 4. 风险约束", ""]
    if risk.get("available"):
        lines.append(f"- 滚动 {risk.get('observations')} 个观测：年化实现波动 {risk.get('realized_vol_annualized')}，95% Expected Shortfall {risk.get('expected_shortfall_95')}，最大回撤 {risk.get('max_drawdown')}。")
    else:
        lines.append(f"- 历史风险统计暂不可用：{safe_md(risk.get('note') or '等待滚动数据积累。')}")
    session = advanced.get("session") or {}
    lines += ["", "### 5. 交易日与数据质量", ""]
    lines.append(f"- 交易日判断：{safe_md('是' if session.get('is_trading_day') is True else '否' if session.get('is_trading_day') is False else '未知')}；行情日期：{safe_md(session.get('quote_date') or '待补充')}；下一交易日：{safe_md(session.get('next_session') or '待补充')}。日历入口：[{session.get('calendar_url')}]({session.get('calendar_url')})。")
    quality = advanced.get("data_quality") or {}
    lines.append(f"- 数据质量：{safe_md(quality.get('label') or '待评估')}；当日已核验发布日期消息 {quality.get('news_verified_today', 0)} 条；基本面因子={safe_md('已接入' if quality.get('fundamentals') else '未接入')}，本地因子收益={safe_md('已接入' if quality.get('factor_returns') else '未接入')}。")
    events = advanced.get("events") or []
    lines += ["", "### 6. 事件传导链", ""]
    if events:
        for event in events:
            lines.append(f"- **{safe_md(event.get('channel'))}**：[{safe_md(event.get('title'))}]({event.get('url')})；传导路径：{safe_md(event.get('pathway'))}；核验要求：{safe_md(event.get('check'))}。")
    else:
        lines.append("- 当日没有足够的可核验发行方日期事件触发传导假设；抓取时间不会被当作新闻发布日期。")
    lines += ["", "### 7. 理论模型目录", ""]
    for model in advanced.get("model_catalog", []):
        lines.append(f"- **{safe_md(model.get('name'))}**（{safe_md(model.get('status'))}）：{safe_md(model.get('description'))}")
    lines += ["", "## 三、基于当日信息的专业分析", "", "### 1. 指数与市场宽度", ""]
    lines += [f"- 主要指数中 {analysis['up']} 个上涨、{analysis['down']} 个下跌，平均涨跌幅 {pct(analysis['avg'])}；这说明指数表现并非完全同向。",
              f"- 市场宽度上涨占比为 {analysis['ratio']:.1f}% 。该指标低于 50% 时，短线赚钱效应需要更多确认，单看指数上涨容易高估市场强度。" if analysis['ratio'] is not None else "- 市场宽度缺少可用数据，暂不把指数变化外推为全市场机会。"]
    if analysis["strongest"]:
        lines.append("- 相对强势：" + "、".join(f"{item.get('name')} {pct(item.get('pct'))}" for item in analysis["strongest"]) + "。")
    if analysis["weakest"]:
        lines.append("- 相对弱势：" + "、".join(f"{item.get('name')} {pct(item.get('pct'))}" for item in analysis["weakest"]) + "。")
    lines += ["", "### 2. 跨市场传导", "", "- 若海外股指走弱、能源价格上行而贵金属同步偏强，通常意味着增长预期、通胀扰动和避险需求同时存在；对高估值、高波动方向应提高估值与现金流要求。", "- 这只是变量之间的传导框架，不等于因果结论；下一交易日需用成交、北向/机构资金（如有可靠数据）和公司公告验证。", "", "### 3. 综合判断", "", f"**当前状态：{analysis['stance']}。** {analysis['tone']}", "", "## 四、下一交易日 A 股观察与建议", "", "### 基准情景：震荡中验证宽度", "", "- 开盘后先观察 30—60 分钟，不因单只股票或单条快讯追涨；重点看上涨占比能否稳定回到 50% 以上，以及沪深 300、上证指数是否与成交额同步改善。", "- 若宽度继续低于 50%、成长指数继续明显弱于大盘：降低高波动仓位，优先保留现金流稳定、估值有安全边际的方向，等待市场结构修复。", "- 若宽度升至 55% 以上、主要指数站回前收并伴随成交放大：可以分批研究宽基 ETF、盈利稳定行业和有真实订单支撑的公司，避免一次性满仓。", "- 若能源继续快速上行并压制风险偏好：把通胀、运输和制造成本作为财报核查项，谨慎追逐已经大幅上涨的主题。", "", "### 明日需要核对的事实", "", "1. 市场宽度是否改善，以及上涨是否由更多行业共同贡献。", "2. 主要指数成交额是否放大，领涨方向是否出现量价背离。", "3. 当日政策和公告是否有正式全文、执行细则或风险提示，而不是只依据标题和二手解读。", "", "## 五、长期投资建议（研究框架）", "", "- **核心仓位：** 以低成本、分散化的宽基指数和盈利质量较高的资产为主，采用分批投入和定期再平衡，减少对单一行业、单一公司和单一时点的依赖。", "- **卫星仓位：** 只配置自己能解释盈利来源、竞争壁垒、现金流和估值的行业或公司；主题仓位应设置上限，出现逻辑变化时按规则退出。", "- **风险控制：** 保留应急现金，不使用影响生活的资金和高杠杆；为单一持仓、行业暴露和最大回撤设定事先规则。", "- **验证周期：** 长期判断至少用多个季度的盈利、现金流、资本开支和政策执行数据验证，不因为一天的涨跌改写长期逻辑。", "", "## 六、信息来源与可追溯性", "", f"本次报告使用的数据快照：新闻 {safe_md(news_payload.get('updated_at'))}；行情 {safe_md(market.get('updated_at'))}；行情接口：{safe_md(market.get('provider'))}。", "", "| 来源 | 类别 | 状态 | 原始入口 |", "|---|---|---|---|"]
    for item in statuses:
        lines.append(f"| {safe_md(item.get('name'))} | {safe_md(item.get('category'))} | {safe_md(item.get('status'))} | [{item.get('url','')}]({item.get('url','')}) |")
    lines += ["", "## 七、理论依据与方法来源", "", "本报告使用公开、可追溯的研究框架；引用用于说明模型边界，不代表模型对未来收益的保证。", ""]
    lines.append("| 框架 | 原始资料 | 用途 |")
    lines.append("|---|---|---|")
    ref_map = {item.get("id"): item for item in advanced.get("references", [])}
    for model in advanced.get("model_catalog", []):
        ref = ref_map.get(model.get("reference"), {})
        if ref:
            lines.append(f"| {safe_md(model.get('name'))} | [{safe_md(ref.get('title'))}]({ref.get('url')}) | {safe_md(model.get('description'))} |")
    lines += ["", "## 附录：当日可追溯消息清单", "", "| 时间 | 类别 | 来源 | 标题 | 原文 |", "|---|---|---|---|---|"]
    for item in news:
        if date_in_item(item) not in (report_date, "") and any(date_in_item(x) == report_date for x in news):
            continue
        url = item.get("url") or ""
        link = f"[{safe_md(item.get('title'))}]({url})" if url else safe_md(item.get("title"))
        lines.append(f"| {safe_md(item.get('published_at') or '—')} | {safe_md(item.get('category'))} | {safe_md(item.get('source'))} | {link} | {url} |")
    lines += ["", "## 免责声明", "", "本报告用于个人学习和研究。公开数据可能存在延迟、缺失、修订或口径差异；市场分析为条件化推演，不能替代持牌机构的个性化投资顾问服务，也不保证任何收益。", ""]
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"{report_date}.md"
    destination.write_text("\n".join(lines), encoding="utf-8")
    (output_dir / "latest.md").write_text("\n".join(lines), encoding="utf-8")
    return destination


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="report date in YYYY-MM-DD; default is yesterday in Beijing")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--output-dir", default="reports")
    args = parser.parse_args()
    report_date = args.date or (now_bj().date() - timedelta(days=1)).isoformat()
    print(build_report(report_date, args.data_dir, args.output_dir))


if __name__ == "__main__":
    main()

