$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$repo = 'D:\research\ml-des\repo'
$py = 'D:\research\ml-des\.venv\Scripts\python.exe'
Set-Location $repo
$env:PYTHONPATH = "$repo\src"
$out = "$repo\results\stage2\chunk4r_start.out"
$err = "$repo\results\stage2\chunk4r_start.err"
$args = @('-m','des_ml.train.train_chunk_scorer','--config','configs\six_round\chunk-scorer-des4-v2.yaml','--out','results/stage2')
$p = Start-Process -FilePath $py -ArgumentList $args -RedirectStandardOutput $out -RedirectStandardError $err -NoNewWindow -Wait -PassThru
Write-Output "EXIT $($p.ExitCode)"
if (Test-Path $err) { if ((Get-Item $err).Length -gt 0) { Write-Output '==ERR'; Get-Content $err -Tail 20 } }
if (Test-Path $out) { Get-Content $out -Tail 10 }
