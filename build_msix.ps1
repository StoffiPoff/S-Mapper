# An improved script to build the MSIX package for S-Mapper

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

# 3. Run PyInstaller to create the executable
& $pyInstallerPath --noconfirm --onefile --windowed --icon "icon.png" "s_mapper.py"
if ($LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller failed to build the executable. See the log above for details." -ForegroundColor Red
    exit 1
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

Write-Host "Building full variant (includes keyboard if present in venv)" -ForegroundColor Cyan
& $pyInstallerPath --noconfirm --onefile --windowed --name s_mapper_full --icon "icon.png" "s_mapper.py"
if ($LASTEXITCODE -ne 0) { Write-Host "PyInstaller failed to build full variant" -ForegroundColor Red; exit 1 }

Write-Host "Building lite variant (explicitly excludes 'keyboard' to avoid low-level suppression dependency)" -ForegroundColor Cyan
& $pyInstallerPath --noconfirm --onefile --windowed --name s_mapper_lite --icon "icon.png" --exclude-module keyboard "s_mapper.py"
if ($LASTEXITCODE -ne 0) { Write-Host "PyInstaller failed to build lite variant" -ForegroundColor Red; exit 1 }

# 6. Create separate appx folders for full + lite and copy required files
$AppxFull = Join-Path -Path $AppxPath -ChildPath "full"
$AppxLite = Join-Path -Path $AppxPath -ChildPath "lite"
New-Item -Path $AppxFull -ItemType Directory -Force | Out-Null
New-Item -Path $AppxLite -ItemType Directory -Force | Out-Null

# Copy full executable + assets. The manifest expects the executable to be
# named "s_mapper.exe" so we copy into that filename to keep the manifest
# consistent.
Copy-Item -Path "dist\s_mapper_full.exe" -Destination (Join-Path -Path $AppxFull -ChildPath 's_mapper.exe')
Copy-Item -Path "assets" -Destination $AppxFull -Recurse

# Copy lite executable + assets. Also copy the lite exe to s_mapper.exe so
# the manifest's Executable attribute matches the file inside the package.
Copy-Item -Path "dist\s_mapper_lite.exe" -Destination (Join-Path -Path $AppxLite -ChildPath 's_mapper.exe')
Copy-Item -Path "assets" -Destination $AppxLite -Recurse

# Prepare manifests
Prepare-ManifestCopy -DestinationFolder $AppxFull -Variant 'full'
Prepare-ManifestCopy -DestinationFolder $AppxLite -Variant 'lite'

# 7. Create the MSIX packages
Write-Host "Creating full MSIX" -ForegroundColor Cyan
& $makeAppxPath pack /d $AppxFull /p "$InstallerPath\$PackageName-full.msix" /o
if ($LASTEXITCODE -ne 0) { Write-Host "makeappx failed for full" -ForegroundColor Red; exit 1 }

Write-Host "Creating lite MSIX" -ForegroundColor Cyan
& $makeAppxPath pack /d $AppxLite /p "$InstallerPath\$PackageName-lite.msix" /o
if ($LASTEXITCODE -ne 0) { Write-Host "makeappx failed for lite" -ForegroundColor Red; exit 1 }

# 7. Sign the MSIX package (optional but recommended for local testing)
# You may need to create a self-signed certificate for this.
# Example:
# signtool sign /a /fd SHA256 /f "my_certificate.pfx" /p "my_password" "$InstallerPath\$PackageName.msix"

Write-Host "MSIX package created at $InstallerPath\$PackageName.msix" -ForegroundColor Green