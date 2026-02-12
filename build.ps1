# build.ps1 - Transmission for fnOS Local Build

$ErrorActionPreference = "Stop"

$PROJECT_DIR = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$MANIFEST_FILE = Join-Path $PROJECT_DIR "manifest"

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
$ARCH = "arm64"
$BUILD_DIR = Join-Path $PROJECT_DIR ".local-build"
$FNPACK_URL = "https://static2.fnnas.com/fnpack/fnpack-1.2.1-windows-amd64"
$GITHUB_BRANCH = "https://ghfast.top/https://raw.githubusercontent.com/sushazhi/fnos-transmission/main"
$WEBUI_BASE = "https://ghfast.top/https://github.com/jianxcao/transmission-web/releases/download"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Transmission for fnOS - Local Build" -ForegroundColor Cyan
Write-Host "  Version: $APP_VERSION" -ForegroundColor Gray
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
@("LICENSE", "ICON.PNG", "ICON_256.PNG") | ForEach-Object {
    if (Test-Path "$PROJECT_DIR\$_") {
        Copy-Item "$PROJECT_DIR\$_" "$BUILD_DIR\" -Force
    }
}
Write-Host "  Project files copied" -ForegroundColor Green

# Get transmission-daemon
Write-Host "[3/6] Preparing transmission-daemon..." -ForegroundColor Yellow
$daemonCache = Join-Path $BUILD_DIR "transmission-daemon"
$daemonTarget = "$BUILD_DIR\app\bin\transmission-daemon"
if ((Test-Path $daemonCache)) {
    Write-Host "  Using cached binary" -ForegroundColor Green
    Copy-Item $daemonCache $daemonTarget -Force
} else {
    Write-Host "  Downloading..." -ForegroundColor Yellow
    $url = "$GITHUB_BRANCH/builds/$APP_VERSION/transmission-daemon"
    Invoke-WebRequest -Uri $url -OutFile $daemonCache -UseBasicParsing
    Copy-Item $daemonCache $daemonTarget -Force
    Write-Host "  Downloaded" -ForegroundColor Green
}

# Get libminiupnpc
Write-Host "[4/6] Preparing libminiupnpc..." -ForegroundColor Yellow
$libCache = Join-Path $BUILD_DIR "libminiupnpc.so.17"
$libTarget = "$BUILD_DIR\app\lib\libminiupnpc.so.17"
if ((Test-Path $libCache)) {
    Write-Host "  Using cached" -ForegroundColor Green
    Copy-Item $libCache $libTarget -Force
} else {
    Write-Host "  Downloading..." -ForegroundColor Yellow
    $url = "$GITHUB_BRANCH/builds/$APP_VERSION/libminiupnpc.so.17"
    try {
        Invoke-WebRequest -Uri $url -OutFile $libCache -UseBasicParsing
        Copy-Item $libCache $libTarget -Force
        Write-Host "  Downloaded" -ForegroundColor Green
    } catch {
        Write-Host "  Warning: Not available" -ForegroundColor Yellow
    }
}

# Get WebUI version from GitHub
Write-Host "[5/6] Preparing WebUI..." -ForegroundColor Yellow
$WEBUI_API_URL = "https://api.github.com/repos/jianxcao/transmission-web/releases/latest"
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

# Read version from manifest
$manifestContent = Get-Content "$BUILD_DIR\manifest" -Raw
$versionMatch = $manifestContent | Select-String 'version\s*=\s*(\S+)'
if ($versionMatch) {
    $appVersion = $versionMatch.Matches.Groups[1].Value.Trim()
}

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
cmd /c "$fnpackPath build" *>&1 | Out-Null
$buildSuccess = Test-Path "transmission.fpk"
Pop-Location

if ($buildSuccess) {
    Move-Item "$BUILD_DIR\transmission.fpk" "$PROJECT_DIR\transmission-$APP_VERSION-$ARCH.fpk" -Force
    Write-Host "  Build successful!" -ForegroundColor Green
} else {
    Write-Host "  ERROR: Build failed" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Build Complete!" -ForegroundColor Green
Write-Host "  Output: transmission-$APP_VERSION-$ARCH.fpk" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
