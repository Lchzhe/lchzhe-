"""Refresh public finance sources and build a linkable news feed."""
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from financial_analysis import build_analysis, completed_rows, is_trading_day

BEIJING = timezone(timedelta(hours=8))
USER_AGENT = "lchzhe-finance-radar/2.0 (+https://github.com/Lchzhe/lchzhe-)"
SOURCES = [
    {"id": "pbc", "name": "中国人民银行", "category": "中国宏观", "url": "https://www.pbc.gov.cn/"},
    {"id": "nbs-data", "name": "国家统计局数据", "category": "中国宏观", "url": "https://data.stats.gov.cn/"},
    {"id": "nbs-news", "name": "国家统计局", "category": "中国宏观", "url": "https://www.stats.gov.cn/"},
    {"id": "gov-policy", "name": "中国政府网政策", "category": "政策", "url": "https://www.gov.cn/zhengce/"},
    {"id": "ndrc", "name": "国家发展改革委", "category": "政策", "url": "https://www.ndrc.gov.cn/"},
    {"id": "mof", "name": "财政部", "category": "财政", "url": "https://www.mof.gov.cn/"},
    {"id": "customs", "name": "海关总署", "category": "外贸", "url": "http://www.customs.gov.cn/"},
    {"id": "safe", "name": "国家外汇管理局", "category": "外汇", "url": "https://www.safe.gov.cn/"},
    {"id": "csrc", "name": "中国证监会", "category": "监管", "url": "https://www.csrc.gov.cn/"},
    {"id": "cninfo", "name": "巨潮资讯", "category": "A股披露", "url": "https://www.cninfo.com.cn/"},
    {"id": "sse", "name": "上海证券交易所", "category": "A股披露", "url": "https://www.sse.com.cn/"},
    {"id": "szse", "name": "深圳证券交易所", "category": "A股披露", "url": "https://www.szse.cn/"},
    {"id": "bse", "name": "北京证券交易所", "category": "A股披露", "url": "https://www.bse.cn/"},
    {"id": "chinabond", "name": "中国债券信息网", "category": "债券利率", "url": "https://www.chinabond.com.cn/"},
    {"id": "shibor", "name": "Shibor", "category": "债券利率", "url": "https://www.shibor.org/"},
    {"id": "fred", "name": "FRED", "category": "全球宏观", "url": "https://fred.stlouisfed.org/", "feed": "https://fred.stlouisfed.org/feeds/releases.xml"},
    {"id": "fed", "name": "美联储", "category": "全球宏观", "url": "https://www.federalreserve.gov/", "feed": "https://www.federalreserve.gov/feeds/press_all.xml"},
    {"id": "bls", "name": "美国劳工统计局", "category": "全球宏观", "url": "https://www.bls.gov/", "feed": "https://www.bls.gov/feed/bls_latest.rss"},
    {"id": "bea", "name": "美国经济分析局", "category": "全球宏观", "url": "https://www.bea.gov/", "feed": "https://www.bea.gov/news/rss.xml"},
    {"id": "ecb", "name": "欧洲央行", "category": "全球宏观", "url": "https://www.ecb.europa.eu/", "feed": "https://www.ecb.europa.eu/rss/press.html"},
    {"id": "imf", "name": "国际货币基金组织", "category": "全球宏观", "url": "https://www.imf.org/", "feed": "https://www.imf.org/en/News/RSS"},
    {"id": "oecd", "name": "OECD", "category": "全球宏观", "url": "https://www.oecd.org/", "feed": "https://www.oecd.org/newsroom/rss.xml"},
    {"id": "worldbank", "name": "世界银行", "category": "全球宏观", "url": "https://www.worldbank.org/en/news"},
    {"id": "sec", "name": "美国 SEC", "category": "全球监管", "url": "https://www.sec.gov/", "feed": "https://www.sec.gov/news/pressreleases.rss"},
    {"id": "treasury", "name": "美国财政部", "category": "全球宏观", "url": "https://home.treasury.gov/news/press-releases"},
    {"id": "bis", "name": "国际清算银行", "category": "全球宏观", "url": "https://www.bis.org/press/index.htm"},
    {"id": "tradingeconomics", "name": "Trading Economics（辅助）", "category": "数据工具", "url": "https://tradingeconomics.com/"},
]

