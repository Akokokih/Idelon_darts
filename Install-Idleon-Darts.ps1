$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 64 bits est requis.' }
}
& '.venv\Scripts\python.exe' -m pip install -e '.[capture,vision]'
if ($LASTEXITCODE -ne 0) { throw 'Installation interrompue. Consultez le message ci-dessus.' }
Write-Host 'Installation terminee. Ouvrez Start-Idleon-Darts.cmd.'
