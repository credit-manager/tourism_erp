param([string]$LogFile)

# Wait for and extract the tunnel URL
$url = $null
for ($i = 0; $i -lt 25; $i++) {
    Start-Sleep 1
    if (Test-Path $LogFile) {
        $content = Get-Content $LogFile -Raw -ErrorAction SilentlyContinue
        if ($content) {
            $match = [regex]::Match($content, 'https://[a-z0-9\-]+\.trycloudflare\.com')
            if ($match.Success) {
                $url = $match.Value.Trim()
                break
            }
        }
    }
}

if ($url) {
    # Send to phone via ntfy.sh
    try {
        Invoke-RestMethod -Uri "https://ntfy.sh/mahmoud-erp-2026" -Method Post -Body $url -Headers @{
            'Title' = 'Tourism ERP Ready'
            'Priority' = 'high'
        } -ErrorAction SilentlyContinue | Out-Null
    } catch {}
    # Output for the batch file
    Write-Output $url
} else {
    Write-Output ""
}
