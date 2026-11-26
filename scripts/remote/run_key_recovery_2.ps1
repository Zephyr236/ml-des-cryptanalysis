$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = 'SilentlyContinue'
$repo = 'D:\research\ml-des\repo'
$py = 'D:\research\ml-des\.venv\Scripts\python.exe'
$ckpt = 'D:\research\ml-des\repo\results\stage2\20261126T150811Z-fa7d0232-c7d52488-s0\best.pt'
Set-Location $repo
$env:PYTHONPATH = "$repo\src"
Write-Output "=== key recovery $ckpt $(Get-Date -Format o) ==="
& $py scripts\chunk_key_recovery.py --checkpoint $ckpt --out results/stage2 --keys 1 --pairs 64 --top 4 --known-boxes 8 --eval-keys 8 --device cuda
$code = $LASTEXITCODE
Write-Output "=== exit $code $(Get-Date -Format o) ==="
exit $code
