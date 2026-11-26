$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = 'SilentlyContinue'
$repo = 'D:\research\ml-des\repo'
$py = 'D:\research\ml-des\.venv\Scripts\python.exe'
$config = 'configs\six_round\chunk-scorer-des6-r4.yaml'
Set-Location $repo
$env:PYTHONPATH = "$repo\src"
Write-Output "=== chunk scorer $config $(Get-Date -Format o) ==="
& $py -m des_ml.train.train_chunk_scorer --config $config --out results/stage2
$code = $LASTEXITCODE
Write-Output "=== exit $code $(Get-Date -Format o) ==="
exit $code
