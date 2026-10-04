[CmdletBinding()]
param(
    [switch]$Package
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$distRoot = Join-Path $projectRoot "dist"
$workRoot = Join-Path $projectRoot "build\pyinstaller"
$releaseRoot = Join-Path $projectRoot "release"
$specPath = Join-Path $PSScriptRoot "VoxRescue.spec"
$appDir = Join-Path $distRoot "VoxRescue"
$nativeBuild = Join-Path $PSScriptRoot "native_model_guard\build.ps1"
$zipPath = Join-Path $releaseRoot "VoxRescue-Windows-x64-1.1.0.zip"
$hashPath = "$zipPath.sha256.txt"

Set-Location $projectRoot
New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null

& $nativeBuild

$pyInstallerArgs = @(
    "-m"
    "PyInstaller"
    "--noconfirm"
    "--clean"
    "--distpath"
    $distRoot
    "--workpath"
    $workRoot
    $specPath
)
python @pyInstallerArgs
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE"
}

if (-not (Test-Path -LiteralPath (Join-Path $appDir "VoxRescue.exe"))) {
    throw "VoxRescue.exe was not created"
}

$exe = Get-Item -LiteralPath (Join-Path $appDir "VoxRescue.exe")
$result = [ordered]@{
    Executable = $exe.FullName
    ExecutableBytes = $exe.Length
}
if ($Package) {
    if (Test-Path -LiteralPath $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }
    if (Test-Path -LiteralPath $hashPath) {
        Remove-Item -LiteralPath $hashPath -Force
    }
    Compress-Archive -Path $appDir -DestinationPath $zipPath -CompressionLevel Optimal
    $hash = Get-FileHash -LiteralPath $zipPath -Algorithm SHA256
    "$($hash.Hash)  $($hash.Path | Split-Path -Leaf)" |
        Set-Content -LiteralPath $hashPath -Encoding ascii
    $archive = Get-Item -LiteralPath $zipPath
    $result.Package = $archive.FullName
    $result.PackageBytes = $archive.Length
    $result.SHA256 = $hash.Hash
}
[pscustomobject]$result
