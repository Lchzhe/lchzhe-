"""Refresh public finance sources and build a linkable news feed."""
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

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


def now_bj():
    return datetime.now(timezone.utc).astimezone(BEIJING)


def fetch(url, limit=400_000):
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, text/html, */*"})
    with urlopen(request, timeout=15) as response:
        return response.status, response.headers.get_content_type(), response.read(limit)


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
        result.append({"title": title, "url": link, "source": source["name"], "category": source["category"], "published_at": node_text(date_node) or now_bj().isoformat(timespec="minutes"), "summary": "来自公开原始来源的最新发布。"})
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
        result.append({"title": title, "url": link, "source": source["name"], "category": source["category"], "published_at": now_bj().isoformat(timespec="minutes"), "summary": "打开原文查看完整公告、数据表或政策文件。"})
        if len(result) >= 5:
            break
    return result


def collect(source):
    target = source.get("feed", source["url"])
    try:
        status, content_type, raw = fetch(target)
        items = parse_feed(raw, source) if source.get("feed") or "xml" in content_type else parse_html(raw, source)
        if not items:
            items = [{"title": f"查看{source['name']}最新发布", "url": source["url"], "source": source["name"], "category": source["category"], "published_at": now_bj().isoformat(timespec="minutes"), "summary": "该来源未提供可机器读取的列表，点击进入官网查看最新内容。"}]
        return {"source": source, "status": "reachable" if 200 <= status < 400 else f"http-{status}", "detail": str(status), "items": items}
    except Exception as exc:
        return {"source": source, "status": "restricted", "detail": type(exc).__name__, "items": [{"title": f"打开{source['name']}官网", "url": source["url"], "source": source["name"], "category": source["category"], "published_at": now_bj().isoformat(timespec="minutes"), "summary": "该来源暂时无法自动读取，点击官网仍可查看最新发布。"}]}


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
    os.makedirs("reports", exist_ok=True)
    report_path = os.path.join("reports", now.strftime("%Y-%m-%d") + ".md")
    lines = ["# 雷传喆 · 中国宏观与 A 股每日信息底稿", "", f"生成时间（北京时间）：{now:%Y-%m-%d %H:%M}", "", "> 这是公开来源聚合与研究清单，不构成个性化投资建议。请回到原始公告和数据表核对。", "", "## 来源状态", "", "| 类别 | 来源 | 状态 | 链接 |", "|---|---|---|---|"]
    lines += [f"| {item['category']} | {item['name']} | {item['status']} | {item['url']} |" for item in statuses]
    lines += ["", "## 最新可追溯条目", ""]
    lines += [f"- [{item['title']}]({item['url']}) · {item['source']} · {item['category']}" for item in news[:40]]
    lines += ["", "## 研究顺序", "", "1. 先读政策与流动性，再看价格、景气和公司披露。", "2. 每条结论分成事实、推断、待验证三栏。", "3. 投资决策前回到原始来源核对时间、口径和修订说明。", ""]
    with open(report_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


if __name__ == "__main__":
    main()

