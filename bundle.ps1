$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $root 'src'
$packaging = Join-Path $source 'packaging'
$dest = Join-Path $root 'dist'
$app = Join-Path $dest 'app'
$scriptsDir = Join-Path $app 'scripts'
$destSrc = Join-Path $app 'src'
$launchers = @('Run.bat')
$scripts = @('setup.ps1')

$configPath = Join-Path $source 'config.py'
if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) { throw 'Missing src/config.py' }
$configText = Get-Content -LiteralPath $configPath -Raw
$versionMatch = [regex]::Match($configText, '(?m)^\s*VERSION\s*=\s*["''](?<version>[0-9A-Za-z][0-9A-Za-z._-]*)["'']')
if (-not $versionMatch.Success) { throw 'Could not find VERSION = "..." in src/config.py' }
$version = $versionMatch.Groups['version'].Value
$zipPath = Join-Path $root "blazingautomation-$version.zip"

if (-not (Test-Path -LiteralPath (Join-Path $source 'main.py') -PathType Leaf)) { throw 'Missing src/main.py' }
foreach ($name in $scripts) {
    if (-not (Test-Path -LiteralPath (Join-Path $packaging "scripts\$name") -PathType Leaf)) { throw "Missing src/packaging/scripts/$name" }
}
foreach ($name in $launchers) {
    if (-not (Test-Path -LiteralPath (Join-Path $packaging "launchers\$name") -PathType Leaf)) { throw "Missing src/packaging/launchers/$name" }
}

New-Item -ItemType Directory -Force -Path $dest, $app, $scriptsDir | Out-Null
if (Test-Path -LiteralPath $destSrc) { Remove-Item -LiteralPath $destSrc -Recurse -Force }
New-Item -ItemType Directory -Force -Path $destSrc | Out-Null
Get-ChildItem -LiteralPath $source -Force | Where-Object { $_.Name -notin @('packaging', '__pycache__') } | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $destSrc -Recurse -Force
}
Get-ChildItem -LiteralPath $destSrc -Directory -Recurse -Filter '__pycache__' | Remove-Item -Recurse -Force
# drop scripts from older builds so they are not shipped by accident
Get-ChildItem -LiteralPath $scriptsDir -File | Where-Object { $_.Name -notin $scripts } | Remove-Item -Force
foreach ($name in $scripts) {
    Copy-Item -LiteralPath (Join-Path $packaging "scripts\$name") -Destination (Join-Path $scriptsDir $name) -Force
}
foreach ($name in $launchers) {
    Copy-Item -LiteralPath (Join-Path $packaging "launchers\$name") -Destination (Join-Path $dest $name) -Force
}
Write-Host "[BUILD] Installer prepared: $dest (version $version)" -ForegroundColor Green

$stage = Join-Path $root '.bundle-stage'
if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
try {
    New-Item -ItemType Directory -Force -Path (Join-Path $stage 'app') | Out-Null
    Copy-Item -LiteralPath $destSrc -Destination (Join-Path $stage 'app\src') -Recurse -Force
    Copy-Item -LiteralPath $scriptsDir -Destination (Join-Path $stage 'app\scripts') -Recurse -Force
    foreach ($name in $launchers) {
        Copy-Item -LiteralPath (Join-Path $dest $name) -Destination (Join-Path $stage $name) -Force
    }
    if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
    Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zipPath -CompressionLevel Optimal
    Write-Host "[ZIP] Created $zipPath" -ForegroundColor Green
} finally {
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
}

Write-Host ''
$choice = Read-Host 'Press Enter to launch Run.bat (or Q to quit)'
if ($choice.Trim().ToLower() -in @('q', 'quit')) { exit 0 }
& (Join-Path $dest 'Run.bat')
exit $LASTEXITCODE
