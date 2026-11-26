$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$repo = 'D:\research\ml-des\repo'
$py = 'D:\research\ml-des\.venv\Scripts\python.exe'
Set-Location $repo
$env:PYTHONPATH = "$repo\src"
& $py scripts\score_chunk_model.py --checkpoint "$repo\results\stage2\20261126T150811Z-fa7d0232-c7d52488-s0\best.pt" --key 0xF2D2BB1DDEC586ED --pairs 64 --device cuda --out "$repo\results\stage2\ai2_scores_F2D2.json"
exit $LASTEXITCODE
