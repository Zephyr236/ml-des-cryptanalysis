# Run a training experiment inside the GPU host's virtualenv.
param(
    [Parameter(Mandatory = $true)][string]$Config,
    [string]$Out = 'results/stage1',
    [string]$CodeSha = '',
    [string]$Device = 'cuda',
    [int]$MaxSteps = 0,
    [string]$Repo = 'D:\research\ml-des\repo',
    [string]$Venv = 'D:\research\ml-des\.venv'
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = 'SilentlyContinue'

$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
$py = "$Venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "python not found: $py (run bootstrap.ps1 first)" }

Set-Location $Repo
$env:PYTHONPATH = "$Repo\src"
if ($CodeSha) { $env:DES_CODE_SHA = $CodeSha }

$arguments = @(
    '-m', 'des_ml.train.train_distinguisher',
    '--config', $Config,
    '--out', $Out,
    '--device', $Device
)
if ($MaxSteps -gt 0) { $arguments += @('--max-steps', "$MaxSteps") }

Write-Output "=== run $(Get-Date -Format o) config=$Config sha=$CodeSha ==="
& $py @arguments
$code = $LASTEXITCODE
Write-Output "=== exit $code $(Get-Date -Format o) ==="
exit $code
