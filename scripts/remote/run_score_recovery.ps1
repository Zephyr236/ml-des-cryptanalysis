$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = 'SilentlyContinue'
$repo = 'D:\research\ml-des\repo'
$py = 'D:\research\ml-des\.venv\Scripts\python.exe'
$scores = 'D:\research\ml-des\repo\results\stage2\20261126T154935Z-80d903b0-583165ba-s0\scores.json'
Set-Location $repo
$env:PYTHONPATH = "$repo\src"
& $py scripts\recover_from_scores.py --scores $scores --key 0x133457799BBCDFF1 --rounds 6 --top-k 3 --known-boxes 8 --device cuda --out results/stage2
exit $LASTEXITCODE
