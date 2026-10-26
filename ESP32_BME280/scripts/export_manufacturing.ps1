<#
.SYNOPSIS
    Export manufacturing files (Gerbers and drill files) from the PCB.

.DESCRIPTION
    Exports manufacturing outputs using the KiCad 10.0 CLI:

      * Gerbers:  kicad-cli pcb export gerbers
      * Drill:    kicad-cli pcb export drill

    SAFETY REQUIREMENTS:
      * An explicit -Confirm parameter is required before any export runs.
      * Fresh ERC and DRC validation is run against the current source files
        immediately before every export. Pre-existing reports are never trusted.
      * Existing outputs are never overwritten unless -Force is also supplied.
      * Export is refused if validation fails, reports contain violations, or
        the design is incomplete (empty schematic, missing Edge.Cuts outline).
      * This script never modifies the schematic, PCB, or project settings.

    These exports produce files for PCB fabrication. They are NOT hardware
    testing and do NOT validate the design functionally.

    To proceed, supply -Confirm yes. There is no flag that silently bypasses
    these checks.

.PARAMETER ProjectDir
    Absolute path to the ESP32_BME280 project directory.

.PARAMETER KicadCli
    Absolute path to the kicad-cli.exe executable.

.PARAMETER OutputDir
    Directory where manufacturing files will be written. Defaults to
    <ProjectDir>\outputs\manufacturing.

.PARAMETER Confirm
    Required confirmation. Must be exactly "yes" to proceed. This prevents
    accidental exports.

.PARAMETER Force
    Allow overwriting existing output files. Without this, the script aborts
    if any target file already exists.

