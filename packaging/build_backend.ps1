$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Spec = Join-Path $ProjectRoot "packaging\waymark_backend.spec"

if (-not (Test-Path $Python)) {
    throw "WAYMARK Python environment not found: $Python"
}

if (-not (Test-Path $Spec)) {
    throw "PyInstaller spec not found: $Spec"
}

Write-Host "WAYMARK Stage 1 - Python backend packaging" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"
Write-Host ""

# Keep PyInstaller's temporary/work files outside OneDrive.
$LocalRoot = if ($env:LOCALAPPDATA) {
    Join-Path $env:LOCALAPPDATA "WAYMARK\pyinstaller-build"
} else {
    Join-Path $env:TEMP "WAYMARK\pyinstaller-build"
}

if (Test-Path $LocalRoot) {
    Remove-Item -LiteralPath $LocalRoot -Recurse -Force -ErrorAction SilentlyContinue
}

New-Item -ItemType Directory -Path $LocalRoot -Force | Out-Null

$DistPath = Join-Path $ProjectRoot "dist"

try {
    & $Python -m PyInstaller `
        --clean `
        --noconfirm `
        --distpath $DistPath `
        --workpath $LocalRoot `
        $Spec

    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }

    $Backend = Join-Path $DistPath "WAYMARK-backend.exe"

    if (-not (Test-Path $Backend)) {
        throw "Build completed but backend executable was not found: $Backend"
    }

    Write-Host ""
    Write-Host "BUILD SUCCESSFUL" -ForegroundColor Green
    Write-Host "Backend: $Backend"
    Write-Host "PyInstaller work directory: $LocalRoot"
}
finally {
    if (Test-Path $LocalRoot) {
        Remove-Item -LiteralPath $LocalRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
