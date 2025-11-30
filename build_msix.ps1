# An improved script to build the MSIX package for S-Mapper
# Optional variant parameter: full, lite, or both
param(
    [ValidateSet('full','lite','both')]
    [string]$Variant = 'both',
    [switch]$Parallel,        # Build PyInstaller variants in parallel
    [switch]$ForceRebuild     # Rebuild even if a dist artifact exists
)

# --- Configuration ---
$AppName = "S-Mapper"
$AppVersion = "1.0.0.0" # Make sure this matches the version in AppxManifest.xml
$Publisher = "CN=5A473FF8-33D6-4030-AE98-405496883EF4" # From your product identity
$PackageName = "JafsWorks.Stoffi-S-Mapper" # Base package identity used for full build
$PackageNameLite = "$PackageName.Lite"

# --- Paths ---
$ScriptPath = $PSScriptRoot
$VenvPath = Join-Path -Path $ScriptPath -ChildPath ".venv"
$PythonExe = Join-Path -Path $VenvPath -ChildPath "Scripts\python.exe"
$BuildPath = Join-Path -Path $ScriptPath -ChildPath "build"
$AppxPath = Join-Path -Path $BuildPath -ChildPath "appx"
$InstallerPath = Join-Path -Path $ScriptPath -ChildPath "installer"

# --- Helper Functions ---
function Find-MakeAppx {
    $programFiles = ${env:ProgramFiles(x86)}
    $sdkPath = (Get-ChildItem -Path "$programFiles\Windows Kits\10\bin" -Recurse -Filter "makeappx.exe").FullName | Select-Object -Last 1
    if (-not $sdkPath) {
        Write-Host "makeappx.exe not found. Please ensure the Windows SDK is installed." -ForegroundColor Red
        exit 1
    }
    return $sdkPath
}

function ReEncode-Manifest {
    param ([string]$FilePath)
    $content = Get-Content -Path $FilePath -Raw
    [System.IO.File]::WriteAllText($FilePath, $content, [System.Text.UTF8Encoding]::new($false))
}

# Optional variant parameter: full, lite, or both

# Allow overriding the variant with an environment variable (useful when
# calling the script in contexts where parameters don't bind properly).
if ($env:BUILD_VARIANT) {
    $ev = $env:BUILD_VARIANT.ToLower()
    if ($ev -in @('full','lite','both')) {
        Write-Host "BUILD_VARIANT environment variable detected: $ev (overrides parameter)" -ForegroundColor Yellow
        $Variant = $ev
    }
}

# --- Main Logic ---
# 1. Check for dependencies
if (-not (Test-Path -Path $PythonExe)) {
    Write-Host "Python virtual environment not found at $VenvPath. Please create it first." -ForegroundColor Red
    exit 1
}

# Check for pyinstaller
$pyInstallerPath = Join-Path -Path $VenvPath -ChildPath "Scripts\pyinstaller.exe"
if (-not (Test-Path -Path $pyInstallerPath)) {
    Write-Host "pyinstaller not found in the virtual environment. Please run: pip install pyinstaller" -ForegroundColor Red
    exit 1
}

$makeAppxPath = Find-MakeAppx

# 2. Clean up previous build
if (Test-Path -Path $BuildPath) {
    Remove-Item -Path $BuildPath -Recurse -Force
}
if (-not (Test-Path -Path $InstallerPath)) {
    New-Item -Path $InstallerPath -ItemType Directory
}
New-Item -Path $BuildPath -ItemType Directory
New-Item -Path $AppxPath -ItemType Directory

## Start timer so we can measure elapsed build time
$sw = [Diagnostics.Stopwatch]::StartNew()

# 3. Build executables depending on the desired variant
function ShouldBuildExe {
    param([string]$exeName)
    if ($ForceRebuild) { return $true }
    $target = Join-Path -Path $ScriptPath -ChildPath (Join-Path 'dist' $exeName)
    return (-not (Test-Path -Path $target))
}

$procs = @()
if ($Variant -eq 'full' -or $Variant -eq 'both') {
    if (ShouldBuildExe 's_mapper_full.exe') {
        Write-Host "Building full variant (includes keyboard if present in venv)" -ForegroundColor Cyan
        $fullArgs = @('--noconfirm','--onefile','--windowed','--name','s_mapper_full','--icon','assets\Square150x150Logo.png','--add-data','assets;assets','s_mapper\app.py')
        if ($Parallel.IsPresent -and ($Variant -eq 'both')) {
            $p = Start-Process -FilePath $pyInstallerPath -ArgumentList $fullArgs -PassThru
            $procs += $p
        } else {
            $p = Start-Process -FilePath $pyInstallerPath -ArgumentList $fullArgs -NoNewWindow -Wait -PassThru
            if ($p.ExitCode -ne 0) { Write-Host "PyInstaller failed to build full variant" -ForegroundColor Red; exit 1 }
        }
    } else {
        Write-Host "Skipping full variant - dist/s_mapper_full.exe already exists (use -ForceRebuild to override)" -ForegroundColor Yellow
    }
}

