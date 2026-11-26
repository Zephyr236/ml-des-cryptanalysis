$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = 'SilentlyContinue'
$repo = 'D:\research\ml-des\repo'
$py = 'D:\research\ml-des\.venv\Scripts\python.exe'
Set-Location $repo
$env:PYTHONPATH = "$repo\src"
& $py scripts\differential_match.py --key 0x133457799BBCDFF1 --delta 0x0000001010000000 --trail-l5 0x0C000060 --rounds 6 --pairs 323000000 --batch 65536 --device cuda --out results/stage2 --filter-vector "8,1,19,48,8,4,2,32" --top-k 1 --full-boxes ""
exit $LASTEXITCODE
