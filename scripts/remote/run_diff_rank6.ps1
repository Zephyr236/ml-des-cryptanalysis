$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = 'SilentlyContinue'
$repo = 'D:\research\ml-des\repo'
$py = 'D:\research\ml-des\.venv\Scripts\python.exe'
Set-Location $repo
$env:PYTHONPATH = "$repo\src"
Write-Output "=== 6-round diff rank $(Get-Date -Format o) ==="
& $py scripts\differential_rank.py --key 0x133457799BBCDFF1 --delta 0x0000001010000000 --rounds 6 --pairs 100000000 --batch 65536 --device cuda --out results/stage2
$code = $LASTEXITCODE
Write-Output "=== exit $code $(Get-Date -Format o) ==="
exit $code