MARKET_INDEXES = [
    {"code": "sh000001", "name": "上证指数", "url": "https://quote.eastmoney.com/zs000001.html"},
    {"code": "sz399001", "name": "深证成指", "url": "https://quote.eastmoney.com/zs399001.html"},
    {"code": "sz399006", "name": "创业板指", "url": "https://quote.eastmoney.com/zs399006.html"},
    {"code": "sh000688", "name": "科创50", "url": "https://quote.eastmoney.com/zs000688.html"},
    {"code": "bj899050", "name": "北证50", "url": "https://quote.eastmoney.com/bj899050.html"},
    {"code": "sh000300", "name": "沪深300", "url": "https://quote.eastmoney.com/zs000300.html"},
    {"code": "sh000905", "name": "中证500", "url": "https://quote.eastmoney.com/zs000905.html"},
    {"code": "hkHSI", "name": "恒生指数", "url": "https://quote.eastmoney.com/gb/hkHSI.html"},
]

MARKET_GLOBAL = [
    {"code": "usDJI", "name": "道琼斯", "url": "https://quote.eastmoney.com/gb/.DJI.html"},
    {"code": "usIXIC", "name": "纳斯达克", "url": "https://quote.eastmoney.com/gb/.IXIC.html"},
    {"code": "usINX", "name": "标普500", "url": "https://quote.eastmoney.com/gb/.INX.html"},
]

MARKET_COMMODITIES = [
    {"code": "hf_XAU", "name": "伦敦金", "url": "https://quote.eastmoney.com/globalfuture/GC00.html"},
    {"code": "hf_CL", "name": "纽约原油", "url": "https://quote.eastmoney.com/globalfuture/CL00.html"},
    {"code": "hf_SI", "name": "伦敦银", "url": "https://quote.eastmoney.com/globalfuture/SI00.html"},
]


def now_bj():
    return datetime.now(timezone.utc).astimezone(BEIJING)


