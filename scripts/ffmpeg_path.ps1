$ff = Get-ChildItem -Path "tools\ffmpeg" -Recurse -Filter "ffmpeg.exe" -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
if ($ff) {
    $env:Path = (Split-Path $ff) + ';' + $env:Path
    Write-Host "FFmpeg -> $ff"
} else {
    Write-Error 'ffmpeg not found'
    exit 1
}
