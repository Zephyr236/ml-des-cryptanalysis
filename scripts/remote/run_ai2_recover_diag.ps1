$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$repo = 'D:\research\ml-des\repo'
$py = 'D:\research\ml-des\.venv\Scripts\python.exe'
Set-Location $repo
$env:PYTHONPATH = "$repo\src"
$log = "$repo\results\stage2\ai2_recover_stdout.log"
& $py scripts\recover_from_scores.py --scores "$repo\results\stage2\ai2_scores_F2D2.json" --key 0xF2D2BB1DDEC586ED --rounds 2 --top-k 2 --known-boxes 8 --full-boxes "3,5" --device cuda --out results/stage2 --no-latest *> $log
$code = $LASTEXITCODE
Write-Output "EXIT $code"
if (Test-Path $log) { Get-Content $log -Tail 40 }
exit $code
