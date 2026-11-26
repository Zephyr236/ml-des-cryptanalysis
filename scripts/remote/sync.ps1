# Fetch a git bundle and check out an exact commit on the GPU host.
param(
    [string]$Bundle = 'D:\research\ml-des\repo.bundle',
    [string]$Repo = 'D:\research\ml-des\repo',
    [string]$Branch = 'main',
    [string]$Sha = ''
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

if (-not (Test-Path $Bundle)) { throw "bundle not found: $Bundle" }

if (-not (Test-Path $Repo)) {
    git clone $Bundle $Repo
}
Set-Location $Repo
git fetch $Bundle "+refs/heads/*:refs/remotes/bundle/*" --force
git checkout -B $Branch "bundle/$Branch"
git reset --hard "bundle/$Branch"

$head = (git rev-parse HEAD).Trim()
if ($Sha -and $head -ne $Sha) { throw "bundle head $head does not match requested $Sha" }
Write-Output "remote HEAD $head on $Branch"
