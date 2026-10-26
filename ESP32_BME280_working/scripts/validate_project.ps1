<#
.SYNOPSIS
    Run KiCad design-rule checks (schematic ERC and PCB DRC) and save reports.

.DESCRIPTION
    Runs two independent design-rule checks using the KiCad 10.0 CLI:

      1. Schematic Electrical Rules Check (ERC):  kicad-cli sch erc --exit-code-violations
      2. PCB Design Rules Check (DRC):             kicad-cli pcb drc --exit-code-violations

    The --exit-code-violations flag makes the CLI return a non-zero exit code when
    violations exist. This script also independently parses the generated report
    files to count violations, so that exit code zero alone is never treated as
    proof of a clean design.

    Reports are written in KiCad's native "report" text format only (no JSON
    variant, to avoid format/extension mismatch).

    IMPORTANT: These are DESIGN-RULE CHECKS only. They verify the design against
    KiCad's electrical and physical design rules. They do NOT constitute
    hardware testing, functional validation, or certification of the physical
    board. A passing result means no design-rule violations were reported; it
    does NOT mean the circuit is electrically correct or manufacturable.

    This script never modifies the schematic, PCB, or project settings, and it
    never deletes the lock file.

.PARAMETER ProjectDir
    Absolute path to the ESP32_BME280 project directory.

.PARAMETER KicadCli
    Absolute path to the kicad-cli.exe executable.

.PARAMETER OutputDir
    Directory where ERC and DRC reports will be written. Defaults to
    <ProjectDir>\outputs\validation.

.PARAMETER ErcUnits
    Report units for the ERC report: "in", "mm", or "mils". Default: "mm".

.PARAMETER ErcSeverityAll
    Report all ERC violations (all severity levels).

.PARAMETER ErcSeverityError
    Report ERC error-level violations.

.PARAMETER ErcSeverityWarning
    Report ERC warning-level violations.

.PARAMETER ErcSeverityExclusions
    Report excluded ERC violations.

.EXAMPLE
    .\scripts\validate_project.ps1 `
        -ProjectDir "C:\Users\Anirudh\OneDrive\Documents\kicad ai\ESP32_BME280" `
        -KicadCli "C:\Users\Anirudh\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $ProjectDir,

    [Parameter(Mandatory = $true)]
    [string] $KicadCli,

    [string] $OutputDir = "",

    [ValidateSet("in", "mm", "mils")]
    [string] $ErcUnits = "mm",

    [switch] $ErcSeverityAll,
    [switch] $ErcSeverityError,
    [switch] $ErcSeverityWarning,
    [switch] $ErcSeverityExclusions
)

$ErrorActionPreference = 'Continue'
$script:scriptName = [System.IO.Path]::GetFileName($MyInvocation.MyCommand.Path)
$script:failures = @()
$script:checksRun = @()

function Write-Status {
    param([string] $Message, [string] $Level = "INFO")
    $prefix = switch ($Level) {
        "PASS" { "PASS" }
        "FAIL" { "FAIL" }
        "WARN" { "WARN" }
        "INCOMPLETE" { "INCOMPLETE" }
        default { "INFO" }
    }
    Write-Host ("[{0}] {1}: {2}" -f $prefix, $script:scriptName, $Message)
}

# Resolve output directory
if ([string]::IsNullOrWhiteSpace($OutputDir)) {
    $OutputDir = Join-Path -Path $ProjectDir -ChildPath "outputs\validation"
}
if (!(Test-Path -LiteralPath $OutputDir -PathType Container)) {
    try {
        New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
    } catch {
        Write-Status "Failed to create output directory: $OutputDir" "FAIL"
        exit 1
    }
}

# Resolve input files
$schFile = Join-Path -Path $ProjectDir -ChildPath "ESP32_BME280.kicad_sch"
$pcbFile = Join-Path -Path $ProjectDir -ChildPath "ESP32_BME280.kicad_pcb"

