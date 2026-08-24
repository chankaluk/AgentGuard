param(
  [string]$PythonExecutable = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not $PythonExecutable) {
  $VenvPython = if ($IsWindows -or $PSVersionTable.PSEdition -eq "Desktop") {
    Join-Path $Root ".venv\Scripts\python.exe"
  } else {
    Join-Path $Root ".venv/bin/python"
  }
  $PythonExecutable = if (Test-Path -LiteralPath $VenvPython) { $VenvPython } elseif (Get-Command python3 -ErrorAction SilentlyContinue) { "python3" } else { "python" }
}

function Invoke-PythonChecked {
  param([string[]]$Arguments)

  & $PythonExecutable @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Python step failed with exit code ${LASTEXITCODE}: $($Arguments -join ' ')"
  }
}

if (-not (Test-Path -LiteralPath (Join-Path $Root "artifacts/agentguard.pt"))) {
  Write-Host "Model not found; running the full pipeline first." -ForegroundColor Yellow
  & "$Root\run_all.ps1" -PythonExecutable $PythonExecutable
  if ($LASTEXITCODE -ne 0) {
    throw "Full pipeline failed with exit code $LASTEXITCODE"
  }
}

Invoke-PythonChecked -Arguments @("scripts/serve.py")
