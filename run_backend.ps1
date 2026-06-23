$envFile = "api\.env"
Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#')) {
        $parts = $line -split '=', 2
        if ($parts.Count -eq 2) {
            [Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim().Trim('"'), 'Process')
        }
    }
}
Set-Location "D:\Projects-D\s2connects AI Voice bot\scaiva"
.\venv\Scripts\python.exe -m uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload --reload-dir api
