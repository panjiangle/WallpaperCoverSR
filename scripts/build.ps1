$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    py -3.13 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.13 x64 is required.' }
}
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
& $pythonExe -m pip install -r requirements.txt pyinstaller==6.22.3
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $pythonExe scripts\download_backend.py
if ($LASTEXITCODE -ne 0) { throw 'Backend download failed.' }
& $pythonExe scripts\make_icon.py
& $pythonExe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
& $pythonExe -m PyInstaller --noconfirm --clean --windowed --onedir --name WallpaperCoverSR --icon build\app.ico --collect-submodules winrt.windows.foundation --collect-submodules winrt.windows.foundation.collections --hidden-import winrt.windows.media.control --hidden-import winrt.windows.storage.streams --hidden-import winrt.windows.media --hidden-import winrt.windows.media.playback --hidden-import winrt.windows.media.core --hidden-import pystray._win32 run.py
if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
& $pythonExe scripts\package_release.py
if ($LASTEXITCODE -ne 0) { throw 'Packaging failed.' }
