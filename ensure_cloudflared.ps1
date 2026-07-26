$cfDir = Join-Path $PSScriptRoot "cloudflared"
$cfExe = Join-Path $cfDir "cloudflared.exe"

# Check if already exists
if (Test-Path $cfExe) {
    Write-Output "FOUND"
    exit 0
}

# Check in PATH
$fromPath = (Get-Command "cloudflared.exe" -ErrorAction SilentlyContinue).Source
if ($fromPath) {
    Write-Output "FOUND"
    exit 0
}

Write-Output "Downloading cloudflared.exe..."

# Create directory
if (-not (Test-Path $cfDir)) {
    New-Item -ItemType Directory -Path $cfDir -Force | Out-Null
}

# Detect architecture
$arch = if ([Environment]::Is64BitOperatingSystem) { "amd64" } else { "386" }
$url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-$arch.exe"

try {
    $wc = New-Object System.Net.WebClient
    $wc.DownloadFile($url, $cfExe)
    Write-Output "DONE"
    exit 0
} catch {
    Write-Output "FAILED"
    Write-Output "Download manually from: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
    exit 1
}
