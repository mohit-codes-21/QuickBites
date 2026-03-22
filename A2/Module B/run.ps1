param(
    [ValidateSet("help", "venv", "install", "run", "clean")]
    [string]$Target = "run",
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

$VenvDir = ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$ReqFile = "app\requirements.txt"
$AppFile = "app\app.py"

function Ensure-Venv {
    if (-not (Test-Path $VenvPython)) {
        Write-Host "[venv] Creating virtual environment..."
        & $Python -m venv $VenvDir
    }
    else {
        Write-Host "[venv] Virtual environment already exists."
    }
}

function Install-Deps {
    Ensure-Venv
    Write-Host "[install] Upgrading pip..."
    & $VenvPython -m pip install --upgrade pip

    Write-Host "[install] Installing requirements..."
    & $VenvPython -m pip install -r $ReqFile
}

function Run-App {
    Install-Deps
    Write-Host "[run] Starting Flask app..."
    & $VenvPython $AppFile
}

function Clean-Venv {
    if (Test-Path $VenvDir) {
        Remove-Item -Recurse -Force $VenvDir
        Write-Host "[clean] Removed $VenvDir"
    }
    else {
        Write-Host "[clean] No virtual environment found."
    }
}

switch ($Target) {
    "help" {
        Write-Host "Targets:"
        Write-Host "  .\run.ps1 -Target venv"
        Write-Host "  .\run.ps1 -Target install"
        Write-Host "  .\run.ps1 -Target run"
        Write-Host "  .\run.ps1 -Target clean"
    }
    "venv" { Ensure-Venv }
    "install" { Install-Deps }
    "run" { Run-App }
    "clean" { Clean-Venv }
}
