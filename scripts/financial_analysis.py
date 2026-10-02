"""Auditable descriptive financial research. No fitted prediction model is implied.

All returns are decimals. Histories contain distinct completed sessions of price
indices (dividends excluded). Risk estimates describe those indices, not the user's
holdings, and cannot be interpreted as guaranteed future loss limits.
"""
import math
import re
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from statistics import mean, stdev

BJ = timezone(timedelta(hours=8))
VERSION = "3.0-research"
REFERENCES = [
    {"id": "ff", "title": "Fama & French (2015) · A five-factor asset pricing model", "url": "https://doi.org/10.1016/j.jfineco.2014.10.010"},
    {"id": "carhart", "title": "Carhart (1997) · On Persistence in Mutual Fund Performance", "url": "https://doi.org/10.1111/j.1540-6261.1997.tb03808.x"},
    {"id": "dcf", "title": "Damodaran · Discounted cash flow valuation inputs", "url": "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/lectures/dcfinput.html"},
    {"id": "lw", "title": "Ledoit & Wolf (2004) · Covariance shrinkage", "url": "https://www.ledoit.net/Well-conditioned2004.pdf"},
    {"id": "es", "title": "BIS · Basel Framework, MAR33", "url": "https://www.bis.org/committees/bcbs/basel-framework/standard/mar"},
    {"id": "macro", "title": "Federal Reserve (2023) · Financial conditions and growth", "url": "https://www.federalreserve.gov/econres/notes/feds-notes/a-new-index-to-measure-us-financial-conditions-20230630.html"},
    {"id": "ml", "title": "Kelly & Xiu (2023) · Financial Machine Learning", "url": "https://www.nber.org/papers/w31502"},
]
CALENDAR_SOURCE = "https://www.sse.com.cn/disclosure/announcement/general/c/c_20251222_10802507.shtml"
HOLIDAYS_2026 = (("01-01", "01-03"), ("02-15", "02-23"), ("04-04", "04-06"), ("05-01", "05-05"), ("06-19", "06-21"), ("09-25", "09-27"), ("10-01", "10-07"))


