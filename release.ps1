param(
    [switch]$Clean
)

$Version = "0.1.0"
$ReleaseRoot = Join-Path $PSScriptRoot "release"
$ReleaseDir = Join-Path $ReleaseRoot "SilentInstallHelper-$Version"
$DistExe = Join-Path $PSScriptRoot "dist\\SilentInstallHelper.exe"

if ($Clean) {
    if (Test-Path $ReleaseRoot) { Remove-Item $ReleaseRoot -Recurse -Force }
}

& (Join-Path $PSScriptRoot "build.ps1") -Clean:$Clean
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
Copy-Item $DistExe $ReleaseDir -Force
Copy-Item (Join-Path $PSScriptRoot "example-config.json") $ReleaseDir -Force
Copy-Item (Join-Path $PSScriptRoot "config-7zip-extract.jsonc") $ReleaseDir -Force
Copy-Item (Join-Path $PSScriptRoot "config-example-7z-icacls.jsonc") $ReleaseDir -Force
Copy-Item (Join-Path $PSScriptRoot "config-template.jsonc") $ReleaseDir -Force
Copy-Item (Join-Path $PSScriptRoot "config-template-basic.jsonc") $ReleaseDir -Force
Copy-Item (Join-Path $PSScriptRoot "config-template-full.jsonc") $ReleaseDir -Force
Copy-Item (Join-Path $PSScriptRoot "config-template-silent.jsonc") $ReleaseDir -Force
Copy-Item (Join-Path $PSScriptRoot "readme.md") $ReleaseDir -Force

$ReleaseNotes = @"
SilentInstallHelper $Version

Enthaelt:
- SilentInstallHelper.exe
- example-config.json
- config-7zip-extract.jsonc
- config-example-7z-icacls.jsonc
- config-template.jsonc
- config-template-basic.jsonc
- config-template-full.jsonc
- config-template-silent.jsonc
- readme.md

Optional:
- Fuer ein eigenes Icon assets/app.ico vor dem Build hinterlegen.
"@

$ReleaseNotes | Set-Content -Encoding utf8 (Join-Path $ReleaseDir "RELEASE.txt")

Compress-Archive -Path (Join-Path $ReleaseDir "*") -DestinationPath (Join-Path $ReleaseRoot "SilentInstallHelper-$Version.zip") -Force

Write-Host "Release bereit unter: $ReleaseDir"
Write-Host "ZIP bereit unter: $(Join-Path $ReleaseRoot "SilentInstallHelper-$Version.zip")"