.EXAMPLE
    .\scripts\export_manufacturing.ps1 `
        -ProjectDir "C:\Users\Anirudh\OneDrive\Documents\kicad ai\ESP32_BME280" `
        -KicadCli "C:\Users\Anirudh\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe" `
        -Confirm yes
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $ProjectDir,

    [Parameter(Mandatory = $true)]
    [string] $KicadCli,

    [string] $OutputDir = "",

    [Parameter(Mandatory = $true)]
    [ValidateSet("yes")]
    [string] $Confirm,

    [switch] $Force
)

$ErrorActionPreference = 'Continue'
$scriptName = [System.IO.Path]::GetFileName($MyInvocation.MyCommand.Path)
$failures = @()

function Write-Status {
    param([string] $Message, [string] $Level = "INFO")
    $prefix = switch ($Level) {
        "PASS" { "PASS" }
        "FAIL" { "FAIL" }
        "WARN" { "WARN" }
        default { "INFO" }
    }
    Write-Host ("[{0}] {1}: {2}" -f $prefix, $scriptName, $Message)
}

# -----------------------------------------------------------------
# Hardware profile gate preflight (fail-closed, cannot be bypassed)
#
# This check reuses the Python gate functions in hardware_profile.py
# to ensure U1-U7 facts are verified and at least one footprint is
# verified before any manufacturing output is created or modified.
#
# The preflight runs BEFORE any output directory is created and
# BEFORE -Force or -Confirm has any effect. A gate failure exits
# immediately with no side effects.
# -----------------------------------------------------------------
$gateCheckScript = Join-Path -Path $PSScriptRoot -ChildPath "ai\check_hardware_gates.py"
Write-Status "Checking hardware profile fabrication gate..."
if (Get-Command "python" -ErrorAction SilentlyContinue) {
    $gateOutput = & python $gateCheckScript --project-dir $ProjectDir 2>&1
    $gateExitCode = $LASTEXITCODE
    if ($gateExitCode -ne 0) {
        $failures += "Hardware profile gate check failed"
        Write-Status "Hardware profile gate check FAILED" "FAIL"
        if ($gateOutput) {
            Write-Host $gateOutput
        }
        Write-Host "  Manufacturing export blocked by hardware safety gates."
        Write-Host "  Create hardware_profile.json with all U1-U7 verified and at least one verified footprint."
        Write-Host ""
        Write-Host "Resolve the issues above before attempting export. There is no override to"
        Write-Host "bypass these checks."
        exit 1
    } else {
        Write-Status "Hardware profile gate check: passed" "PASS"
    }
} else {
    Write-Status "Python not found; hardware gate check cannot run" "FAIL"
    $failures += "Python not found; cannot verify hardware profile"
    Write-Host ""
    Write-Host "Resolve the issues above before attempting export. There is no override to"
    Write-Host "bypass these checks."
    exit 1
}

# Resolve output directory
if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = Join-Path -Path $ProjectDir -ChildPath "outputs\manufacturing"
}
if (!(Test-Path -LiteralPath $OutputDir -PathType Container)) {
    try {
        New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
    } catch {
        Write-Status "Failed to create output directory: $OutputDir" "FAIL"
        exit 1
    }
}

$pcbFile = Join-Path -Path $ProjectDir -ChildPath "ESP32_BME280.kicad_pcb"
$schFile = Join-Path -Path $ProjectDir -ChildPath "ESP32_BME280.kicad_sch"

if (!(Test-Path -LiteralPath $pcbFile -PathType Leaf)) {
    Write-Status "PCB file not found: $pcbFile" "FAIL"
    exit 1
}
if (!(Test-Path -LiteralPath $schFile -PathType Leaf)) {
    Write-Status "Schematic file not found: $schFile" "FAIL"
    exit 1
}

# ---- Pre-export: run FRESH ERC and DRC validation against current sources ----
# Reports are written to the validation output dir so they remain available for
# check_outputs.ps1, but the export decision is based on these fresh results.
$validationDir = Join-Path -Path $ProjectDir -ChildPath "outputs\validation"
if (!(Test-Path -LiteralPath $validationDir -PathType Container)) {
    try {
        New-Item -ItemType Directory -Path $validationDir -Force | Out-Null
    } catch {
        Write-Status "Failed to create validation directory: $validationDir" "FAIL"
        exit 1
    }
}

$ercReport = Join-Path -Path $validationDir -ChildPath "ESP32_BME280_erc_report.txt"
$drcReport = Join-Path -Path $validationDir -ChildPath "ESP32_BME280_drc_report.txt"

Write-Status "Running fresh ERC validation before export on: $schFile"
$ercArgs = @("sch", "erc", $schFile, "-o", $ercReport, "--format", "report", "--units", "mm", "--exit-code-violations")
$ercCliRan = $false
$ercCliExitCode = -1
if (!(Test-Path -LiteralPath $KicadCli -PathType Leaf)) {
    $failures += "KiCad CLI not found at: $KicadCli"
    Write-Status "KiCad CLI not found" "FAIL"
} else {
    & $KicadCli @ercArgs 2>$null | Out-Null
    $ercCliExitCode = $LASTEXITCODE
    $ercCliRan = $true
}

# Strictly parse the fresh ERC report
function Test-ErcReportClean {
    param([string] $Path)
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    $content = Get-Content -LiteralPath $Path -Raw -ErrorAction SilentlyContinue
    if ([string]::IsNullOrWhiteSpace($content)) { return $false }
    # Require the exact count line and zero violations
    return ($content -match "ERC messages:\s*\d+\s*Errors\s*0\s*Warnings\s*0")
}
$ercClean = Test-ErcReportClean -Path $ercReport
if (-not $ercCliRan) {
    $failures += "Pre-export ERC CLI did not execute"
    Write-Status "Pre-export ERC CLI did not execute" "FAIL"
} elseif (-not $ercClean) {
    $failures += "Pre-export ERC report contains violations or is malformed"
    Write-Status "Pre-export ERC report not clean" "FAIL"
} else {
    Write-Status "Pre-export ERC: clean (0 errors, 0 warnings)" "PASS"
}

Write-Status "Running fresh DRC validation before export on: $pcbFile"
$drcArgs = @("pcb", "drc", $pcbFile, "-o", $drcReport, "--exit-code-violations")
$drcCliRan = $false
$drcCliExitCode = -1
if (!(Test-Path -LiteralPath $KicadCli -PathType Leaf)) {
    $failures += "KiCad CLI not found at: $KicadCli"
    Write-Status "KiCad CLI not found" "FAIL"
} else {
    & $KicadCli @drcArgs 2>$null | Out-Null
    $drcCliExitCode = $LASTEXITCODE
    $drcCliRan = $true
}

# Strictly parse the fresh DRC report: all three count lines present and zero
function Test-DrcReportClean {
    param([string] $Path)
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    $content = Get-Content -LiteralPath $Path -Raw -ErrorAction SilentlyContinue
    if ([string]::IsNullOrWhiteSpace($content)) { return $false }
    $hasV = $content -match "Found\s+\d+\s+DRC violations"
    $hasU = $content -match "Found\s+\d+\s+unconnected pads"
    $hasF = $content -match "Found\s+\d+\s+Footprint errors"
    $zeroV = $content -match "Found\s+0\s+DRC violations"
    $zeroU = $content -match "Found\s+0\s+unconnected pads"
    $zeroF = $content -match "Found\s+0\s+Footprint errors"
    return ($hasV -and $hasU -and $hasF -and $zeroV -and $zeroU -and $zeroF)
}
$drcClean = Test-DrcReportClean -Path $drcReport
if (-not $drcCliRan) {
    $failures += "Pre-export DRC CLI did not execute"
    Write-Status "Pre-export DRC CLI did not execute" "FAIL"
} elseif (-not $drcClean) {
    $failures += "Pre-export DRC report contains violations or is malformed"
    Write-Status "Pre-export DRC report not clean" "FAIL"
} else {
    Write-Status "Pre-export DRC: clean (0 violations, 0 unconnected, 0 footprint errors)" "PASS"
}

if ($failures.Count -gt 0) {
    Write-Status "EXPORT BLOCKED - pre-export validation failed" "FAIL"
    foreach ($f in $failures) {
        Write-Host ("  - {0}" -f $f)
    }
    Write-Host ""
    Write-Host "Resolve the issues above before attempting export. There is no override to"
    Write-Host "bypass these checks."
    exit 1
}

# ---- Design completeness checks on current source files ----
$emptySch = $false
$missingOutline = $false

$schContent = Get-Content -LiteralPath $schFile -Raw -ErrorAction SilentlyContinue
if ([string]::IsNullOrWhiteSpace($schContent) -or
    (-not ($schContent -match '\(symbol ') -and -not ($schContent -match '\(net '))) {
    $emptySch = $true
    $failures += "Schematic is empty (no symbols or nets). Refusing to export."
}

$pcbContent = Get-Content -LiteralPath $pcbFile -Raw -ErrorAction SilentlyContinue
if ([string]::IsNullOrWhiteSpace($pcbContent) -or
    (-not ($pcbContent -match 'Edge\.Cuts') -and -not ($pcbContent -match '(?s)\(gr_line[\s\S]*?Edge\.Cuts\)|\(gr_arc[\s\S]*?Edge\.Cuts\)|\(gr_circle[\s\S]*?Edge\.Cuts\)|\(gr_poly[\s\S]*?Edge\.Cuts\)|\(fp_line[\s\S]*?Edge\.Cuts\)'))) {
    $missingOutline = $true
    $failures += "PCB has no valid Edge.Cuts outline. Refusing to export."
}

if ($failures.Count -gt 0) {
    Write-Status "EXPORT BLOCKED - design incomplete" "FAIL"
    foreach ($f in $failures) {
        Write-Host ("  - {0}" -f $f)
    }
    exit 1
}

# ---- Check for existing outputs (do not overwrite without -Force) ----
$gerberDir = Join-Path -Path $OutputDir -ChildPath "gerbers"
$drillDir  = Join-Path -Path $OutputDir -ChildPath "drill"

$existingTargets = @()
if (Test-Path -LiteralPath $gerberDir -PathType Container) {
    $existingTargets += $gerberDir
}
if (Test-Path -LiteralPath $drillDir -PathType Container) {
    $existingTargets += $drillDir
}

if ($existingTargets.Count -gt 0 -and !$Force) {
    Write-Status "Output directories already exist. Use -Force to overwrite." "FAIL"
    foreach ($t in $existingTargets) {
        Write-Host ("  Existing: {0}" -f $t)
    }
    exit 1
}

Write-Status "All pre-export checks passed. Proceeding with export from: $pcbFile"
Write-Host ("  Gerbers -> {0}" -f $gerberDir)
Write-Host ("  Drill   -> {0}" -f $drillDir)

# ---- Export Gerbers ----
Write-Status "Exporting Gerbers..."
if (!(Test-Path -LiteralPath $KicadCli -PathType Leaf)) {
    $failures += "KiCad CLI not found at: $KicadCli"
    Write-Status "KiCad CLI not found" "FAIL"
} else {
    & $KicadCli pcb export gerbers $pcbFile -o $gerberDir 2>$null | Out-Null
    $gerberExitCode = $LASTEXITCODE
    if ($gerberExitCode -eq 0) {
        Write-Status "Gerber export completed (exit 0)" "PASS"
    } else {
        $failures += "Gerber export exited with code $gerberExitCode"
        Write-Status "Gerber export failed (exit $gerberExitCode)" "FAIL"
    }
}

# ---- Export Drill files ----
Write-Status "Exporting drill files..."
if (!(Test-Path -LiteralPath $KicadCli -PathType Leaf)) {
    $failures += "KiCad CLI not found at: $KicadCli"
    Write-Status "KiCad CLI not found" "FAIL"
} else {
    & $KicadCli pcb export drill $pcbFile -o $drillDir 2>$null | Out-Null
    $drillExitCode = $LASTEXITCODE
    if ($drillExitCode -eq 0) {
        Write-Status "Drill export completed (exit 0)" "PASS"
    } else {
        $failures += "Drill export exited with code $drillExitCode"
        Write-Status "Drill export failed (exit $drillExitCode)" "FAIL"
    }
}

Write-Host ""
if ($failures.Count -gt 0) {
    Write-Status "MANUFACTURING EXPORT FAILED" "FAIL"
    foreach ($f in $failures) {
        Write-Host ("  - {0}" -f $f)
    }
    exit 1
}

Write-Status "MANUFACTURING EXPORT COMPLETED" "PASS"
Write-Host ""
Write-Host "NOTE: Gerber and drill exports are fabrication outputs. They are NOT"
Write-Host "design-rule checks and NOT hardware testing. Run validate_project.ps1"
Write-Host "separately for ERC/DRC verification."
exit 0
