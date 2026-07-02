# Headless-browser JS check: loads the dashboard in headless Edge and reports
# console errors/warnings. Usage:  powershell -File scripts/browser_check.ps1 [url]
param([string]$Url = "http://127.0.0.1:5057/")

$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
$profile = Join-Path $env:TEMP ("edge-headless-" + [guid]::NewGuid().ToString("N"))
$log = Join-Path $env:TEMP ("edge-console-" + [guid]::NewGuid().ToString("N") + ".log")

# --virtual-time-budget lets the page run its JS (fetches, charts) before dump.
$args = @(
    "--headless=new", "--disable-gpu", "--no-first-run",
    "--user-data-dir=$profile",
    "--enable-logging=stderr", "--v=0",
    "--virtual-time-budget=30000",
    "--dump-dom", $Url
)

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $edge
$psi.Arguments = ($args | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }) -join ' '
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.UseShellExecute = $false

$proc = [System.Diagnostics.Process]::Start($psi)
$stdout = $proc.StandardOutput.ReadToEnd()
$stderr = $proc.StandardError.ReadToEnd()
$proc.WaitForExit(120000) | Out-Null

$domBytes = [System.Text.Encoding]::UTF8.GetByteCount($stdout)
Write-Output ("DOM_BYTES=" + $domBytes)

# Positive evidence that dashboard init ran to completion: switchToTab() sets
# data-active on tab buttons at the very end of init, and settings.js populates
# the test-report year select.
foreach ($marker in @('data-active="true"', '<option value="2025">2025</option>')) {
    $found = $stdout.Contains($marker)
    Write-Output ("MARKER " + $marker + " => " + $(if ($found) { "PRESENT" } else { "MISSING" }))
}

# Surface console messages (errors/warnings) from the Chromium log lines.
$consoleLines = $stderr -split "`n" | Where-Object {
    $_ -match "CONSOLE" -or $_ -match "Uncaught" -or $_ -match ":ERROR:"
} | Where-Object {
    # Ignore GPU/network-stack noise that is not page JS.
    $_ -notmatch "gpu_|GpuControl|network_service|cert_|device_event"
}
if ($consoleLines) {
    Write-Output "CONSOLE_MESSAGES:"
    $consoleLines | ForEach-Object { Write-Output ("  " + $_.Trim()) }
} else {
    Write-Output "CONSOLE_MESSAGES: none"
}

Remove-Item -Recurse -Force $profile -ErrorAction SilentlyContinue
