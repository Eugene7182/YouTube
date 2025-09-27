$null = . .\scripts\load_env.ps1

Write-Host "PEXELS_API_KEY:" ($null -ne $env:PEXELS_API_KEY)
Write-Host "PIXABAY_API_KEY:" ($null -ne $env:PIXABAY_API_KEY)
