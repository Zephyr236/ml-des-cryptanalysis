$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$repo = 'D:\research\ml-des\repo'
$py = 'D:\research\ml-des\.venv\Scripts\python.exe'
Set-Location $repo
$env:PYTHONPATH = "$repo\src"
& $py scripts\chunk_key_recovery.py --checkpoint "$repo\results\stage2\20261126T150811Z-fa7d0232-c7d52488-s0\best.pt" --keys 1 --pairs 16 --top 1 --known-boxes 8 --eval-keys 2 --device cuda --out results/stage2
exit $LASTEXITCODE
