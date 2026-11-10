# .env 의 값을 화면에 출력하지 않고 Railway Variables 로 그대로 옮깁니다.
# 사용법 (my_api 폴더에서, railway login / railway link 를 마친 뒤):
#   .\set_railway_vars.ps1 -FrontOrigins "https://내앱.vercel.app"
param(
  [string]$FrontOrigins = ""
)

$envFile = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $envFile)) { Write-Error ".env 파일이 없습니다."; exit 1 }

$wanted = @("SUPABASE_URL", "SUPABASE_SECRET_KEY")
$args = @()
foreach ($line in Get-Content $envFile) {
  $t = $line.Trim()
  if ($t -eq "" -or $t.StartsWith("#") -or -not $t.Contains("=")) { continue }
  $k, $v = $t.Split("=", 2)
  $k = $k.Trim(); $v = $v.Trim().Trim('"').Trim("'")
  if ($wanted -contains $k -and $v -ne "") { $args += "$k=$v"; Write-Host "옮길 변수: $k" }
}
if ($args.Count -ne $wanted.Count) { Write-Error "SUPABASE_URL / SUPABASE_SECRET_KEY 를 .env 에서 모두 찾지 못했습니다."; exit 1 }
if ($FrontOrigins -ne "") { $args += "FRONT_ORIGINS=$FrontOrigins"; Write-Host "옮길 변수: FRONT_ORIGINS" }

foreach ($a in $args) { railway variables --set $a --skip-deploys | Out-Null }
Write-Host "완료! (값은 출력하지 않았습니다) 확인: railway variables"
