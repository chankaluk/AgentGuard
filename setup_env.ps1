param(
  [string]$BasePython = "python"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = if ($IsWindows -or $PSVersionTable.PSEdition -eq "Desktop") {
  Join-Path $Root ".venv\Scripts\python.exe"
} else {
  Join-Path $Root ".venv/bin/python"
}

function Invoke-Checked {
  param(
    [string]$Executable,
    [string[]]$Arguments
  )

  & $Executable @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Command failed with exit code ${LASTEXITCODE}: $Executable $($Arguments -join ' ')"
  }
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
  Write-Host "Creating the project-local .venv ..." -ForegroundColor Cyan
  Invoke-Checked -Executable $BasePython -Arguments @("-m", "venv", (Join-Path $Root ".venv"))
}

Write-Host "Installing AgentGuard dependencies ..." -ForegroundColor Cyan
Invoke-Checked -Executable $VenvPython -Arguments @(
  "-m", "pip", "install", "--disable-pip-version-check", "-r", (Join-Path $Root "requirements.txt")
)

Write-Host "Verifying core dependencies ..." -ForegroundColor Cyan
Invoke-Checked -Executable $VenvPython -Arguments @(
  "-c", "import torch,numpy,docx,pptx,matplotlib,psutil; print('AgentGuard dependency check: OK')"
)

Write-Host "Project environment is ready: $VenvPython" -ForegroundColor Green
