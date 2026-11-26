# Bootstrap the Windows GPU host. Idempotent.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = 'SilentlyContinue'

$root = if ($env:DES_REMOTE_ROOT) { $env:DES_REMOTE_ROOT } else { 'D:\research\ml-des' }
New-Item -ItemType Directory -Force -Path "$root\logs" | Out-Null
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"

Write-Output "=== bootstrap $(Get-Date -Format o) root=$root ==="
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Output 'installing uv...'
    irm https://astral.sh/uv/install.ps1 | iex
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
uv --version

if (-not (Test-Path "$root\.venv")) {
    uv venv "$root\.venv" --python 3.12
}
$py = "$root\.venv\Scripts\python.exe"

Write-Output '=== installing torch (CUDA 12.4) ==='
uv pip install --python $py torch --index-url https://download.pytorch.org/whl/cu124

Write-Output '=== installing experiment dependencies ==='
uv pip install --python $py numpy pyyaml pytest tqdm

Write-Output '=== verify ==='
& $py -c "import torch,sys;print('python',sys.version.split()[0]);print('torch',torch.__version__);print('cuda_available',torch.cuda.is_available());print('device',torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu');print('cuda',torch.version.cuda)"
Write-Output "=== done $(Get-Date -Format o) ==="