$ercReport = Join-Path -Path $OutputDir -ChildPath "ESP32_BME280_erc_report.txt"
$drcReport = Join-Path -Path $OutputDir -ChildPath "ESP32_BME280_drc_report.txt"

# ---- Helper: parse ERC report for violation counts (STRICT) ----
function Parse-ErcReport {
    param([string] $Path)
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) {
        return @{ Errors = -1; Warnings = -1; Parseable = $false }
    }
    $content = Get-Content -LiteralPath $Path -Raw -ErrorAction SilentlyContinue
    if ([string]::IsNullOrWhiteSpace($content)) {
        return @{ Errors = -1; Warnings = -1; Parseable = $false }
    }
    $errors = -1
    $warnings = -1
    # STRICT: require the exact "ERC messages: N Errors N Warnings N" line.
    # If the line is missing or truncated, the report is not reliably interpretable.
    if ($content -match "ERC messages:\s*(?<m>\d+)\s*Errors\s*(?<e>\d+)\s*Warnings\s*(?<w>\d+)") {
        $errors = [int]$Matches['e']
        $warnings = [int]$Matches['w']
        return @{ Errors = $errors; Warnings = $warnings; Parseable = $true }
    }
    # Missing/unparseable count line -> not reliably interpretable -> FAIL
    return @{ Errors = -1; Warnings = -1; Parseable = $false }
}

# ---- Helper: parse DRC report for violation counts (STRICT) ----
function Parse-DrcReport {
    param([string] $Path)
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) {
        return @{ Violations = -1; Unconnected = -1; FootprintErrors = -1; Parseable = $false }
    }
    $content = Get-Content -LiteralPath $Path -Raw -ErrorAction SilentlyContinue
    if ([string]::IsNullOrWhiteSpace($content)) {
        return @{ Violations = -1; Unconnected = -1; FootprintErrors = -1; Parseable = $false }
    }
    $violations = -1
    $unconnected = -1
    $footprintErrors = -1
    # STRICT: require each violation-count line. A missing line means the report
    # is truncated or malformed and must not be treated as clean.
    if ($content -match "Found\s+(?<v>\d+)\s+DRC violations") {
        $violations = [int]$Matches['v']
    }
    if ($content -match "Found\s+(?<u>\d+)\s+unconnected pads") {
        $unconnected = [int]$Matches['u']
    }
    if ($content -match "Found\s+(?<f>\d+)\s+Footprint errors") {
        $footprintErrors = [int]$Matches['f']
    }
    # All three count lines must be present for the report to be reliable.
    if ($violations -eq -1 -or $unconnected -eq -1 -or $footprintErrors -eq -1) {
        return @{ Violations = -1; Unconnected = -1; FootprintErrors = -1; Parseable = $false }
    }
    return @{ Violations = $violations; Unconnected = $unconnected; FootprintErrors = $footprintErrors; Parseable = $true }
}

# ---- Helper: detect empty schematic (no components, no nets, no pins) ----
function Test-EmptySchematic {
    param([string] $Path)
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $true
    }
    $content = Get-Content -LiteralPath $Path -Raw -ErrorAction SilentlyContinue
    if ([string]::IsNullOrWhiteSpace($content)) {
        return $true
    }
    if ($content -match '\(symbol ') {
        return $false
    }
    if ($content -match '\(net ') {
        return $false
    }
    return $true
}

# ---- Helper: detect PCB without valid Edge.Cuts outline ----
function Test-PcbMissingOutline {
    param([string] $Path)
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $true
    }
    $content = Get-Content -LiteralPath $Path -Raw -ErrorAction SilentlyContinue
    if ([string]::IsNullOrWhiteSpace($content)) {
        return $true
    }
    if ($content -match 'Edge\.Cuts') {
        if ($content -match '(?s)(\(gr_line[\s\S]*?Edge\.Cuts|\(gr_arc[\s\S]*?Edge\.Cuts|\(gr_circle[\s\S]*?Edge\.Cuts|\(gr_poly[\s\S]*?Edge\.Cuts|\(fp_line[\s\S]*?Edge\.Cuts)') {
            return $false
        }
        return $true  # Edge.Cuts referenced but no geometry
    }
    return $true  # No Edge.Cuts layer at all
}