def num(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def fmt_pct(value):
    return "待补充" if value is None else f"{value * 100:+.2f}%"


def is_trading_day(day):
    if day.year != 2026:
        return None  # Never silently reuse an obsolete year's exchange calendar.
    return day.weekday() < 5 and not any(a <= day.strftime("%m-%d") <= b for a, b in HOLIDAYS_2026)


def next_session(day):
    for offset in range(1, 15):
        candidate = day + timedelta(days=offset)
        known = is_trading_day(candidate)
        if known is None:
            return None
        if known:
            return candidate.isoformat()
    return None


def completed_rows(rows, as_of):
    """Reject duplicate dates, bad prices, weekends, and an unfinished current bar."""
    valid = {}
    for row in rows or []:
        try:
            day = date.fromisoformat(row.get("date", ""))
        except (TypeError, ValueError):
            continue
        close = num(row.get("close"))
        if close is None or close <= 0 or day > as_of.date() or day.weekday() >= 5:
            continue
        if is_trading_day(day) is False:
            continue
        if day == as_of.date() and as_of.hour < 15:
            continue
        valid[day.isoformat()] = {**row, "close": close}
    return [valid[k] for k in sorted(valid)]


def returns_map(rows):
    return {rows[i]["date"]: rows[i]["close"] / rows[i - 1]["close"] - 1 for i in range(1, len(rows))}


def expected_shortfall(returns, level=0.95):
    """Empirical ES: exact fractional mean of the worst (1-level) share of ALL losses."""
    if not returns or not 0 < level < 1:
        raise ValueError("ES requires observations and 0 < level < 1")
    losses = sorted((-value for value in returns), reverse=True)
    mass = len(losses) * (1 - level)
    full = min(len(losses), int(math.floor(mass + 1e-10)))
    remainder = max(0.0, mass - full)
    tail_sum = sum(losses[:full])
    if remainder > 1e-10 and full < len(losses):
        tail_sum += remainder * losses[full]
    return tail_sum / mass


def max_drawdown(closes):
    if not closes:
        return None
    peak, worst = closes[0], 0.0
    for close in closes:
        peak = max(peak, close)
        worst = max(worst, 1 - close / peak)
    return worst


def history_metrics(rows):
    closes = [row["close"] for row in rows]
    daily = list(returns_map(rows).values())
    n = len(daily)
    momentum = closes[-22] / closes[-253] - 1 if len(closes) >= 253 else None
    trend = closes[-1] / mean(closes[-60:]) - 1 if len(closes) >= 60 else None
    vol = stdev(daily[-63:]) * math.sqrt(252) if n >= 63 else None
    tail = daily[-250:]
    return {
        "observations": n, "start": rows[0]["date"] if rows else None,
        "end": rows[-1]["date"] if rows else None,
        "momentum_12_1": momentum, "distance_ma60": trend,
        "realized_vol_annualized": vol,
        "expected_shortfall_95": expected_shortfall(tail) if n >= 250 else None,
        "max_drawdown": max_drawdown(closes[-251:]) if n >= 250 else None,
        "risk_observations": min(n, 250), "available": n >= 250,
        "note": "波动用最近63个收盘收益，ES与回撤用最近250个收盘收益；均为价格指数历史估计，未含股息、交易成本或持仓。",
    }


def beta_and_correlation(asset_returns, benchmark_returns):
    dates = sorted(set(asset_returns) & set(benchmark_returns))[-252:]
    if len(dates) < 126:
        return {"observations": len(dates), "beta": None, "correlation": None}
    x, y = [benchmark_returns[d] for d in dates], [asset_returns[d] for d in dates]
    mx, my = mean(x), mean(y)
    xx = sum((v - mx)**2 for v in x)
    yy = sum((v - my)**2 for v in y)
    xy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    return {"observations": len(dates), "beta": xy / xx if xx else None,
            "correlation": xy / math.sqrt(xx * yy) if xx and yy else None}


def news_day(item):
    """Only known publisher dates count as daily news; crawl time never does."""
    raw = item.get("published_at") or ""
    if item.get("date_quality") not in ("publisher", "url_date"):
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = parsedate_to_datetime(raw)
        except (ValueError, TypeError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=BJ)
    return dt.astimezone(BJ).date().isoformat()


EVENT_RULES = [
    ("货币与信用", ("降准", "降息", "货币政策", "贷款贴息", "利率"), "融资成本 / 信用供给 → 企业现金流与折现率", "核对额度、适用对象、期限和银行实际执行；支持力度未量化前不判定板块必然上涨。"),
    ("财政与需求", ("财政", "专项债", "消费", "基建", "补贴"), "财政支出 / 需求 → 收入、利润率和资金周转", "核对预算规模、落地时间及收入确认；政策方向与盈利兑现分开判断。"),
    ("公司与治理", ("风险警示", "诉讼", "减持", "业绩", "回购", "分红"), "现金流、股本或治理变化 → 估值与风险溢价", "核对正式公告与财务影响；风险警示、诉讼和减持先列入风险清单。"),
]


def event_channels(news, report_date):
    events = []
    seen = set()
    for item in news:
        if not item.get("url") or item.get("url") in seen or item.get("item_type") == "source_entry":
            continue
        if news_day(item) != report_date:
            continue
        for name, terms, pathway, check in EVENT_RULES:
            if any(term in item.get("title", "") for term in terms):
                events.append({"title": item["title"], "source": item.get("source"), "url": item["url"],
                               "channel": name, "pathway": pathway, "check": check,
                               "evidence": "标题触发的研究假设，尚未完成全文核验"})
                seen.add(item["url"])
                break
        if len(events) >= 6:
            break
    return events


def build_analysis(market, history, news, as_of):
    series = (history or {}).get("series", {}) if isinstance(history, dict) else {}
    rows_by_code = {code: completed_rows(data.get("rows", []), as_of) for code, data in series.items()}
    benchmark = rows_by_code.get("sh000300", [])
    metrics = history_metrics(benchmark)
    benchmark_returns = returns_map(benchmark)
    # Use mainland benchmarks only. Hong Kong has a separate session/calendar.
    indices = [i for i in market.get("indices", []) if i.get("code", "").startswith(("sh", "sz", "bj"))]
    values = [num(i.get("pct")) for i in indices]
    values = [v for v in values if v is not None]
    avg, dispersion = (mean(values) if values else None), (stdev(values) if len(values) >= 2 else None)
    breadth = market.get("breadth") or {}
    ratio = num(breadth.get("ratio")) if breadth.get("available") else None
    trend = metrics["distance_ma60"]
    is_open_day = is_trading_day(as_of.date())
    quote_day = next((re.search(r"(20\d{2})[-/]?(\d{2})[-/]?(\d{2})", str(i.get("observed", ""))) for i in indices), None)
    quote_date = "-".join(quote_day.groups()) if quote_day else None
    stale = (bool(market.get("data_stale")) and is_open_day is True) or (is_open_day is True and quote_date is not None and quote_date < as_of.date().isoformat() and as_of.hour >= 10)
    if not values or stale:
        state, code = "证据不足，暂缓短线判断", "insufficient"
    elif trend is not None and trend > 0 and ratio is not None and ratio >= 55:
        state, code = "趋势与宽度同向改善", "improving"
    elif trend is not None and trend < 0 and ratio is not None and ratio < 45:
        state, code = "趋势与宽度同向走弱", "weakening"
    else:
        state, code = "信号分化，保持观察", "mixed"
    covered = sum((bool(values), ratio is not None, trend is not None, metrics["available"]))
    quality = "较完整" if covered == 4 and not stale else "部分可用" if covered else "数据不足"
    risk = {**metrics, "benchmark": "沪深300", "price_basis": "价格指数，非总收益指数"}
    momentum_label = fmt_pct(metrics["momentum_12_1"])
    factors = [
        {"name": "市场敏感度 β", "model": "线性市场回归", "status": "computed" if benchmark_returns else "missing", "score": None,
         "signal": "相对于沪深300的日收益敏感度", "note": "下表提供对齐交易日回归；未扣无风险利率，未输出 CAPM 预期收益或 alpha。"},
        {"name": "12—1 月动量", "model": "动量研究中的价格描述指标", "status": "computed" if metrics["momentum_12_1"] is not None else "missing", "score": None,
         "signal": momentum_label, "note": "沪深300第t-21日收盘 / 第t-252日收盘 - 1；排除最近21个交易日，不是 Carhart 横截面因子收益。"},
        {"name": "估值与现金流", "model": "DCF / 相对估值", "status": "missing", "score": None,
         "signal": "公司财务与预测数据待接入", "note": "需要 FCFF/FCFE、净债务、折现率和增长情景；暂不生成目标价。"},
        {"name": "盈利与投资", "model": "Fama-French 五因子", "status": "missing", "score": None,
         "signal": "A股本地因子组合待接入", "note": "需要时点一致的账面价值、盈利、资产增长、规模、无风险利率与因子收益；未拟合五因子回归。"},
        {"name": "滚动风险", "model": "历史波动 / ES / 回撤", "status": "computed" if metrics["available"] else "missing", "score": None,
         "signal": f"63日年化波动 {fmt_pct(metrics['realized_vol_annualized'])}", "note": "ES 使用全体250日收益的最差5%尾部，包括所有损益；一日95%研究口径，不等同银行监管ES。"},
    ]
    asset_metrics = []
    for item in indices:
        rows = rows_by_code.get(item.get("code"), [])
        m = history_metrics(rows)
        relation = beta_and_correlation(returns_map(rows), benchmark_returns)
        asset_metrics.append({"name": item["name"], "code": item["code"], **m, **relation})
    signals = [
        {"name": "A股指数截面", "status": "available" if values else "missing", "value": f"{len(values)}个指数均值 {avg:+.2f}% · 分化 {dispersion:.2f}个百分点" if avg is not None and dispersion is not None else "待补充", "interpretation": "描述最近行情；指数相互重叠，均值不代表可投资组合。", "caveat": "港股单列，不计入A股截面。"},
        {"name": "市场宽度", "status": "available" if ratio is not None else "missing", "value": f"上涨占比 {ratio:.1f}%" if ratio is not None else "待补充", "interpretation": "以接口覆盖范围为准；55%/45%为研究规则阈值，尚未完成收益检验。", "caveat": breadth.get("label", "市场成分估计")},
        {"name": "中期趋势", "status": "available" if trend is not None else "missing", "value": f"沪深300距60日均线 {fmt_pct(trend)}", "interpretation": "根据已完成交易日收盘计算，与宽度共同作描述性状态识别。", "caveat": "未训练HMM，也未给出上涨概率。"},
        {"name": "样本与时间", "status": "available" if benchmark else "missing", "value": f"历史截至 {metrics['end'] or '待补充'} · {metrics['observations']}个日收益", "interpretation": "收盘历史剔除未收盘当日；重复抓取和休市日不新增观测。", "caveat": "抓取时间与交易日期分开记录。"},
    ]
    scenarios = [
        {"name": "基准情景", "trigger": "趋势、宽度或消息证据未形成一致方向", "action": "观察成交与政策执行，复核现有风险暴露；长期按现金流、估值和分散程度研究。", "priority": "base"},
        {"name": "改善情景", "trigger": "趋势转强且上涨占比≥55%，后续成交与盈利信息支持", "action": "将低成本宽基和盈利质量稳定的方向列入研究，分批评估；未核验信息不触发自动买入。", "priority": "upside"},
        {"name": "压力情景", "trigger": "趋势转弱且上涨占比<45%，或公司现金流/治理出现恶化", "action": "复核集中度、杠杆、流动性和回撤承受能力；减少超过自身预算的风险暴露。", "priority": "downside"},
    ]
    theory_models = [
        {"name": "DCF与资本成本", "status": "待数据", "description": "现金流与折现率匹配、终值敏感性、净债务和每股价值；接入财报后再估值。", "reference": "dcf"},
        {"name": "多因子资产定价", "status": "待数据", "description": "FF5与动量用于归因；本地A股因子序列与发表时点一致后才估计暴露和残差。", "reference": "ff"},
        {"name": "风险与组合", "status": "部分启用", "description": "已计算历史风险和β/相关性；组合优化需持仓、资产池、成本和风险预算，尚未运行。", "reference": "lw"},
        {"name": "宏观金融传导", "status": "研究框架", "description": "需求、信用、通胀与利率经现金流/折现率传导；未取得发布值、预期值和历史样本时不输出惊喜指数。", "reference": "macro"},
        {"name": "金融机器学习", "status": "研究储备", "description": "非线性交互模型须经时序划分、滚动样本外评估、成本扣减和数据泄漏审查；尚未训练，不输出AI胜率。", "reference": "ml"},
    ]
    return {
        "framework_version": VERSION, "generated_at": as_of.isoformat(timespec="minutes"),
        "regime": {"code": code, "label": state, "score": None, "confidence": None, "confidence_label": "未校准概率", "quality_label": quality, "covered": covered, "total": 4},
        "session": {"is_trading_day": is_open_day, "next_session": next_session(as_of.date()), "quote_date": quote_date, "calendar_url": CALENDAR_SOURCE, "calendar_year": 2026},
        "signals": signals, "factor_lens": factors, "risk_metrics": risk,
        "asset_metrics": asset_metrics, "scenarios": scenarios,
        "events": event_channels(news, as_of.date().isoformat()),
        "model_catalog": theory_models, "references": REFERENCES,
        "data_quality": {"label": quality, "stale": stale, "fundamentals": False, "factor_returns": False,
                         "news_verified_today": sum(news_day(x) == as_of.date().isoformat() for x in news)},
        "methodology": ["60日趋势与宽度是透明研究规则，阈值未回测，不代表预测胜率。", "价格指数日收益用于β、波动、ES和回撤；未含股息、成本或个人持仓。", "基本面与本地因子缺失时停用DCF目标价和五因子回归；机器学习模型尚未训练。"],
    }

