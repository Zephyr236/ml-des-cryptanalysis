# Run the TH-1 trail search on the GPU host.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = 'SilentlyContinue'

$repo = 'D:\research\ml-des\repo'
$py = 'D:\research\ml-des\.venv\Scripts\python.exe'
Set-Location $repo
$env:PYTHONPATH = "$repo\src"

Write-Output "=== trail search $(Get-Date -Format o) ==="
& $py scripts\trail_search.py --config configs\theory\trail-search.yaml --out results/stage1
$code = $LASTEXITCODE
Write-Output "=== exit $code $(Get-Date -Format o) ==="
exit $code
