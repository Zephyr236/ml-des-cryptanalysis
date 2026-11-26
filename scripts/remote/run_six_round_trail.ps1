$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = 'SilentlyContinue'
$repo = 'D:\research\ml-des\repo'
$py = 'D:\research\ml-des\.venv\Scripts\python.exe'
Set-Location $repo
$env:PYTHONPATH = "$repo\src"
Write-Output "=== six-round trail search $(Get-Date -Format o) ==="
& $py scripts\trail_search.py --config configs\theory\six-round-wide2.yaml --out results/stage1
$code = $LASTEXITCODE
Write-Output "=== exit $code $(Get-Date -Format o) ==="
exit $code
