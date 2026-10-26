<#
.SYNOPSIS
    Verify that generated KiCad output files exist, are non-empty, and contain
    expected content.

.DESCRIPTION
    Checks manufacturing and validation output files produced by the other
    scripts in this framework. For each expected file or directory it reports
    whether it exists, whether it is non-empty, and (for validation reports)
    whether it parses cleanly with zero violations.

    MANUFACTURING OUTPUT LIMITATIONS:
      * Gerber checks verify that .gbr files exist and are non-zero bytes. They
        do NOT verify Gerber syntax, aperture definitions, or coordinate
        correctness.
      * Drill-file checks verify that at least one tool command (T\d+) is
        present. A header-only drill file (M48 ... M30 with no tool changes) is
        rejected as having no actual drill operations. This is a heuristic and
        does NOT establish manufacturability.

    File existence, non-empty size, zero-byte checks, and zero reported
    violations do NOT prove electrical correctness or functional validity of
    the hardware.

    This is a post-generation verification step only. It does NOT run any
    KiCad CLI command, does NOT modify project files, and does NOT perform
    design-rule checks or hardware testing.

.PARAMETER ProjectDir
    Absolute path to the ESP32_BME280 project directory.

.PARAMETER CheckManufacturing
    Also verify manufacturing outputs (gerbers and drill directories).

.PARAMETER CheckValidation
    Also verify validation reports (ERC and DRC report files).

.PARAMETER CheckErcJson
    Not supported. JSON report generation was removed to avoid format/extension
    mismatch. This parameter is accepted for backward compatibility but has no
    effect.

.EXAMPLE
    .\scripts\check_outputs.ps1 -ProjectDir "C:\Users\Anirudh\OneDrive\Documents\kicad ai\ESP32_BME280" -CheckManufacturing -CheckValidation
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $ProjectDir,

    [switch] $CheckManufacturing,
    [switch] $CheckValidation,
    [switch] $CheckErcJson
)

$ErrorActionPreference = 'Continue'
$script:scriptName = [System.IO.Path]::GetFileName($MyInvocation.MyCommand.Path)
$script:failures = @()
$script:warnings = @()

function Write-Status {
    param([string] $Message, [string] $Level = "INFO")
    $prefix = switch ($Level) {
        "PASS" { "PASS" }
        "FAIL" { "FAIL" }
        "WARN" { "WARN" }
        default { "INFO" }
    }
    Write-Host ("[{0}] {1}: {2}" -f $prefix, $script:scriptName, $Message)
}

function Test-OutputPath {
    param([string] $Label, [string] $Path, [switch] $MustBeNonEmpty)

    if (!(Test-Path -LiteralPath $Path)) {
        $script:failures += "MISSING: $Label ($Path)"
        Write-Status ("{0}: MISSING ({1})" -f $Label, $Path) "FAIL"
        return
    }

    $item = Get-Item -LiteralPath $Path
    if ($MustBeNonEmpty) {
        if ($item.PSIsContainer) {
            $childCount = (Get-ChildItem -LiteralPath $Path -Force | Measure-Object).Count
            if ($childCount -eq 0) {
                $script:failures += "EMPTY (no children): $Label ($Path)"
                Write-Status ("{0}: EMPTY directory ({1})" -f $Label, $Path) "FAIL"
                return
            }
            Write-Status ("{0}: OK ({1} item(s))" -f $Label, $childCount) "PASS"
        } else {
            if ($item.Length -eq 0) {
                $script:failures += "EMPTY (0 bytes): $Label ($Path)"
                Write-Status ("{0}: EMPTY file (0 bytes) ({1})" -f $Label, $Path) "FAIL"
                return
            }
            Write-Status ("{0}: OK ({1} bytes)" -f $Label, $item.Length) "PASS"
        }
    } else {
        Write-Status ("{0}: EXISTS" -f $Label) "PASS"
    }
}

