param([string]$OutputDir = 'D:\C\桌面\雷传喆的资料\2026秋季学期\金融\每日研报')
$ErrorActionPreference='SilentlyContinue'
New-Item -ItemType Directory -Force $OutputDir | Out-Null
$now=[DateTime]::UtcNow.AddHours(8); $stamp=$now.ToString('yyyy-MM-dd HH:mm')
$sources=@(
 @{name='PBC';url='https://www.pbc.gov.cn/'}, @{name='NBS data';url='https://data.stats.gov.cn/'}, @{name='CNINFO';url='https://www.cninfo.com.cn/'}, @{name='ChinaBond';url='https://www.chinabond.com.cn/'}, @{name='FRED';url='https://fred.stlouisfed.org/'}, @{name='Federal Reserve';url='https://www.federalreserve.gov/'}, @{name='BLS';url='https://www.bls.gov/'}, @{name='BEA';url='https://www.bea.gov/'} )
$rows=@(); foreach($s in $sources){$status='manual check'; try{$r=Invoke-WebRequest -Uri $s.url -Method Head -TimeoutSec 12 -UseBasicParsing; if($r.StatusCode -ge 200 -and $r.StatusCode -lt 400){$status='reachable'}}catch{$status='restricted'}}
$md="# Daily Finance Information Report`n`nGenerated (Beijing): $stamp`n`nThis is a research note. Verify original sources before any investment action.`n`n## Source status`n`n| Source | URL | Status |`n|---|---|---|`n"
foreach($s in $sources){$md += "| $($s.name) | $($s.url) | $status |`n"}
$md += "`n## Review checklist`n`n- Policy and liquidity: OMO, MLF, LPR, Shibor, government bond yields.`n- Prices and activity: CPI/PPI, PMI, industrial output, fixed-asset investment.`n- Company disclosure: CNINFO, exchanges, CSRC original filings.`n- Global macro: Fed, BLS, BEA, FRED, ECB, IMF, OECD.`n- Separate facts, inferences, and items requiring verification.`n"
Set-Content -Path (Join-Path $OutputDir ($now.ToString('yyyy-MM-dd')+'-finance-report.md')) -Value $md -Encoding utf8
