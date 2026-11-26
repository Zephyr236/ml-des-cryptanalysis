$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = 'SilentlyContinue'
$repo = 'D:\research\ml-des\repo'
$py = 'D:\research\ml-des\.venv\Scripts\python.exe'
Set-Location $repo
$env:PYTHONPATH = "$repo\src"
& $py scripts\chunk_key_recovery.py --checkpoint "$repo\results\stage2\20261126T150811Z-fa7d0232-c7d52488-s0\best.pt" --keys 1 --pairs 64 --top 2 --known-boxes 6 --eval-keys 8 --device cuda --out results/stage2
exit $LASTEXITCODE
