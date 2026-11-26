$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = 'SilentlyContinue'
$repo = 'D:\research\ml-des\repo'
$py = 'D:\research\ml-des\.venv\Scripts\python.exe'
$scores = 'D:\research\ml-des\repo\results\stage2\20261126T165820Z-9d233012-7f919ef3-s0\scores.json'
Set-Location $repo
$env:PYTHONPATH = "$repo\src"
& $py scripts\recover_from_scores.py --scores $scores --key 0x133457799BBCDFF1 --rounds 6 --top-k 2 --known-boxes 8 --device cuda --out results/stage2
exit $LASTEXITCODE
