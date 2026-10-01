# TokenForward class setup for Windows (PowerShell). One command:
#   irm https://raw.githubusercontent.com/sayonsom/tokenforward/main/setup.ps1 | iex
# Options via env vars before running: $env:TFD_DEMO = "numpy" (default pandas), $env:TFD_WORK = "C:\tfd"
$ErrorActionPreference = "Stop"
$Work = if ($env:TFD_WORK) { $env:TFD_WORK } else { Join-Path $HOME "tfd-class" }
$Demo = if ($env:TFD_DEMO) { $env:TFD_DEMO } else { "pandas" }

function Need($cmd, $fix) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
    Write-Host "Installing $cmd ..."
    Invoke-Expression $fix
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User") + ";$HOME\.local\bin"
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { throw "$cmd still missing. Install it, open a new terminal, rerun." }
  }
}

Need git    "winget install --id Git.Git -e --silent --accept-source-agreements --accept-package-agreements"
Need node   "winget install --id OpenJS.NodeJS.LTS -e --silent --accept-source-agreements --accept-package-agreements"
Need uv     "powershell -ExecutionPolicy ByPass -c 'irm https://astral.sh/uv/install.ps1 | iex'"
Need claude "irm https://claude.ai/install.ps1 | iex"
git config --global core.longpaths true

Write-Host "== Python tools: graphify, spec-kit"
uv tool install graphifyy --force | Out-Null
uv tool install specify-cli --force | Out-Null
uv tool update-shell | Out-Null
$env:Path += ";$HOME\.local\bin"

Write-Host "== TokenForward source"
New-Item -ItemType Directory -Force -Path $Work | Out-Null
$Tf = Join-Path $Work "tokenforward"
if (Test-Path $Tf) { git -C $Tf pull -q } else { git clone -q https://github.com/sayonsom/tokenforward.git $Tf }

uv run --python 3.12 --no-project python (Join-Path $Tf "scripts\class_setup.py") --work $Work --demo $Demo