# ---- Pre-check: detect incomplete design ----
Write-Status "Checking design completeness..."

$emptySch = Test-EmptySchematic -Path $schFile
$missingOutline = Test-PcbMissingOutline -Path $pcbFile

$incomplete = $false
if ($emptySch) {
    $script:failures += "INCOMPLETE: Schematic is empty (no symbols or nets found). ERC passes trivially on a blank schematic."
    Write-Status "Schematic is empty" "INCOMPLETE"
    $incomplete = $true
} else {
    Write-Status "Schematic contains content" "PASS"
}

if ($missingOutline) {
    $script:failures += "INCOMPLETE: PCB has no valid Edge.Cuts outline. Board cannot be fabricated."
    Write-Status "PCB missing Edge.Cuts outline" "INCOMPLETE"
    $incomplete = $true
} else {
    Write-Status "PCB has Edge.Cuts outline" "PASS"
}

# ---- 1. Schematic ERC ----
Write-Status "Running schematic ERC on: $schFile"
# Format fixed to "report" text to avoid format/extension mismatch.
$ercArgs = @("sch", "erc", $schFile, "-o", $ercReport, "--format", "report", "--units", $ErcUnits, "--exit-code-violations")
if ($ErcSeverityAll) { $ercArgs += "--severity-all" }
if ($ErcSeverityError) { $ercArgs += "--severity-error" }
if ($ErcSeverityWarning) { $ercArgs += "--severity-warning" }
if ($ErcSeverityExclusions) { $ercArgs += "--severity-exclusions" }

$ercCliExitCode = -1
$ercCliRan = $false
if (!(Test-Path -LiteralPath $KicadCli -PathType Leaf)) {
    $script:failures += "KiCad CLI not found at: $KicadCli"
    Write-Status "KiCad CLI not found" "FAIL"
} else {
    & $KicadCli @ercArgs 2>$null | Out-Null
    $ercCliExitCode = $LASTEXITCODE
    $ercCliRan = $true
}

# Parse the actual ERC report regardless of exit code (STRICT)
$ercParsed = Parse-ErcReport -Path $ercReport
$ercHasViolations = $false
if (-not $ercParsed.Parseable) {
    $script:failures += "ERC report is missing, truncated, or malformed: $ercReport"
    Write-Status "ERC report not reliably interpretable" "FAIL"
    $ercHasViolations = $true
} elseif ($ercParsed.Errors -gt 0 -or $ercParsed.Warnings -gt 0) {
    $ercHasViolations = $true
    $script:failures += "ERC reported $($ercParsed.Errors) error(s), $($ercParsed.Warnings) warning(s)"
    Write-Status "ERC reported violations (E=$($ercParsed.Errors) W=$($ercParsed.Warnings))" "FAIL"
} else {
    Write-Status "ERC report: 0 errors, 0 warnings" "PASS"
}

if (-not $ercCliRan) {
    $script:failures += "Schematic ERC CLI did not execute"
    Write-Status "Schematic ERC CLI did not execute" "FAIL"
} else {
    Write-Status "Schematic ERC CLI ran (exit $ercCliExitCode)" "INFO"
}

$script:checksRun += @{ Name = "schematic ERC"; CliRan = $ercCliRan; CliExitCode = $ercCliExitCode; Parsed = $ercParsed; HasViolations = $ercHasViolations; Report = $ercReport }

Write-Host ("  ERC report: {0}" -f $ercReport)

# ---- 2. PCB DRC ----
Write-Status "Running PCB DRC on: $pcbFile"
$drcArgs = @("pcb", "drc", $pcbFile, "-o", $drcReport, "--exit-code-violations")