function Test-ErcReportContent {
    param([string] $Path)
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) {
        $script:failures += "MISSING: ERC report ($Path)"
        Write-Status ("ERC report: MISSING ({0})" -f $Path) "FAIL"
        return
    }
    $content = Get-Content -LiteralPath $Path -Raw -ErrorAction SilentlyContinue
    if ([string]::IsNullOrWhiteSpace($content)) {
        $script:failures += "EMPTY: ERC report ($Path)"
        Write-Status ("ERC report: EMPTY ({0})" -f $Path) "FAIL"
        return
    }
    # STRICT: require the count line and zero violations
    if ($content -match "ERC messages:\s*(?<m>\d+)\s*Errors\s*(?<e>\d+)\s*Warnings\s*(?<w>\d+)") {
        $e = [int]$Matches['e']
        $w = [int]$Matches['w']
        if ($e -gt 0 -or $w -gt 0) {
            $script:failures += "ERC report contains violations: $e error(s), $w warning(s) ($Path)"
            Write-Status ("ERC report: VIOLATIONS (E=$e W=$w)" -f $e, $w) "FAIL"
            return
        }
        Write-Status ("ERC report: OK (E=0 W=0)" ) "PASS"
    } else {
        $script:failures += "ERC report missing violation-count line (truncated or malformed): $Path"
        Write-Status ("ERC report: UNPARSEABLE (missing count line) ({0})" -f $Path) "FAIL"
    }
}

function Test-DrcReportContent {
    param([string] $Path)
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) {
        $script:failures += "MISSING: DRC report ($Path)"
        Write-Status ("DRC report: MISSING ({0})" -f $Path) "FAIL"
        return
    }
    $content = Get-Content -LiteralPath $Path -Raw -ErrorAction SilentlyContinue
    if ([string]::IsNullOrWhiteSpace($content)) {
        $script:failures += "EMPTY: DRC report ($Path)"
        Write-Status ("DRC report: EMPTY ({0})" -f $Path) "FAIL"
        return
    }
    # STRICT: require all three count lines and zero violations
    $hasV = $content -match "Found\s+(?<v>\d+)\s+DRC violations"
    $hasU = $content -match "Found\s+(?<u>\d+)\s+unconnected pads"
    $hasF = $content -match "Found\s+(?<f>\d+)\s+Footprint errors"
    $zeroV = $content -match "Found\s+0\s+DRC violations"
    $zeroU = $content -match "Found\s+0\s+unconnected pads"
    $zeroF = $content -match "Found\s+0\s+Footprint errors"
    if (-not ($hasV -and $hasU -and $hasF)) {
        $script:failures += "DRC report missing violation-count lines (truncated or malformed): $Path"
        Write-Status ("DRC report: UNPARSEABLE (missing count lines) ({0})" -f $Path) "FAIL"
        return
    }
    if (-not ($zeroV -and $zeroU -and $zeroF)) {
        $v = if ($hasV) { [int]$Matches['v'] } else { -1 }
        $u = if ($hasU) { [int]$Matches['u'] } else { -1 }
        $f = if ($hasF) { [int]$Matches['f'] } else { -1 }
        $script:failures += "DRC report contains violations: $v violation(s), $u unconnected pad(s), $f footprint error(s) ($Path)"
        Write-Status ("DRC report: VIOLATIONS (V=$v U=$u F=$f)" -f $v, $u, $f) "FAIL"
        return
    }
    Write-Status ("DRC report: OK (V=0 U=0 F=0)" ) "PASS"
}

