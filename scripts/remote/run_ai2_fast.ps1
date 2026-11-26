$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$repo = 'D:\research\ml-des\repo'
$py = 'D:\research\ml-des\.venv\Scripts\python.exe'
Set-Location $repo
$env:PYTHONPATH = "$repo\src"
$out = "$repo\results\stage2\ai2_fast.out"
$err = "$repo\results\stage2\ai2_fast.err"
$args = @('scripts\ai2_fast_recover.py','--scores',"$repo\results\stage2\ai2_scores_F2D2.json",'--key','0xF2D2BB1DDEC586ED','--top-k','2','--known-boxes','8','--full-boxes','3,5','--device','cuda','--out','results/stage2')
$p = Start-Process -FilePath $py -ArgumentList $args -RedirectStandardOutput $out -RedirectStandardError $err -NoNewWindow -Wait -PassThru
Write-Output "EXIT $($p.ExitCode)"
if (Test-Path $err) { if ((Get-Item $err).Length -gt 0) { Write-Output '==ERR'; Get-Content $err -Tail 20 } }
if (Test-Path $out) { Get-Content $out -Tail 20 }
