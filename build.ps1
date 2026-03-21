param(
    [switch]$Clean
)

if ($Clean) {
    if (Test-Path .\build) { Remove-Item .\build -Recurse -Force }
    if (Test-Path .\dist) { Remove-Item .\dist -Recurse -Force }
}

python -m PyInstaller .\silentinstallhelper.spec --noconfirm
