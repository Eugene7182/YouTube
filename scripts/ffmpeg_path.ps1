Set-StrictMode -Version Latest; $ErrorActionPreference="Stop"
$ff = Get-ChildItem tools\ffmpeg -Recurse -Filter ffmpeg.exe | Select-Object -First 1 -Expand FullName
if (-not $ff) { Write-Error "ffmpeg not found under tools\ffmpeg"; exit 2 }
$env:Path = (Split-Path $ff) + ";" + $env:Path
& $ff -version
