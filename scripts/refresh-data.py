import json, os
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
sources=[
 {'name':'PBC','category':'政策与流动性','url':'https://www.pbc.gov.cn/'},
 {'name':'NBS data','category':'宏观指标','url':'https://data.stats.gov.cn/'},
 {'name':'CNINFO','category':'A股公司披露','url':'https://www.cninfo.com.cn/'},
 {'name':'SSE','category':'交易所','url':'https://www.sse.com.cn/'},
 {'name':'SZSE','category':'交易所','url':'https://www.szse.cn/'},
 {'name':'ChinaBond','category':'债券与利率','url':'https://www.chinabond.com.cn/'},
 {'name':'FRED','category':'全球宏观辅助','url':'https://fred.stlouisfed.org/'},
 {'name':'Federal Reserve','category':'全球宏观辅助','url':'https://www.federalreserve.gov/'}]
now=datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))); results=[]
for source in sources:
 status='restricted'; detail=''
 try:
  request=Request(source['url'],method='HEAD',headers={'User-Agent':'lchzhe-finance-radar/1.0'})
  with urlopen(request,timeout=15) as response: status='reachable' if 200<=response.status<400 else f'http-{response.status}'; detail=str(response.status)
 except Exception as exc: detail=type(exc).__name__
 results.append({**source,'status':status,'detail':detail})
payload={'updated_at':now.isoformat(timespec='minutes'),'timezone':'Asia/Shanghai','sources':results}
os.makedirs('data',exist_ok=True)
with open('data/source-status.json','w',encoding='utf-8') as h: json.dump(payload,h,ensure_ascii=False,indent=2)
os.makedirs('reports',exist_ok=True); report_path=os.path.join('reports',now.strftime('%Y-%m-%d')+'.md')
lines=['# 雷传喆 · 中国宏观与 A 股每日信息底稿','',f'生成时间（北京时间）：{now:%Y-%m-%d %H:%M}','', '> 这是来源状态与研究清单，不构成个性化投资建议。涉及投资决策时请回到原始公告和数据表。','', '## 来源状态','', '| 类别 | 来源 | 状态 | 链接 |','|---|---|---|---|']
for item in results: lines.append(f"| {item['category']} | {item['name']} | {item['status']} | {item['url']} |")
lines += ['', '## 研究顺序','', '1. 政策与流动性：OMO、MLF、LPR、Shibor、国债收益率。','2. 价格与景气：CPI/PPI、PMI、工业增加值、固定资产投资、工业企业利润。','3. A 股披露：巨潮资讯、上交所、深交所的公告原文与定期报告。','4. 结论分成事实、推断、待验证三栏，保留发布时间与原文链接。','']
with open(report_path,'w',encoding='utf-8') as h: h.write('\n'.join(lines))

