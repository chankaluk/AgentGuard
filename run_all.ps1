param(
  [string]$PythonExecutable = "",
  [switch]$VerifyReferences
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

Invoke-PythonChecked -Arguments @("scripts/generate_demo_data.py")
Invoke-PythonChecked -Arguments @("scripts/evaluate_baselines.py")
Invoke-PythonChecked -Arguments @("scripts/train.py")
Invoke-PythonChecked -Arguments @("scripts/evaluate.py")
if ($VerifyReferences) {
  Invoke-PythonChecked -Arguments @("scripts/verify_references.py")
}
Invoke-PythonChecked -Arguments @("-m", "unittest", "discover", "-s", "tests", "-v")
Invoke-PythonChecked -Arguments @("scripts/generate_submission_docs.py")
Invoke-PythonChecked -Arguments @("scripts/verify_project.py")
Invoke-PythonChecked -Arguments @("scripts/package_project.py")

Write-Host "AgentGuard pipeline completed. Outputs: artifacts/ and submission/." -ForegroundColor Green
