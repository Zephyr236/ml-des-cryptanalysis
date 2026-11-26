# Run the six DDT-rank configs on the GPU host.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = 'SilentlyContinue'

$repo = 'D:\research\ml-des\repo'
$py = 'D:\research\ml-des\.venv\Scripts\python.exe'
Set-Location $repo
$env:PYTHONPATH = "$repo\src"

Get-ChildItem 'configs\eval\ddt-rank-*.yaml' | Sort-Object Name | ForEach-Object {
    Write-Output "=== $($_.Name) $(Get-Date -Format o) ==="
    & $py scripts\ddt_rank.py --config $_.FullName --out results/stage1
    if ($LASTEXITCODE -ne 0) { throw "failed: $($_.Name)" }
}
Write-Output "=== all DDT-rank configs done $(Get-Date -Format o) ==="