if ($Variant -eq 'lite' -or $Variant -eq 'both') {
    if (ShouldBuildExe 's_mapper_lite.exe') {
        Write-Host "Building lite variant (explicitly excludes 'keyboard' to avoid low-level suppression dependency)" -ForegroundColor Cyan
        $liteArgs = @('--noconfirm','--onefile','--windowed','--name','s_mapper_lite','--icon','assets\Square150x150Logo.png','--add-data','assets;assets','--exclude-module','keyboard','s_mapper\app.py')
        if ($Parallel.IsPresent -and ($Variant -eq 'both')) {
            $p = Start-Process -FilePath $pyInstallerPath -ArgumentList $liteArgs -PassThru
            $procs += $p
        } else {
            $p = Start-Process -FilePath $pyInstallerPath -ArgumentList $liteArgs -NoNewWindow -Wait -PassThru
            if ($p.ExitCode -ne 0) { Write-Host "PyInstaller failed to build lite variant" -ForegroundColor Red; exit 1 }
        }
    } else {
        Write-Host "Skipping lite variant - dist/s_mapper_lite.exe already exists (use -ForceRebuild to override)" -ForegroundColor Yellow
    }
}

# If we launched parallel processes, wait for them and check status
if ($procs.Count -gt 0) {
    $ids = $procs | ForEach-Object { $_.Id }
    Wait-Process -Id $ids
    foreach ($p in $procs) {
        # refresh process info
        $p.Refresh()
        if ($p.ExitCode -ne 0) { Write-Host "One of the parallel builds failed (exit $($p.ExitCode))" -ForegroundColor Red; exit 1 }
    }
}

# 4. Clean and re-encode the AppxManifest.xml to be safe
$ManifestPath = Join-Path -Path $ScriptPath -ChildPath "AppxManifest.xml"

# Helper: prepare a cleaned copy of the manifest in the provided folder
function Prepare-ManifestCopy {
    param([string]$DestinationFolder, [string]$Variant)

    $destManifest = Join-Path -Path $DestinationFolder -ChildPath "AppxManifest.xml"
    $content = (Get-Content -Path $ManifestPath -Raw).TrimStart()

    if ($Variant -eq 'lite') {
        # For the lite variant we produce a simplified manifest that does not
        # request the restricted 'runFullTrust' capability and removes the
        # Windows startupTask extension. The user may still need to adjust the
        # manifest based on their packaging requirements.

        # For the lite variant we keep runFullTrust (most desktop-apex packaged
        # apps need it because the application is a FullTrust app). But we
        # remove the windows.startupTask extension to avoid auto-start behavior
        # in the lite variant. This keeps the manifest schema valid.

        # remove startupTask extension block conservatively
        $content = [regex]::Replace($content, '<desktop:Extension Category="windows.startupTask".*?<\/desktop:Extension>', '', 'Singleline')

        # change Identity name so the Lite package uses a different identity
        $nameRegex = [regex] 'Name="([^"]+)"'
        $content = $nameRegex.Replace($content, 'Name="' + $PackageNameLite + '"', 1)
    }

    # Always write without BOM
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($destManifest, $content, $utf8NoBom)
}

# 5. Copy the executable and assets to the appx folder
# 5. Build two variants using PyInstaller

# NOTE: the PyInstaller calls were already executed above (depending on $Variant).
# This section used to build binaries again unconditionally and caused the build
# to run twice. Those duplicate invocations have been removed to avoid extra time.

# 6. Create separate appx folders for full + lite and copy required files
$AppxFull = Join-Path -Path $AppxPath -ChildPath "full"
$AppxLite = Join-Path -Path $AppxPath -ChildPath "lite"
# Create appx directories and copy executables/assets only for requested variants
if ($Variant -eq 'full' -or $Variant -eq 'both') {
    New-Item -Path $AppxFull -ItemType Directory -Force | Out-Null
    # Copy full executable + assets. The manifest expects the executable to be
    # named "s_mapper.exe" so we copy into that filename to keep the manifest
    # consistent.
    Copy-Item -Path "dist\s_mapper_full.exe" -Destination (Join-Path -Path $AppxFull -ChildPath 's_mapper.exe')
    Copy-Item -Path "assets" -Destination $AppxFull -Recurse
    Prepare-ManifestCopy -DestinationFolder $AppxFull -Variant 'full'
}

if ($Variant -eq 'lite' -or $Variant -eq 'both') {
    New-Item -Path $AppxLite -ItemType Directory -Force | Out-Null
    Copy-Item -Path "dist\s_mapper_lite.exe" -Destination (Join-Path -Path $AppxLite -ChildPath 's_mapper.exe')
    Copy-Item -Path "assets" -Destination $AppxLite -Recurse
    Prepare-ManifestCopy -DestinationFolder $AppxLite -Variant 'lite'
}

# 7. Create the MSIX packages
if ($Variant -eq 'full' -or $Variant -eq 'both') {
    Write-Host "Creating full MSIX" -ForegroundColor Cyan
    & $makeAppxPath pack /d $AppxFull /p "$InstallerPath\$PackageName-full.msix" /o
    if ($LASTEXITCODE -ne 0) { Write-Host "makeappx failed for full" -ForegroundColor Red; exit 1 }
}

if ($Variant -eq 'lite' -or $Variant -eq 'both') {
    Write-Host "Creating lite MSIX" -ForegroundColor Cyan
    & $makeAppxPath pack /d $AppxLite /p "$InstallerPath\$PackageName-lite.msix" /o
    if ($LASTEXITCODE -ne 0) { Write-Host "makeappx failed for lite" -ForegroundColor Red; exit 1 }
}

# 7. Sign the MSIX package (optional but recommended for local testing)
# You may need to create a self-signed certificate for this.
# Example:
# signtool sign /a /fd SHA256 /f "my_certificate.pfx" /p "my_password" "$InstallerPath\$PackageName.msix"

Write-Host "MSIX packages built (variant: $Variant). See $InstallerPath" -ForegroundColor Green
$sw.Stop()
Write-Host "Total build time: $($sw.Elapsed.TotalSeconds) seconds" -ForegroundColor Green