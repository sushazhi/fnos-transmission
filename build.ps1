# build.ps1 - Transmission for fnOS Local Build
# Usage:
#   .\build.ps1                                 # Build with default version from manifest
#   .\build.ps1 -AppVersion 4.1.1               # Build with custom app version (output filename)
#   .\build.ps1 -TransmissionVersion 4.0.5      # Build with specific transmission daemon version
#   .\build.ps1 -Arch amd64                     # Build for amd64 (default: arm64)
#   .\build.ps1 -AppVersion 4.1.1 -TransmissionVersion 4.0.5  # Custom both
#   .\build.ps1 -ListVersions                    # List available transmission versions

param(
    [string]$AppVersion = "",
    [string]$TransmissionVersion = "",
    [string]$Arch = "arm64",
    [switch]$ListVersions
)

$ErrorActionPreference = "Stop"

# Validate architecture
if ($Arch -notin @("arm64", "amd64")) {
    Write-Host "ERROR: Unsupported architecture '$Arch'. Supported: arm64, amd64" -ForegroundColor Red
    exit 1
}

$PROJECT_DIR = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$MANIFEST_FILE = Join-Path $PROJECT_DIR "manifest"
$TRANSMISSION_RELEASES_URL = "https://api.github.com/repos/transmission/transmission/releases"

# Read version from manifest
$Version = ""
$lines = Get-Content $MANIFEST_FILE
foreach ($line in $lines) {
    if ($line -match "^version\s*=\s*(\S+)") {
        $Version = $matches[1].Trim()
        break
    }
}
if (-not $Version) {
    Write-Host "ERROR: Cannot read version from manifest" -ForegroundColor Red
    exit 1
}

$APP_VERSION = $Version

# Override app version if -AppVersion specified (without modifying manifest)
if ($AppVersion) {
    $APP_VERSION = $AppVersion
    Write-Host "  App version overridden to: $APP_VERSION" -ForegroundColor Yellow
}

# Extract transmission version (first 3 parts of APP_VERSION)
# e.g., 4.1.0.1 -> 4.1.0, 4.1.1 -> 4.1.1
$versionParts = $APP_VERSION -split '\.'
if ($versionParts.Count -ge 3) {
    $DEFAULT_TRANSMISSION_VERSION = "$($versionParts[0]).$($versionParts[1]).$($versionParts[2])"
} else {
    $DEFAULT_TRANSMISSION_VERSION = $APP_VERSION
}

# List available transmission versions
if ($ListVersions) {
    Write-Host "Fetching available transmission versions..." -ForegroundColor Yellow
    try {
        $releases = Invoke-RestMethod -Uri $TRANSMISSION_RELEASES_URL -UseBasicParsing -TimeoutSec 30
        Write-Host ""
        Write-Host "Available transmission versions:" -ForegroundColor Cyan
        $releases | Select-Object -First 10 | ForEach-Object {
            $ver = $_.tag_name -replace '^v', ''
            Write-Host "  - $ver" -ForegroundColor Gray
        }
        Write-Host ""
        Write-Host "Usage: .\build.ps1 -TransmissionVersion <version>" -ForegroundColor Yellow
    } catch {
        Write-Host "ERROR: Failed to fetch versions from GitHub" -ForegroundColor Red
        Write-Host $_.Exception.Message
    }
    exit 0
}
$ARCH = $Arch
$BUILD_DIR = Join-Path $PROJECT_DIR ".local-build"
$FNPACK_URL = "https://static2.fnnas.com/fnpack/fnpack-1.2.3-windows-amd64"
$GITHUB_RELEASES_URL = "https://github.com/sushazhi/fnos-transmission/releases/download"
$WEBUI_BASE = "https://ghfast.top/https://github.com/sushazhi/transmission-web/releases/download"

# 下载代理配置（参考 qbittorrent build.ps1）
$MAIN_PROXY = "https://gh-proxy.com/"
$BINARY_PROXY = "https://ghfast.top/"

