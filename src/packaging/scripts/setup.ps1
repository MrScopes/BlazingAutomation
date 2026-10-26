# Installer. Run.bat starts it when Blazing Automation is not installed yet.
# The Python menu also runs it:  -Force  reinstall tools and packages,  -Dev  add the optional developer packages.
param(
    [switch]$Force,
    [switch]$Dev
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
$env:PYTHONPATH = $root
$script = Join-Path $root 'src\main.py'
$venv = Join-Path $root '.venv'
$python = Join-Path $venv 'Scripts\python.exe'
$uv = Join-Path $root '.bootstrap\uv.exe'
$tools = Join-Path $root 'tools'
$models = Join-Path $root 'models'
$statePath = Join-Path $root '.setup.json'
$uvCache = Join-Path $root '.cache\uv'
$env:UV_CACHE_DIR = $uvCache
# stream uv installs without retaining its large wheel/archive cache
$env:UV_NO_CACHE = '1'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $root '.runtime\python'
$env:UV_PYTHON_PREFERENCE = 'only-managed'
$env:UV_LINK_MODE = 'copy'
$env:PATH = "$(Join-Path $tools 'scrcpy');$(Join-Path $tools 'adb');$(Join-Path $tools 'ffmpeg');$env:PATH"

function Invoke-Checked([string]$File, [string[]]$Arguments) {
    # native tools write progress and warnings to stderr. PowerShell must not
    # treat those as terminating exceptions; their exit code is authoritative
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $File @Arguments
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($code -ne 0) { throw "$File exited with code $code (arguments: $($Arguments -join ' '))" }
}

function Download-File([string]$Url, [string]$Output) {
    $parent = Split-Path -Parent $Output
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $temp = "$Output.partial"
    if (Test-Path $temp) { Remove-Item $temp -Force }
    Write-Host "[DOWNLOAD] $Url" -ForegroundColor Cyan
    Invoke-WebRequest -Uri $Url -OutFile $temp -MaximumRedirection 10
    Move-Item -LiteralPath $temp -Destination $Output -Force
}

function Ensure-Uv {
    if (Test-Path $uv) { return }
    $zip = Join-Path $root '.bootstrap\uv.zip'
    Download-File 'https://github.com/astral-sh/uv/releases/download/0.13.4/uv-x86_64-pc-windows-msvc.zip' $zip
    Expand-Archive -LiteralPath $zip -DestinationPath (Split-Path $uv -Parent) -Force
    Remove-Item $zip -Force
    if (-not (Test-Path $uv)) { throw 'uv.exe missing from downloaded archive.' }
}

function Ensure-Python {
    Ensure-Uv
    if (-not (Test-Path $python)) {
        Write-Host '[SETUP] Installing isolated Python 3.12.15' -ForegroundColor Cyan
        Invoke-Checked $uv @('venv', '--python', '3.12.15', '--python-preference', 'only-managed', $venv)
        if (-not (Test-Path $python)) { throw 'Python environment creation did not produce python.exe.' }
    }
}

function Test-Imports {
    if (-not (Test-Path $python)) { return $false }
    $code = "import cv2, numpy, mss, imageio_ffmpeg, rapidfuzz, onnxruntime; from rapidocr import RapidOCR"
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $python -c $code 2>$null
        $success = ($LASTEXITCODE -eq 0)
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    return $success
}

function Ensure-Packages([string]$Backend, [bool]$Reinstall = $false) {
    Ensure-Uv
    if ($Reinstall -or -not (Test-Imports)) {
        Write-Host '[SETUP] Installing RapidOCR + ONNX Runtime DirectML (CPU fallback)...' -ForegroundColor Cyan
        $reinstallArgs = if ($Reinstall) { @('--reinstall') } else { @() }
        Invoke-Checked $uv (@('pip', 'install', '--link-mode', 'copy') + $reinstallArgs + @('--python', $python, 'rapidocr', 'onnxruntime-directml', 'opencv-python-headless', 'numpy', 'mss', 'imageio-ffmpeg', 'rapidfuzz'))
    }
    if (-not (Test-Imports)) { throw 'ONNX OCR dependencies could not be imported.' }
    # both distributions provide onnxruntime; do not install the CPU wheel over DirectML
    $providerScript = Join-Path $root ".onnx-providers.py"
    try {
        Set-Content -LiteralPath $providerScript -Value "import onnxruntime as ort; print(ort.get_available_providers())" -Encoding UTF8
        $providers = & $python $providerScript
        if ($LASTEXITCODE -ne 0) { throw "Failed to query ONNX Runtime providers." }
    } finally {
        Remove-Item -LiteralPath $providerScript -Force -ErrorAction SilentlyContinue
    }
    if ($providers -notmatch 'DmlExecutionProvider') {
        Write-Host '[OCR] DirectML provider missing; repairing ONNX Runtime installation...' -ForegroundColor Yellow
        Invoke-Checked $uv @('pip', 'install', '--link-mode', 'copy', '--python', $python, '--reinstall-package', 'onnxruntime-directml', 'onnxruntime-directml')
    }
    if (-not (Test-Imports)) { throw 'ONNX OCR dependencies could not be imported.' }
    # remove old large inference stack only after the replacement is verified
    $old = & $uv pip list --python $python --format freeze
    if ($old -match '(?m)^easyocr==' -or $old -match '(?m)^torch==' -or $old -match '(?m)^torchvision==') {
        Write-Host '[CLEANUP] Removing legacy EasyOCR/PyTorch packages...' -ForegroundColor Cyan
        Invoke-Checked $uv @('pip', 'uninstall', '--python', $python, 'easyocr', 'torch', 'torchvision')
    }
    foreach ($name in @('craft_mlt_25k.pth', 'english_g2.pth')) {
        $legacy = Join-Path $models $name
        if (Test-Path -LiteralPath $legacy) { Remove-Item -LiteralPath $legacy -Force }
    }
}

function Ensure-Scrcpy {
    $scrcpyDir = Join-Path $tools 'scrcpy'
    $exe = Join-Path $scrcpyDir 'scrcpy.exe'
    $server = Join-Path $scrcpyDir 'scrcpy-server'
    if ((Test-Path $exe) -and (Test-Path $server) -and (Test-Path (Join-Path $scrcpyDir 'adb.exe'))) { return }
    $zip = Join-Path $root '.cache\scrcpy-win64-v4.1.zip'
    if (-not (Test-Path $zip)) { Download-File 'https://github.com/Genymobile/scrcpy/releases/download/v4.1/scrcpy-win64-v4.1.zip' $zip }
    $extract = Join-Path $root '.cache\scrcpy-extract'
    if (Test-Path $extract) { Remove-Item $extract -Recurse -Force }
    Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
    $found = Get-ChildItem $extract -Filter 'scrcpy.exe' -File -Recurse | Select-Object -First 1
    if (-not $found) { throw 'scrcpy.exe not found in release ZIP.' }
    New-Item -ItemType Directory -Force -Path $scrcpyDir | Out-Null
    Copy-Item -Path (Join-Path $found.DirectoryName '*') -Destination $scrcpyDir -Recurse -Force
    Remove-Item $extract -Recurse -Force
    if (-not ((Test-Path $exe) -and (Test-Path $server) -and (Test-Path (Join-Path $scrcpyDir 'adb.exe')))) { throw 'scrcpy installation incomplete.' }
}

function Ensure-FFmpeg {
    $ffmpegDir = Join-Path $tools 'ffmpeg'
    $target = Join-Path $ffmpegDir 'ffmpeg.exe'
    if (Test-Path $target) { return }
    New-Item -ItemType Directory -Force -Path $ffmpegDir | Out-Null
    $path = (& $python -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())' | Select-Object -Last 1).Trim()
    if (-not (Test-Path $path)) { throw 'imageio-ffmpeg executable not found.' }
    Copy-Item -LiteralPath $path -Destination $target -Force
}

function Ensure-Models {
    Write-Host "[OCR] Verifying RapidOCR..." -ForegroundColor Cyan
    $testScript = Join-Path $root ".rapidocr-check.py"
    $code = @(
        'import onnxruntime as ort'
        'from rapidocr import RapidOCR'
        'providers = ort.get_available_providers()'
        'print("ONNX providers:", providers)'
        'use_dml = "DmlExecutionProvider" in providers'
        'reader = RapidOCR(params={"EngineConfig.onnxruntime.use_dml": use_dml})'
        'print("RapidOCR initialized:", "DirectML" if use_dml else "CPU")'
    ) -join [Environment]::NewLine
    try {
        [System.IO.File]::WriteAllText($testScript, $code, [System.Text.UTF8Encoding]::new($false))
        & $python $testScript
        if ($LASTEXITCODE -ne 0) { throw "RapidOCR initialization failed." }
    } finally {
        Remove-Item -LiteralPath $testScript -Force -ErrorAction SilentlyContinue
    }
}

function Clear-InstallCache {
    Write-Host '[CLEANUP] Removing temporary installation files...' -ForegroundColor Cyan

    $cleanup = @(
        (Join-Path $root '.bootstrap')
        (Join-Path $root '.cache')
        (Join-Path $root '.rapidocr-check.py')
        (Join-Path $root '.onnx-providers.py')
    )

    foreach ($path in $cleanup) {
        if (-not (Test-Path -LiteralPath $path)) { continue }

        try {
            Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction Stop
            Write-Host "[CLEANUP] Removed $(Split-Path $path -Leaf)" -ForegroundColor DarkGray
        } catch {
            Write-Warning "Could not remove $path`: $($_.Exception.Message)"
        }
    }

    Write-Host '[CLEANUP] Finished.' -ForegroundColor Green
}

function Test-CoreSetup([string]$Backend) {
    if (-not ((Test-Path $script) -and (Test-Path $python) -and
        (Test-Path (Join-Path $tools 'scrcpy\scrcpy.exe')) -and
        (Test-Path (Join-Path $tools 'scrcpy\scrcpy-server')) -and
        (Test-Path (Join-Path $tools 'scrcpy\adb.exe')) -and
        (Test-Path (Join-Path $tools 'ffmpeg\ffmpeg.exe')))) { return $false }
    if (-not (Test-Imports)) { return $false }
    return $true
}

function Test-DevSetup {
    if (-not (Test-Path $python)) { return $false }
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $python -c 'import tkinter; from PIL import Image, ImageTk' 2>$null
        $success = ($LASTEXITCODE -eq 0)
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    return $success
}

function Ensure-DevPackages {
    if (Test-DevSetup) { return }
    Write-Host '[DEV] Installing optional developer dependencies...' -ForegroundColor Cyan
    Ensure-Uv
    Invoke-Checked $uv @('pip', 'install', '--link-mode', 'copy', '--python', $python, 'pillow')
    if (-not (Test-DevSetup)) {
        throw 'Developer setup requires Tkinter. The installed Python runtime does not provide tkinter; use a Python build with Tcl/Tk support.'
    }
}

function Read-State {
    if (-not (Test-Path $statePath)) { return $null }
    try { return Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json } catch { return $null }
}

function Save-State([string]$Backend, [string]$Profile) {
    @{ backend=$Backend; profile=$Profile; version=4 } | ConvertTo-Json |
        Set-Content -LiteralPath $statePath -Encoding UTF8
}

# ---------------------------------------------------------------- main

$installSucceeded = $false
$cancelled = $false

try {
    $backend = 'auto'

    if ($Dev) {
        if (-not (Test-Path $python)) { throw 'Install Blazing Automation first.' }
        Ensure-DevPackages
        Clear-InstallCache
        exit 0
    }

    if ($Force) {
        Write-Host ''
        Write-Host '[REINSTALL] Removing tools and saved setup...' -ForegroundColor Cyan
        foreach ($name in @('adb', 'scrcpy')) {
            Get-Process -Name $name -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        }
        foreach ($path in @($tools, $models, $statePath)) {
            if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Recurse -Force }
        }
    } else {
        $state = Read-State
        if ($state -and $state.version -eq 4 -and $state.backend -eq 'auto' -and (Test-CoreSetup $backend)) { exit 0 }

        Write-Host ''
        Write-Host '=== BLAZING AUTOMATION INSTALLER ===' -ForegroundColor Cyan
        Write-Host 'Installs to this folder. Nothing is permanent.' -ForegroundColor White
        Write-Host ''
        Write-Host 'Estimated download:   ~200 MB'
        Write-Host 'Installed size:       ~600 MB'
        Write-Host 'Recommended space:    1 GB free'
        Write-Host ''
        Write-Host 'Includes:'
        Write-Host '  - Python 3.12'
        Write-Host '  - RapidOCR + DirectML (CPU fallback)'
        Write-Host '  - scrcpy + ADB'
        Write-Host '  - FFmpeg'
        Write-Host '  - Automation + Developer tools'
        Write-Host ''

        while ($true) {
            $choice = (Read-Host 'Install Blazing Automation? [Y/n]').Trim().ToLowerInvariant()
            if ($choice -in @('', 'y', 'yes')) { break }
            if ($choice -in @('n', 'no')) {
                $cancelled = $true
                break
            }
            Write-Host 'Please enter Y or N.' -ForegroundColor Yellow
        }
    }

    if (-not $cancelled) {
        Write-Host ''
        Write-Host '[SETUP] Preparing installation...' -ForegroundColor Cyan

        Ensure-Python
        Ensure-Packages $backend $Force.IsPresent
        Ensure-Scrcpy
        Ensure-FFmpeg
        Ensure-Models
        Ensure-DevPackages

        if (-not (Test-CoreSetup $backend)) {
            throw 'Core setup verification failed. Check Python, OCR, scrcpy, and FFmpeg.'
        }

        Save-State $backend 'dev'
        $installSucceeded = $true
    }
} catch {
    Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    Write-Host $_.ScriptStackTrace -ForegroundColor DarkGray
} finally {
    if ($installSucceeded) {
        try {
            Clear-InstallCache
        } catch {
            Write-Warning "Cleanup could not finish: $($_.Exception.Message)"
        }
    }
}

if ($cancelled) {
    Write-Host '[SETUP] Installation cancelled.' -ForegroundColor Yellow
    exit 2
}

if (-not $installSucceeded) { exit 1 }

Write-Host ''
Write-Host 'Installation complete.' -ForegroundColor Green
if (-not $Force) { Start-Sleep -Seconds 2 }
exit 0