def fetch(url, limit=400_000):
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, text/html, */*"})
    with urlopen(request, timeout=15) as response:
        return response.status, response.headers.get_content_type(), response.read(limit)


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_market_group(items, query_url):
    """Read public Tencent quote text; return usable values or an empty list."""
    try:
        request = Request(query_url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.qq.com/"})
        with urlopen(request, timeout=15) as response:
            raw = response.read().decode("gb18030", "ignore")
    except Exception:
        return []
    result = []
    by_code = {item["code"]: item for item in items}
    for code, body in re.findall(r'v_([A-Za-z0-9_]+)="([^"]*)"', raw):
        meta = by_code.get(code)
        if not meta:
            continue
        if code.startswith("hf_"):
            fields = body.split(",")
            price, pct, high, low, prev = (number(fields[i]) if len(fields) > i else None for i in (0, 1, 4, 5, 7))
            chg = round(price - prev, 6) if price is not None and prev is not None else None
            observed = fields[6] if len(fields) > 6 else ""
        else:
            fields = body.split("~")
            price, prev, chg, pct, high, low = (number(fields[i]) if len(fields) > i else None for i in (3, 4, 31, 32, 33, 34))
            observed = fields[30] if len(fields) > 30 else ""
        if price is None:
            continue
        result.append({**meta, "price": price, "prev": prev, "chg": chg, "pct": pct, "high": high, "low": low, "observed": observed, "source": "腾讯行情"})
    return result


def fetch_market_breadth():
    """Approximate A-share breadth from Shanghai and Shenzhen constituent counts."""
    url = "https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&fields=f104,f105,f106&secids=1.000001,0.399001"
    try:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"})
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8", "ignore"))
        rows = (payload.get("data") or {}).get("diff") or []
        up = sum(int(row.get("f104") or 0) for row in rows)
        down = sum(int(row.get("f105") or 0) for row in rows)
        flat = sum(int(row.get("f106") or 0) for row in rows)
        total = up + down + flat
        if not total:
            raise ValueError("breadth empty")
        return {"available": True, "up": up, "down": down, "flat": flat, "total": total, "ratio": round(up / total * 100, 1), "label": "沪深主要成分估算", "url": url}
    except Exception:
        return {"available": False, "label": "等待市场宽度接口", "url": "https://quote.eastmoney.com/center/gridlist.html#hs_a_board"}


def fetch_market_snapshot(now):
    def read_group(items):
        codes = ",".join(item["code"] for item in items)
        return fetch_market_group(items, f"https://qt.gtimg.cn/q={codes}")
    indexes = read_group(MARKET_INDEXES)
    return {
        "updated_at": now.isoformat(timespec="minutes"), "timezone": "Asia/Shanghai",
        "provider": "腾讯行情公开接口", "indices": indexes,
        "global": read_group(MARKET_GLOBAL), "commodities": read_group(MARKET_COMMODITIES),
        "breadth": fetch_market_breadth(),
    }


def fetch_history(item, now):
    code = item["code"]
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,,,400,qfq"
    request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.qq.com/"})
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read(2_000_000).decode("utf-8"))
    series = (payload.get("data") or {}).get(code) or {}
    raw_rows = series.get("day") or series.get("qfqday") or []
    rows = []
    for row in raw_rows:
        if len(row) < 6:
            continue
        close = number(row[2])
        if close is None or close <= 0:
            continue
        rows.append({"date": row[0], "close": close, "volume": number(row[5])})
    rows = completed_rows(rows, now)
    if not rows:
        raise ValueError("empty history")
    return {"code": code, "name": item["name"], "source": "腾讯历史日线", "url": url,
            "fetched_at": now.isoformat(timespec="minutes"), "rows": rows[-400:]}


def refresh_histories(path, now):
    history = read_json(path, {})
    if not isinstance(history, dict):
        history = {}
    series = history.setdefault("series", {})
    pending = []
    for item in MARKET_INDEXES:
        if item["code"].startswith("hk"):
            continue
        cached = series.get(item["code"], {})
        fetched = cached.get("fetched_at", "")
        if cached.get("rows") and fetched[:10] == now.date().isoformat():
            # Repeat after the session closes if today's cache was built before 15:00.
            if now.hour < 15 or cached["rows"][-1]["date"] == now.date().isoformat() or is_trading_day(now.date()) is False:
                continue
        pending.append(item)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch_history, item, now): item for item in pending}
        for future in as_completed(futures):
            item = futures[future]
            try:
                series[item["code"]] = future.result()
            except Exception as exc:
                old = series.get(item["code"])
                if old:
                    old["fetch_error"] = type(exc).__name__
    history["format_version"] = 2
    history["updated_at"] = now.isoformat(timespec="minutes")
    path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    return history


def read_json(path, fallback):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return fallback


def clean(text):
    return re.sub(r"\s+", " ", (text or "")).strip()


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.href, self.parts = [], None, []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self.href = dict(attrs).get("href")
            self.parts = []

    def handle_data(self, data):
        if self.href is not None:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.href:
            title = clean(" ".join(self.parts))
            if 8 <= len(title) <= 180:
                self.links.append((self.href, title))
            self.href, self.parts = None, []


def node_text(node):
    return clean(" ".join(node.itertext())) if node is not None else ""


def parse_feed(raw, source):
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    items = root.findall(".//item") or root.findall(".//{*}entry")
    result = []
    for item in items[:12]:
        title_node = item.find("title")
        if title_node is None:
            title_node = item.find("{*}title")
        link_node = item.find("link")
        if link_node is None:
            link_node = item.find("{*}link")
        title = node_text(title_node)
        link = clean(link_node.text) if link_node is not None and link_node.text else ""
        if not link and link_node is not None:
            link = clean(link_node.attrib.get("href", ""))
        if not title or not link:
            continue
        date_node = item.find("pubDate")
        if date_node is None:
            date_node = item.find("published")
        if date_node is None:
            date_node = item.find("updated")
        if date_node is None:
            date_node = item.find("{*}published")
        if date_node is None:
            date_node = item.find("{*}updated")
        published = node_text(date_node)
        result.append({"title": title, "url": link, "source": source["name"], "category": source["category"], "published_at": published or now_bj().isoformat(timespec="minutes"), "date_quality": "publisher" if published else "unknown", "summary": "来自公开原始来源的最新发布。"})
    return result


def parse_html(raw, source):
    parser = LinkParser()
    parser.feed(raw.decode("utf-8", "ignore"))
    host = urlparse(source["url"]).netloc
    result, seen = [], set()
    for href, title in parser.links:
        link = urljoin(source["url"], href)
        if not link.startswith(("http://", "https://")) or urlparse(link).netloc != host or link in seen:
            continue
        if any(x in title.lower() for x in ("首页", "登录", "注册", "联系我们", "网站地图", "返回顶部")):
            continue
        seen.add(link)
        date_match = re.search(r"(20\d{2})[-/]?(\d{2})[-/]?(\d{2})", link)
        published = "-".join(date_match.groups()) if date_match else now_bj().isoformat(timespec="minutes")
        result.append({"title": title, "url": link, "source": source["name"], "category": source["category"], "published_at": published, "date_quality": "url_date" if date_match else "unknown", "summary": "打开原文查看完整公告、数据表或政策文件。"})
        if len(result) >= 5:
            break
    return result


def collect(source):
    target = source.get("feed", source["url"])
    try:
        status, content_type, raw = fetch(target)
        items = parse_feed(raw, source) if source.get("feed") or "xml" in content_type else parse_html(raw, source)
        if not items:
            items = [{"title": f"查看{source['name']}最新发布", "url": source["url"], "source": source["name"], "category": source["category"], "published_at": now_bj().isoformat(timespec="minutes"), "date_quality": "source_entry", "item_type": "source_entry", "summary": "该来源未提供可机器读取的列表，点击进入官网查看最新内容。"}]
        return {"source": source, "status": "reachable" if 200 <= status < 400 else f"http-{status}", "detail": str(status), "items": items}
    except Exception as exc:
        return {"source": source, "status": "restricted", "detail": type(exc).__name__, "items": [{"title": f"打开{source['name']}官网", "url": source["url"], "source": source["name"], "category": source["category"], "published_at": now_bj().isoformat(timespec="minutes"), "date_quality": "source_entry", "item_type": "source_entry", "summary": "该来源暂时无法自动读取，点击官网仍可查看最新发布。"}]}


def main():
    now = now_bj()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(collect, SOURCES))
    statuses = [{**row["source"], "status": row["status"], "detail": row["detail"]} for row in results]
    news = [item for row in results for item in row["items"]][:80]
    payload = {"updated_at": now.isoformat(timespec="minutes"), "timezone": "Asia/Shanghai", "refresh_interval_seconds": 60, "sources": statuses, "news": news}
    os.makedirs("data", exist_ok=True)
    with open("data/source-status.json", "w", encoding="utf-8") as handle:
        json.dump({"updated_at": payload["updated_at"], "timezone": payload["timezone"], "sources": statuses}, handle, ensure_ascii=False, indent=2)
    with open("data/news.json", "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    history = refresh_histories(Path("data/market-history.json"), now)
    market = fetch_market_snapshot(now)
    previous = read_json("data/market.json", {})
    if not market.get("indices") and previous.get("indices"):
        market = previous
        market["data_stale"] = True
        market["stale_reason"] = "本次接口未返回有效指数，沿用最近一次有效快照。"
    advanced = build_analysis(market, history, news, now)
    market["advanced_analysis"] = advanced
    market["analysis"] = {
        "stance": advanced["regime"]["label"],
        "tone": f"数据覆盖：{advanced['regime']['quality_label']}；{advanced['methodology'][0]}",
        "watch": [signal["interpretation"] for signal in advanced["signals"] if signal["status"] == "available"][:3],
        "risks": advanced["methodology"][1:],
    }
    with open("data/market.json", "w", encoding="utf-8") as handle:
        json.dump(market, handle, ensure_ascii=False, indent=2)



if __name__ == "__main__":
    main()