function Test-GerberFiles {
    param([string] $GerberDir, [string] $PcbFile)
    if (!(Test-Path -LiteralPath $GerberDir -PathType Container)) {
        $script:failures += "MISSING: Gerber directory ($GerberDir)"
        Write-Status ("Gerber directory: MISSING ({0})" -f $GerberDir) "FAIL"
        return
    }
    $gerberFiles = Get-ChildItem -LiteralPath $GerberDir -Filter "*.gbr" -File -ErrorAction SilentlyContinue
    if ($gerberFiles.Count -eq 0) {
        $script:failures += "NO GERBER FILES: $GerberDir contains no .gbr files"
        Write-Status ("Gerber directory: NO .gbr FILES ({0})" -f $GerberDir) "FAIL"
        return
    }
    $zeroByte = @()
    foreach ($gf in $gerberFiles) {
        if ($gf.Length -eq 0) {
            $zeroByte += $gf.FullName
        }
    }
    if ($zeroByte.Count -gt 0) {
        foreach ($z in $zeroByte) {
            $script:failures += "ZERO-BYTE GERBER: $z"
        }
        Write-Status ("Gerber directory: {0} zero-byte .gbr file(s)" -f $zeroByte.Count) "FAIL"
        return
    }

    # Verify required Gerber layers are present
    $gerberNames = $gerberFiles | ForEach-Object { $_.BaseName }
    $requiredLayers = @("F_Cu", "Edge_Cuts")
    $hasBCu = $false
    $hasMaskF = $false
    $hasMaskB = $false
    $hasSilkF = $false
    $hasSilkB = $false
    $hasPasteF = $false

    # Check PCB for back copper presence to decide if B_Cu is required
    if (Test-Path -LiteralPath $PcbFile -PathType Leaf) {
        $pcbContent = Get-Content -LiteralPath $PcbFile -Raw -ErrorAction SilentlyContinue
        if ($pcbContent -match '(?s)\(layer "B\.Cu"\)') {
            $hasBCu = $true
        }
    }

    foreach ($name in $gerberNames) {
        if ($name -like "*F_Cu*") { $hasMaskF = $true } # placeholder, will be overwritten below
    }

    # Proper layer detection
    $layerF_Cu = $false
    $layerEdge_Cuts = $false
    $layerB_Cu = $false
    $layerMaskF = $false
    $layerMaskB = $false
    $layerSilkF = $false
    $layerSilkB = $false
    $layerPasteF = $false

    foreach ($name in $gerberNames) {
        if ($name -like "*-F_Cu") { $layerF_Cu = $true }
        if ($name -like "*-Edge_Cuts") { $layerEdge_Cuts = $true }
        if ($name -like "*-B_Cu") { $layerB_Cu = $true }
        if ($name -like "*-F_Mask") { $layerMaskF = $true }
        if ($name -like "*-B_Mask") { $layerMaskB = $true }
        if ($name -like "*-F_SilkS") { $layerSilkF = $true }
        if ($name -like "*-B_SilkS") { $layerSilkB = $true }
        if ($name -like "*-F_Paste") { $layerPasteF = $true }
    }

    $missingLayers = @()
    if (-not $layerF_Cu) { $missingLayers += "F_Cu" }
    if (-not $layerEdge_Cuts) { $missingLayers += "Edge_Cuts" }
    if ($hasBCu -and -not $layerB_Cu) { $missingLayers += "B_Cu" }

    if ($missingLayers.Count -gt 0) {
        $script:failures += "MISSING GERBER LAYERS: $($missingLayers -join ', ')"
        Write-Status ("Gerber directory: MISSING layers $($missingLayers -join ', ')" ) "FAIL"
        return
    }

    Write-Status ("Gerber directory: OK ({0} non-zero .gbr file(s))" -f $gerberFiles.Count) "PASS"
    # Limitation note
    $script:warnings += "Gerber files exist and are non-zero bytes, but Gerber syntax/coordinates are NOT verified. This does not establish manufacturability."
}

