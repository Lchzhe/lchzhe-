$ErrorActionPreference = "Stop"
$reportDir = "D:\C\桌面\雷传喆的资料\每日金融信息研报"
$reportDate = (Get-Date).ToString("yyyy-MM-dd")
$reportName = "$reportDate-每日金融信息研报.md"
$reportUri = "https://raw.githubusercontent.com/Lchzhe/lchzhe-/main/reports/$reportDate.md"
New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
for ($attempt = 1; $attempt -le 15; $attempt++) {
  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $reportUri -TimeoutSec 30
    if ($response.StatusCode -eq 200 -and $response.Content.Length -gt 1000) {
      $encoding = New-Object System.Text.UTF8Encoding($false)
      [System.IO.File]::WriteAllText((Join-Path $reportDir $reportName), $response.Content, $encoding)
      exit 0
    }
  } catch { }
  if ($attempt -lt 15) { Start-Sleep -Seconds 60 }
}
throw "日报尚未发布：$reportUri"
