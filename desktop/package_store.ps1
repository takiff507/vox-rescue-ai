[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9.-]{3,50}$')][string]$IdentityName,
    [Parameter(Mandatory)][ValidatePattern('^CN=')][string]$Publisher,
    [Parameter(Mandatory)][string]$PublisherDisplayName,
    [ValidatePattern('^\d+\.\d+\.\d+\.0$')][string]$Version = '1.1.0.0'
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$appRoot = Join-Path $projectRoot 'dist\VoxRescue'
if (-not (Test-Path -LiteralPath (Join-Path $appRoot 'VoxRescue.exe'))) {
    throw 'Build the standalone application first.'
}
$sdkRoot = 'C:\Program Files (x86)\Windows Kits\10\bin'
$packager = Get-ChildItem -LiteralPath $sdkRoot -Directory |
    Where-Object Name -Match '^10\.0\.\d+\.0$' |
    Sort-Object { [version]$_.Name } -Descending |
    ForEach-Object { Join-Path $_.FullName 'x64\makeappx.exe' } |
    Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $packager) { throw 'Windows SDK MakeAppx.exe is required.' }

python (Join-Path $PSScriptRoot 'make_store_assets.py')
if ($LASTEXITCODE -ne 0) { throw 'Store asset generation failed.' }
$stageRoot = Join-Path $projectRoot ('build\store-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stageRoot | Out-Null
Copy-Item -LiteralPath $appRoot -Destination (Join-Path $stageRoot 'App') -Recurse
Copy-Item -LiteralPath (Join-Path $projectRoot 'release\store-assets') -Destination (Join-Path $stageRoot 'Assets') -Recurse
$expectedHash = 'B42F1AED76CCD476B293F1BDF98D5ACC289FB75D924581FB3C2BDC4B4A341301'
$modelFile = Join-Path $stageRoot 'App\_internal\models\protected\vox_rescue_engine.vrm'
if ((Get-FileHash -LiteralPath $modelFile -Algorithm SHA256).Hash -ne $expectedHash) {
    throw 'Protected production model integrity check failed.'
}
$identity = [System.Security.SecurityElement]::Escape($IdentityName)
$publisherValue = [System.Security.SecurityElement]::Escape($Publisher)
$publisherLabel = [System.Security.SecurityElement]::Escape($PublisherDisplayName)
$manifest = @"
<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
 xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
 xmlns:uap10="http://schemas.microsoft.com/appx/manifest/uap/windows10/10"
 xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
 IgnorableNamespaces="uap uap10 rescap">
 <Identity Name="$identity" Publisher="$publisherValue" Version="$Version" ProcessorArchitecture="x64"/>
 <Properties><DisplayName>Vox Rescue AI</DisplayName><PublisherDisplayName>$publisherLabel</PublisherDisplayName><Description>Free on-device microphone clarity for Windows.</Description><Logo>Assets\StoreLogo.png</Logo></Properties>
 <Resources><Resource Language="en-us"/></Resources>
 <Dependencies><TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.19041.0" MaxVersionTested="10.0.26300.0"/></Dependencies>
 <Applications><Application Id="VoxRescue" Executable="App\VoxRescue.exe" uap10:RuntimeBehavior="packagedClassicApp" uap10:TrustLevel="mediumIL">
 <uap:VisualElements DisplayName="Vox Rescue AI" Description="Free on-device microphone clarity for Windows." BackgroundColor="#F6F8F8" Square44x44Logo="Assets\Square44x44Logo.png" Square150x150Logo="Assets\Square150x150Logo.png"/>
 </Application></Applications>
 <Capabilities><rescap:Capability Name="runFullTrust"/><DeviceCapability Name="microphone"/></Capabilities>
</Package>
"@
$manifest | Set-Content -LiteralPath (Join-Path $stageRoot 'AppxManifest.xml') -Encoding utf8
$output = Join-Path $projectRoot "release\VoxRescue-$Version-x64.msix"
& $packager pack /d $stageRoot /p $output /o
if ($LASTEXITCODE -ne 0) { throw "MSIX packaging failed: $LASTEXITCODE" }
Get-FileHash -LiteralPath $output -Algorithm SHA256
Write-Output 'Unsigned Store upload package created. No certificate installed and no Store submission performed.'