# 通用代理下载：依次尝试 MAIN_PROXY -> BINARY_PROXY -> 直连（使用 curl.exe，避免代理对 Invoke-WebRequest 返回 403）
function Invoke-ProxyDownload {
    param([string]$Url, [string]$OutFile, [string]$Description)
    $urls = @(
        $MAIN_PROXY + $Url,
        $BINARY_PROXY + $Url,
        $Url
    )
    foreach ($u in $urls) {
        if (Test-Path $OutFile) { Remove-Item $OutFile -Force -ErrorAction SilentlyContinue }
        & curl.exe -L -f -o $OutFile -s --connect-timeout 15 --max-time 180 --retry 2 --retry-delay 3 $u 2>$null
        if ($LASTEXITCODE -eq 0 -and (Test-Path $OutFile) -and (Get-Item $OutFile).Length -gt 0) {
            return $true
        }
    }
    if (Test-Path $OutFile) { Remove-Item $OutFile -Force -ErrorAction SilentlyContinue }
    Write-Host "  ERROR: Failed to download $Description (all proxies failed)" -ForegroundColor Red
    return $false
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Transmission for fnOS - Local Build" -ForegroundColor Cyan
Write-Host "  Version: $APP_VERSION" -ForegroundColor Gray
Write-Host "  Arch: $ARCH" -ForegroundColor Gray
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Setup build directory
Write-Host "[1/6] Setting up build directory..." -ForegroundColor Yellow
@("app\bin", "app\lib", "app\ui", "cmd", "config", "wizard") | ForEach-Object {
    New-Item -ItemType Directory -Force -Path (Join-Path $BUILD_DIR $_) | Out-Null
}
Write-Host "  Build directory ready" -ForegroundColor Green

# Copy project files
Write-Host "[2/6] Copying project files..." -ForegroundColor Yellow
Copy-Item "$PROJECT_DIR\cmd\*" "$BUILD_DIR\cmd\" -Recurse -Force
Copy-Item "$PROJECT_DIR\config\*" "$BUILD_DIR\config\" -Recurse -Force
Copy-Item "$PROJECT_DIR\wizard\*" "$BUILD_DIR\wizard\" -Recurse -Force
Copy-Item "$PROJECT_DIR\manifest" "$BUILD_DIR\" -Force
@("ICON.PNG", "ICON_256.PNG") | ForEach-Object {
    if (Test-Path "$PROJECT_DIR\$_") {
        Copy-Item "$PROJECT_DIR\$_" "$BUILD_DIR\" -Force
    }
}
Write-Host "  Project files copied" -ForegroundColor Green

# Get transmission-daemon
Write-Host "[3/6] Preparing transmission-daemon..." -ForegroundColor Yellow

# Determine transmission version to use
$targetVersion = if ($TransmissionVersion) { $TransmissionVersion } else { $DEFAULT_TRANSMISSION_VERSION }
Write-Host "  Transmission version: $targetVersion" -ForegroundColor Gray

$daemonCache = Join-Path $BUILD_DIR "transmission-daemon-$targetVersion-$ARCH"
$daemonCacheLegacy = Join-Path $BUILD_DIR "transmission-daemon-$targetVersion"
$daemonTarget = "$BUILD_DIR\app\bin\transmission-daemon"

if ((Test-Path $daemonCache) -or (Test-Path $daemonCacheLegacy)) {
    Write-Host "  Using cached binary" -ForegroundColor Green
    if (Test-Path $daemonCache) { Copy-Item $daemonCache $daemonTarget -Force }
    else { Copy-Item $daemonCacheLegacy $daemonTarget -Force }
} else {
    Write-Host "  Downloading from release v$targetVersion..." -ForegroundColor Yellow
    # Try arch-suffixed (new releases) -> version-suffixed -> plain (legacy releases)
    $daemonUrls = @(
        "$GITHUB_RELEASES_URL/v$targetVersion/transmission-daemon-$targetVersion-$ARCH",
        "$GITHUB_RELEASES_URL/v$targetVersion/transmission-daemon-$targetVersion",
        "$GITHUB_RELEASES_URL/v$targetVersion/transmission-daemon"
    )
    $downloaded = $false
    foreach ($url in $daemonUrls) {
        if (Invoke-ProxyDownload -Url $url -OutFile $daemonCache -Description "transmission-daemon-$targetVersion-$ARCH") {
            Copy-Item $daemonCache $daemonTarget -Force
            Write-Host "  Downloaded (via proxy) -> $url" -ForegroundColor Green
            $downloaded = $true
            break
        }
        Write-Host "  Not found: $url" -ForegroundColor DarkGray
    }
    if (-not $downloaded) {
        Write-Host "  ERROR: Failed to download transmission-daemon for $ARCH from release v$targetVersion" -ForegroundColor Red
        Write-Host "  Make sure release v$targetVersion exists with transmission-daemon asset" -ForegroundColor Yellow
        exit 1
    }
}

# Get libminiupnpc
Write-Host "[4/6] Preparing libminiupnpc..." -ForegroundColor Yellow
$libCache = Join-Path $BUILD_DIR "libminiupnpc.so.17-$targetVersion-$ARCH"
$libCacheLegacy = Join-Path $BUILD_DIR "libminiupnpc.so.17-$targetVersion"
$libTarget = "$BUILD_DIR\app\lib\libminiupnpc.so.17"
if ((Test-Path $libCache) -or (Test-Path $libCacheLegacy)) {
    Write-Host "  Using cached" -ForegroundColor Green
    if (Test-Path $libCache) { Copy-Item $libCache $libTarget -Force }
    else { Copy-Item $libCacheLegacy $libTarget -Force }
} else {
    Write-Host "  Downloading from release v$targetVersion..." -ForegroundColor Yellow
    # Try arch-suffixed (new releases) -> version-suffixed -> plain (legacy releases)
    $libUrls = @(
        "$GITHUB_RELEASES_URL/v$targetVersion/libminiupnpc.so.17-$targetVersion-$ARCH",
        "$GITHUB_RELEASES_URL/v$targetVersion/libminiupnpc.so.17-$targetVersion",
        "$GITHUB_RELEASES_URL/v$targetVersion/libminiupnpc.so.17"
    )
    $libDownloaded = $false
    foreach ($url in $libUrls) {
        if (Invoke-ProxyDownload -Url $url -OutFile $libCache -Description "libminiupnpc.so.17-$targetVersion-$ARCH") {
            Copy-Item $libCache $libTarget -Force
            Write-Host "  Downloaded (via proxy) -> $url" -ForegroundColor Green
            $libDownloaded = $true
            break
        }
        Write-Host "  Not found: $url" -ForegroundColor DarkGray
    }
    if (-not $libDownloaded) {
        Write-Host "  Warning: libminiupnpc.so.17 not available for $ARCH in release v$targetVersion" -ForegroundColor Yellow
    }
}

# Get WebUI version from GitHub
Write-Host "[5/6] Preparing WebUI..." -ForegroundColor Yellow
$WEBUI_API_URL = "https://api.github.com/repos/sushazhi/transmission-web/releases/latest"
try {
    $webuiResponse = Invoke-WebRequest -Uri $WEBUI_API_URL -UseBasicParsing -TimeoutSec 30
    $webuiJson = $webuiResponse | ConvertFrom-Json
    $WEBUI_VERSION = $webuiJson.tag_name -replace '^v', ''
    Write-Host "  Latest WebUI version: v$WEBUI_VERSION" -ForegroundColor Gray
} catch {
    Write-Host "  Warning: Failed to get latest WebUI version, using cached" -ForegroundColor Yellow
    $WEBUI_VERSION = "0.0.9"
}
$webuiFile = "transmission-web-v$WEBUI_VERSION.zip"
$webuiCache = Join-Path $BUILD_DIR $webuiFile
if ((Test-Path $webuiCache)) {
    Write-Host "  Using cached" -ForegroundColor Green
} else {
    Write-Host "  Downloading..." -ForegroundColor Yellow
    $url = "$WEBUI_BASE/v$WEBUI_VERSION/$webuiFile"
    Invoke-WebRequest -Uri $url -OutFile $webuiCache -UseBasicParsing
    Write-Host "  Downloaded" -ForegroundColor Green
}

# Extract WebUI
Write-Host "  Extracting..." -ForegroundColor Gray
Expand-Archive -Path $webuiCache -DestinationPath "$BUILD_DIR\app\ui" -Force
if (Test-Path "$BUILD_DIR\app\ui\transmission") {
    Get-ChildItem "$BUILD_DIR\app\ui\transmission" | Move-Item -Destination "$BUILD_DIR\app\ui\" -Force
    Remove-Item "$BUILD_DIR\app\ui\transmission" -Recurse -Force
}

# Inject update check into transmission-web's index.html
Write-Host "  Injecting update check..." -ForegroundColor Gray
$indexHtml = Get-Content "$BUILD_DIR\app\ui\index.html" -Raw

# Use $APP_VERSION (which may be overridden by -AppVersion)
$appVersion = $APP_VERSION

# Inject version and update script before </body>
$injectScript = @"
    <script>
        window.TRANSMISSION_APP_VERSION = '$appVersion';
    </script>
    <script src="update-check.js"></script>
"@

if ($indexHtml -match '</body>') {
    $indexHtml = $indexHtml -replace '</body>', "$injectScript`n</body>"
    $indexHtml | Set-Content "$BUILD_DIR\app\ui\index.html" -NoNewline
    Write-Host "  Update check injected (v$appVersion)" -ForegroundColor Green
} else {
    Write-Host "  Warning: Could not find </body> tag" -ForegroundColor Yellow
}

# Copy update files
if (Test-Path "$PROJECT_DIR\app\ui\config") {
    Copy-Item "$PROJECT_DIR\app\ui\config" "$BUILD_DIR\app\ui\" -Force
}
if (Test-Path "$PROJECT_DIR\app\ui\images") {
    Copy-Item "$PROJECT_DIR\app\ui\images" "$BUILD_DIR\app\ui\" -Recurse -Force
}
if (Test-Path "$PROJECT_DIR\app\ui\update-check.js") {
    Copy-Item "$PROJECT_DIR\app\ui\update-check.js" "$BUILD_DIR\app\ui\" -Force
}
# Copy gateway proxy
if (Test-Path "$PROJECT_DIR\app\bin\gateway-proxy.py") {
    Copy-Item "$PROJECT_DIR\app\bin\gateway-proxy.py" "$BUILD_DIR\app\bin\" -Force
}
Write-Host "  WebUI ready" -ForegroundColor Green

# Build
Write-Host "[6/6] Building package..." -ForegroundColor Yellow
$FNPACK_FILE = $FNPACK_URL.Substring($FNPACK_URL.LastIndexOf('/') + 1)
$fnpackPath = Join-Path $BUILD_DIR $FNPACK_FILE
if (-not (Test-Path $fnpackPath)) {
    Write-Host "  Downloading fnpack..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri $FNPACK_URL -OutFile $fnpackPath -UseBasicParsing
    Write-Host "  Downloaded" -ForegroundColor Green
} else {
    Write-Host "  Using cached fnpack" -ForegroundColor Green
}

Remove-Item "$BUILD_DIR\transmission.fpk" -Force -ErrorAction SilentlyContinue
Push-Location $BUILD_DIR
$buildOutput = cmd /c "$fnpackPath build" 2>&1
$buildSuccess = Test-Path "transmission.fpk"
Pop-Location

if ($buildSuccess) {
    Move-Item "$BUILD_DIR\transmission.fpk" "$PROJECT_DIR\transmission-$APP_VERSION-$ARCH.fpk" -Force
    Write-Host "  Build successful!" -ForegroundColor Green
} else {
    Write-Host "  ERROR: Build failed" -ForegroundColor Red
    Write-Host "  Build output:" -ForegroundColor Yellow
    Write-Host $buildOutput
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Build Complete!" -ForegroundColor Green
Write-Host "  Output: transmission-$APP_VERSION-$ARCH.fpk" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
