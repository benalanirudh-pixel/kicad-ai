<#
.SYNOPSIS
    Verify the automation environment before running any KiCad CLI commands.

.DESCRIPTION
    Checks that:
      * The KiCad 10.0 CLI executable exists at the verified path.
      * The ESP32_BME280 project files exist.
      * The CLI reports a usable version.

    This script only inspects files and runs `kicad-cli --version`. It never
    modifies the schematic, PCB, or project settings, and it never touches the
    lock file.

.PARAMETER ProjectDir
    Absolute path to the ESP32_BME280 project directory.

.PARAMETER KicadCli
    Absolute path to the kicad-cli.exe executable.

.EXAMPLE
    .\scripts\check_environment.ps1 -ProjectDir "C:\Users\Anirudh\OneDrive\Documents\kicad ai\ESP32_BME280" -KicadCli "C:\Users\Anirudh\AppData\Local\Programs\KiCad\10.0\bin\kicad-cli.exe"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $ProjectDir,

    [Parameter(Mandatory = $true)]
    [string] $KicadCli
)

$ErrorActionPreference = 'Stop'

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

try {
    Write-Status "Checking KiCad CLI executable: $KicadCli"
    if (!(Test-Path -LiteralPath $KicadCli -PathType Leaf)) {
        $failures += "KiCad CLI not found at: $KicadCli"
        Write-Status "KiCad CLI not found" "FAIL"
    } else {
        Write-Status "KiCad CLI found" "PASS"
    }

    Write-Status "Checking project directory: $ProjectDir"
    if (!(Test-Path -LiteralPath $ProjectDir -PathType Container)) {
        $failures += "Project directory not found: $ProjectDir"
        Write-Status "Project directory not found" "FAIL"
    } else {
        Write-Status "Project directory found" "PASS"
    }

    $requiredFiles = @(
        "ESP32_BME280.kicad_pro",
        "ESP32_BME280.kicad_sch",
        "ESP32_BME280.kicad_pcb"
    )

    foreach ($file in $requiredFiles) {
        $fullPath = Join-Path -Path $ProjectDir -ChildPath $file
        Write-Status "Checking project file: $file"
        if (!(Test-Path -LiteralPath $fullPath -PathType Leaf)) {
            $failures += "Missing project file: $fullPath"
            Write-Status "Missing: $file" "FAIL"
        } else {
            Write-Status "Present: $file" "PASS"
        }
    }

    $lockFile = Join-Path -Path $ProjectDir -ChildPath "~ESP32_BME280.kicad_pro.lck"
    if (Test-Path -LiteralPath $lockFile -PathType Leaf) {
        Write-Status "Lock file present - KiCad may have the project open. Do not delete it." "WARN"
    }

    if (Test-Path -LiteralPath $KicadCli -PathType Leaf) {
        Write-Status "Running kicad-cli --version"
        try {
            $versionOutput = & $KicadCli --version 2>&1
            $exitCode = $LASTEXITCODE
            if ($exitCode -eq 0) {
                Write-Status "CLI version: $versionOutput" "PASS"
            } else {
                $failures += "kicad-cli --version exited with code $exitCode"
                Write-Status "CLI version check failed (exit $exitCode)" "FAIL"
            }
        } catch {
            $failures += "Failed to invoke kicad-cli: $($_.Exception.Message)"
            Write-Status "CLI invocation failed" "FAIL"
        }
    }

    Write-Host ""
    if ($failures.Count -gt 0) {
        Write-Status "ENVIRONMENT CHECK FAILED" "FAIL"
        foreach ($f in $failures) {
            Write-Host ("  - {0}" -f $f)
        }
        exit 1
    } else {
        Write-Status "ENVIRONMENT CHECK PASSED" "PASS"
        exit 0
    }
} catch {
    Write-Status "Unexpected error: $($_.Exception.Message)" "FAIL"
    exit 1
}
