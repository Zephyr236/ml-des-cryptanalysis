$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = 'SilentlyContinue'
$repo = 'D:\research\ml-des\repo'
$py = 'D:\research\ml-des\.venv\Scripts\python.exe'
$config = 'configs\six_round\distinguisher-des6-cpa.yaml'
Set-Location $repo
$env:PYTHONPATH = "$repo\src"
Write-Output "=== distinguisher $config $(Get-Date -Format o) ==="
& $py -m des_ml.train.train_distinguisher --config $config --out results/stage1 --device cuda
$code = $LASTEXITCODE
Write-Output "=== exit $code $(Get-Date -Format o) ==="
exit $code
