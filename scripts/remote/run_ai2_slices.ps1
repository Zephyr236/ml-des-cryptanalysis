$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$repo = 'D:\research\ml-des\repo'
$py = 'D:\research\ml-des\.venv\Scripts\python.exe'
Set-Location $repo
$env:PYTHONPATH = "$repo\src"
foreach ($start in 0, 65536, 131072, 196608) {
  $out = "$repo\results\stage2\ai2_slice_$start.out"
  $err = "$repo\results\stage2\ai2_slice_$start.err"
  $args = @('scripts\recover_from_scores.py','--scores',"$repo\results\stage2\ai2_scores_F2D2.json",'--key','0xF2D2BB1DDEC586ED','--rounds','2','--top-k','2','--known-boxes','8','--full-boxes','3,5','--device','cuda','--out','results/stage2','--no-latest','--combo-start',$start,'--combo-count','65536')
  $p = Start-Process -FilePath $py -ArgumentList $args -RedirectStandardOutput $out -RedirectStandardError $err -NoNewWindow -Wait -PassThru
  Write-Output "SLICE $start EXIT $($p.ExitCode)"
  if (Test-Path $out) { Get-Content $out -Tail 20 }
  if (Test-Path $err) { if ((Get-Item $err).Length -gt 0) { Write-Output '==ERR'; Get-Content $err -Tail 10 } }
  if (Test-Path $out) { $t = Get-Content $out -Raw; if ($t -match '"recovered": 1') { Write-Output 'FOUND'; break } }
}