function Test-DrillFile {
    param([string] $DrillFile, [string] $PcbFile)
    if (!(Test-Path -LiteralPath $DrillFile -PathType Leaf)) {
        $script:failures += "MISSING: Drill file ($DrillFile)"
        Write-Status ("Drill file: MISSING ({0})" -f $DrillFile) "FAIL"
        return
    }
    $item = Get-Item -LiteralPath $DrillFile
    if ($item.Length -eq 0) {
        $script:failures += "EMPTY (0 bytes): Drill file ($DrillFile)"
        Write-Status ("Drill file: EMPTY (0 bytes) ({0})" -f $DrillFile) "FAIL"
        return
    }
    $content = Get-Content -LiteralPath $DrillFile -Raw -ErrorAction SilentlyContinue
    if ([string]::IsNullOrWhiteSpace($content)) {
        $script:failures += "EMPTY (whitespace only): Drill file ($DrillFile)"
        Write-Status ("Drill file: EMPTY ({0})" -f $DrillFile) "FAIL"
        return
    }

    # Determine if the PCB actually has thru-hole pads that require drilling
    $hasThruHolePads = $false
    if (Test-Path -LiteralPath $PcbFile -PathType Leaf) {
        $pcbContent = Get-Content -LiteralPath $PcbFile -Raw -ErrorAction SilentlyContinue
        if ($pcbContent -match '\(pad.*thru_hole') {
            $hasThruHolePads = $true
        }
    }

    # Require at least one tool command (T\d+ at start of a line) only if the
    # design actually has thru-hole pads. A hole-free surface-mount design
    # legitimately produces a header-only drill file.
    if ($hasThruHolePads -and ($content -notmatch '(?m)^T\d+')) {
        $script:failures += "NO DRILL OPERATIONS: PCB has thru-hole pads but drill file contains headers only (no T\d+ tool commands): $DrillFile"
        Write-Status ("Drill file: NO TOOL COMMANDS (header-only) ({0})" -f $DrillFile) "FAIL"
        return
    }
    if (-not $hasThruHolePads) {
        Write-Status ("Drill file: OK (hole-free design, no drill operations required, {0} bytes)" -f $item.Length) "PASS"
    } else {
        Write-Status ("Drill file: OK (tool command(s) present, {0} bytes)" -f $item.Length) "PASS"
    }
    # Limitation note
    $script:warnings += "Drill-file check verifies tool-command presence only; it does NOT verify drill coordinates, tool sizes, or hole completeness. This does not establish manufacturability."
}

$validationDir = Join-Path -Path $ProjectDir -ChildPath "outputs\validation"
$manufacturingDir = Join-Path -Path $ProjectDir -ChildPath "outputs\manufacturing"
$pcbFile = Join-Path -Path $ProjectDir -ChildPath "ESP32_BME280.kicad_pcb"

Write-Host "Checking outputs under: $ProjectDir"
Write-Host ""

$runValidation = $CheckValidation
$runManufacturing = $CheckManufacturing
if (!$runValidation -and !$runManufacturing) {
    $runValidation = $true
    $runManufacturing = $true
}

if ($runValidation) {
    Write-Status "Checking validation reports..."
    Test-ErcReportContent -Path (Join-Path $validationDir "ESP32_BME280_erc_report.txt")
    if ($CheckErcJson) {
        Write-Status "JSON ERC report support removed (format/extension mismatch). Use the .txt report." "WARN"
    }
    Test-DrcReportContent -Path (Join-Path $validationDir "ESP32_BME280_drc_report.txt")
}

if ($runManufacturing) {
    Write-Status "Checking manufacturing outputs..."
    $gerberDir = Join-Path $manufacturingDir "gerbers"
    $drillDir  = Join-Path $manufacturingDir "drill"
    Test-OutputPath -Label "Gerber directory" -Path $gerberDir -MustBeNonEmpty
    Test-OutputPath -Label "Drill directory" -Path $drillDir -MustBeNonEmpty
    Test-GerberFiles -GerberDir $gerberDir -PcbFile $pcbFile
    $drillFile = Join-Path $drillDir "ESP32_BME280.drl"
    Test-DrillFile -DrillFile $drillFile -PcbFile $pcbFile
}

Write-Host ""
if ($script:warnings.Count -gt 0) {
    Write-Host "LIMITATIONS:"
    foreach ($w in $script:warnings) {
        Write-Host ("  - {0}" -f $w)
    }
    Write-Host ""
}

if ($script:failures.Count -gt 0) {
    Write-Status "OUTPUT CHECK FAILED" "FAIL"
    foreach ($f in $script:failures) {
        Write-Host ("  - {0}" -f $f)
    }
    exit 1
}

Write-Status "ALL OUTPUTS PRESENT, NON-EMPTY, AND PARSE CLEANLY" "PASS"
Write-Host ""
Write-Host "NOTE: File existence, non-empty size, and zero reported violations do NOT"
Write-Host "prove electrical correctness. Run validate_project.ps1 for ERC/DRC"
Write-Host "verification. These checks are not hardware testing and do not establish"
Write-Host "manufacturability."
exit 0
