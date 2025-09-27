param()

$targetKeys = @('PEXELS_API_KEY','PIXABAY_API_KEY','YOUTUBE_API_KEY')
$envPath = Join-Path (Get-Location) '.env'
$secretsPath = Join-Path (Get-Location) 'secrets\api_keys.json'
$values = @{}

# If secrets/api_keys.json exists, load keys from it (prefer these)
if (Test-Path $secretsPath) {
    try {
        $json = Get-Content $secretsPath -Raw | ConvertFrom-Json
        foreach ($k in $targetKeys) {
            if ($json.PSObject.Properties.Name -contains $k -and -not [string]::IsNullOrEmpty($json.$k)) {
                $values[$k] = $json.$k
            }
        }
    } catch {
        Write-Host "Warning: failed to parse secrets/api_keys.json: $($_.Exception.Message)"
    }
}

if (Test-Path $envPath) {
    foreach ($line in Get-Content $envPath) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        if ($line.TrimStart().StartsWith('#')) { continue }
        if ($line -match '^\s*([^=]+?)\s*=\s*(.*)$') {
            $key = $matches[1].Trim()
            $value = $matches[2]
            if ($targetKeys -contains $key) {
                $values[$key] = $value
            }
        }
    }
}

foreach ($key in $targetKeys) {
    if ($values.ContainsKey($key) -and -not [string]::IsNullOrEmpty($values[$key])) {
        Set-Item -Path ("Env:{0}" -f $key) -Value $values[$key]
    }
    $current = (Get-Item -Path ("Env:{0}" -f $key) -ErrorAction SilentlyContinue).Value
    if ([string]::IsNullOrEmpty($current)) {
        Write-Host "${key}: (not set)"
    } else {
        $mask = if ($current.Length -le 6) { $current } else { $current.Substring(0,6) + '...' }
        Write-Host "${key}: $mask"
    }
}

