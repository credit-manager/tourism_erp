$cloudflared = (Get-Command "cloudflared.exe" -ErrorAction SilentlyContinue).Source
if (-not $cloudflared) {
    $localPath = Join-Path $PSScriptRoot "cloudflared\cloudflared.exe"
    if (Test-Path $localPath) { $cloudflared = $localPath }
    else { Write-Output "cloudflared.exe not found. Install it or place in project folder."; exit 1 }
}
$ntfyTopic = "mahmoud-erp-2026"
$logFile = "$env:TEMP\cf_tunnel.log"

# Start cloudflared
$p = Start-Process -FilePath $cloudflared -ArgumentList "tunnel","--url","http://localhost:8000" -RedirectStandardError $logFile -NoNewWindow -PassThru

# Wait for URL (max 30 seconds)
$url = $null
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep 2
    if (Test-Path $logFile) {
        $content = Get-Content $logFile -Raw -ErrorAction SilentlyContinue
        $match = [regex]::Match($content, 'https://[a-z0-9\-]+\.trycloudflare\.com')
        if ($match.Success) {
            $url = $match.Value.Trim()
            break
        }
    }
}

if ($url) {
    $ntfyUrl = "https://ntfy.sh/" + $ntfyTopic
    Invoke-RestMethod -Uri $ntfyUrl -Method Post -Body $url -Headers @{
        'Title' = 'Tourism ERP Ready'
        'Priority' = 'high'
    } -ErrorAction SilentlyContinue
}

# Keep tunnel alive until server stops
$p.WaitForExit()
