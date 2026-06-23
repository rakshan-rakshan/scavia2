# SCAIVA Remote Deploy Runner (PowerShell)
# Uploads deploy script to Oracle VM and runs it
param(
    [Parameter(Mandatory=$true)]
    [string]$ServerIp,
    [Parameter(Mandatory=$true)]
    [string]$SshKeyPath,
    [Parameter(Mandatory=$false)]
    [string]$SshUser = "ubuntu",
    [Parameter(Mandatory=$false)]
    [int]$FastApiWorkers = 2,
    [Parameter(Mandatory=$false)]
    [switch]$ForceTurnRelay
)

$ErrorActionPreference = "Stop"
$ScriptPath = Join-Path $PSScriptRoot "deploy_scaiva_remote.sh"

if (-not (Test-Path -LiteralPath $ScriptPath)) {
    Write-Error "deploy_scaiva_remote.sh not found at $ScriptPath"
    exit 1
}

if (-not (Test-Path -LiteralPath $SshKeyPath)) {
    Write-Error "SSH key not found at $SshKeyPath"
    exit 1
}

# Validate the key has proper permissions
$keyAcl = icacls $SshKeyPath 2>&1
Write-Host "[*] Using SSH key: $SshKeyPath"
Write-Host "[*] Server IP: $ServerIp"
Write-Host "[*] SSH user: $SshUser"
Write-Host ""

# Test SSH connection first
Write-Host "[1/3] Testing SSH connection..."
$testResult = ssh -i $SshKeyPath -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 "$SshUser@$ServerIp" "echo CONNECTED" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "SSH connection failed: $testResult"
    exit 1
}
Write-Host "  OK - Connected to $ServerIp"

# Upload the deployment script
Write-Host "[2/3] Uploading deployment script..."
scp -i $SshKeyPath -o StrictHostKeyChecking=accept-new $ScriptPath "$SshUser@$ServerIp`:~/deploy_scaiva_remote.sh" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "SCP upload failed"
    exit 1
}
Write-Host "  OK - Script uploaded"

# Make it executable and run
Write-Host "[3/3] Running deployment on remote server..."
Write-Host "  (This takes ~5-10 minutes on first run)"
Write-Host ""

$envVars = "FORCE_TURN_RELAY=`$($ForceTurnRelay.IsPresent ? 'true' : 'false')"
$envVars += " FASTAPI_WORKERS=$FastApiWorkers"
$envVars += " ENABLE_TELEMETRY=false"

ssh -i $SshKeyPath -o StrictHostKeyChecking=accept-new "$SshUser@$ServerIp" `
    "bash ~/deploy_scaiva_remote.sh $ServerIp" 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "  DEPLOYMENT COMPLETE!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Open https://$ServerIp in your browser" -ForegroundColor Cyan
    Write-Host "Accept the self-signed cert warning"
    Write-Host ""
    Write-Host "SSH quick commands:" -ForegroundColor Yellow
    Write-Host "  ssh -i $SshKeyPath ubuntu@$ServerIp"
    Write-Host "  cd ~/scaiva/dograh && docker compose ps"
    Write-Host "  cd ~/scaiva/dograh && docker compose logs -f api"
} else {
    Write-Host ""
    Write-Host "Deployment encountered issues. Check the output above." -ForegroundColor Red
}