$drcCliExitCode = -1
$drcCliRan = $false
if (!(Test-Path -LiteralPath $KicadCli -PathType Leaf)) {
    $script:failures += "KiCad CLI not found at: $KicadCli"
    Write-Status "KiCad CLI not found" "FAIL"
} else {
    & $KicadCli @drcArgs 2>$null | Out-Null
    $drcCliExitCode = $LASTEXITCODE
    $drcCliRan = $true
}

# Parse the actual DRC report regardless of exit code (STRICT)
$drcParsed = Parse-DrcReport -Path $drcReport
$drcHasViolations = $false
if (-not $drcParsed.Parseable) {
    $script:failures += "DRC report is missing, truncated, or malformed: $drcReport"
    Write-Status "DRC report not reliably interpretable" "FAIL"
    $drcHasViolations = $true
} elseif ($drcParsed.Violations -gt 0 -or $drcParsed.Unconnected -gt 0 -or $drcParsed.FootprintErrors -gt 0) {
    $drcHasViolations = $true
    $script:failures += "DRC reported $($drcParsed.Violations) violation(s), $($drcParsed.Unconnected) unconnected pad(s), $($drcParsed.FootprintErrors) footprint error(s)"
    Write-Status "DRC reported violations (V=$($drcParsed.Violations) U=$($drcParsed.Unconnected) F=$($drcParsed.FootprintErrors))" "FAIL"
} else {
    Write-Status "DRC report: 0 violations, 0 unconnected, 0 footprint errors" "PASS"
}

if (-not $drcCliRan) {
    $script:failures += "PCB DRC CLI did not execute"
    Write-Status "PCB DRC CLI did not execute" "FAIL"
} else {
    Write-Status "PCB DRC CLI ran (exit $drcCliExitCode)" "INFO"
}

$script:checksRun += @{ Name = "PCB DRC"; CliRan = $drcCliRan; CliExitCode = $drcCliExitCode; Parsed = $drcParsed; HasViolations = $drcHasViolations; Report = $drcReport }

Write-Host ("  DRC report: {0}" -f $drcReport)

# ---- Summary ----
Write-Host ""
Write-Host "========================================"
Write-Host " DESIGN-RULE CHECK SUMMARY"
Write-Host "========================================"
foreach ($c in $script:checksRun) {
    $cliStatus = if ($c.CliRan) { "CLI ran (exit $($c.CliExitCode))" } else { "CLI did not run" }
    $violStatus = if ($c.HasViolations) { "VIOLATIONS" } else { "NO VIOLATIONS" }
    Write-Host ("  {0,-20} : {1}, {2}" -f $c.Name, $cliStatus, $violStatus)
    Write-Host ("                 report: {0}" -f $c.Report)
}
Write-Host ""

# Final determination: PASS only if both CLIs ran, both reports parsed cleanly,
# both report zero violations, and the design is complete.
# CLI exit code is reported for information but the report content is authoritative.
$allCliRan = ($script:checksRun | Where-Object { -not $_.CliRan }).Count -eq 0
$allParsed = ($script:checksRun | Where-Object { -not $_.Parsed }).Count -eq 0
$noViolations = ($script:checksRun | Where-Object { $_.HasViolations }).Count -eq 0
$designComplete = -not $incomplete

if ($script:failures.Count -gt 0 -or -not $allCliRan -or -not $allParsed -or -not $noViolations -or -not $designComplete) {
    Write-Status "VALIDATION NOT PASSED" "FAIL"
    Write-Host ""
    Write-Host "NOTE: These are design-rule checks only (ERC/DRC). They do NOT replace"
    Write-Host "hardware testing, functional validation, or manufacturability review."
    exit 1
}

Write-Status "ALL DESIGN-RULE CHECKS PASSED (no violations reported)" "PASS"
Write-Host ""
Write-Host "NOTE: A passing ERC/DRC means no design-rule violations were reported."
Write-Host "It does NOT mean the hardware has been tested or is functionally correct."
Write-Host "These are design-rule checks, not hardware validation."
exit 0
