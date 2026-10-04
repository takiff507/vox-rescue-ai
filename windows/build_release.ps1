[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$windowsRoot = $PSScriptRoot
$projectRoot = (Resolve-Path (Join-Path $windowsRoot "..")).Path
$driverRoot = Join-Path $windowsRoot "VoxRescueVirtualAudio"
$driverProject = Join-Path $driverRoot "TabletAudioSample\TabletAudioSample.vcxproj"
$endpointsProject = Join-Path $driverRoot "EndpointsCommon\EndpointsCommon.vcxproj"
$toolProject = Join-Path $windowsRoot "VoxRescueDeviceTool\VoxRescueDeviceTool.vcxproj"
$releaseRoot = Join-Path $windowsRoot "release"
$driverPackage = Join-Path $releaseRoot "driver\x64"
$toolsPackage = Join-Path $releaseRoot "tools\x64"

function Invoke-CleanTool {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory
    )

    $start = [System.Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $FilePath
    $start.WorkingDirectory = $WorkingDirectory
    $start.UseShellExecute = $false
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true

    # Codex/CI environments can expose both Path and PATH. MSBuild rejects
    # duplicate environment keys, so recreate one case-insensitive environment.
    $uniqueEnvironment =
        [System.Collections.Generic.SortedDictionary[string,string]]::new(
            [System.StringComparer]::OrdinalIgnoreCase
        )
    foreach ($entry in [System.Environment]::GetEnvironmentVariables().GetEnumerator()) {
        $key = [string]$entry.Key
        if ($key -ieq "PATH") {
            $key = "Path"
        }
        $uniqueEnvironment[$key] = [string]$entry.Value
    }
    $start.Environment.Clear()
    foreach ($entry in $uniqueEnvironment.GetEnumerator()) {
        $start.Environment[$entry.Key] = $entry.Value
    }
    foreach ($argument in $Arguments) {
        [void]$start.ArgumentList.Add($argument)
    }

    $process = [System.Diagnostics.Process]::Start($start)
    $standardOutput = $process.StandardOutput.ReadToEnd()
    $standardError = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    if ($standardOutput) {
        Write-Host $standardOutput.TrimEnd()
    }
    if ($standardError) {
        Write-Host $standardError.TrimEnd()
    }
    if ($process.ExitCode -ne 0) {
        throw "$(Split-Path $FilePath -Leaf) failed with exit code $($process.ExitCode)"
    }
}

$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (-not (Test-Path -LiteralPath $vswhere)) {
    throw "Visual Studio locator was not found"
}
$instances = & $vswhere -all -products * -format json | ConvertFrom-Json
$msbuild = $null
foreach ($instance in $instances) {
    $candidate = Join-Path $instance.installationPath "MSBuild\Current\Bin\amd64\MSBuild.exe"
    if (Test-Path -LiteralPath $candidate) {
        $msbuild = $candidate
        break
    }
}
if (-not $msbuild) {
    throw "A registered Visual Studio DriverKit x64 MSBuild installation was not found"
}

$kitsRoot = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots").KitsRoot10
$toolVersion = Get-ChildItem -LiteralPath (Join-Path $kitsRoot "Tools") -Directory |
    Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName "x64\infverif.exe") } |
    Sort-Object { [version]$_.Name } -Descending |
    Select-Object -First 1
if (-not $toolVersion) {
    throw "WDK InfVerif was not found"
}
$infVerif = Join-Path $toolVersion.FullName "x64\infverif.exe"
$inf2Cat = Join-Path $kitsRoot "bin\$($toolVersion.Name)\x86\Inf2Cat.exe"
if (-not (Test-Path -LiteralPath $inf2Cat)) {
    throw "WDK Inf2Cat was not found"
}

$commonBuildArguments = @(
    "/m",
    "/t:Build",
    "/p:Configuration=Release",
    "/p:Platform=x64",
    "/verbosity:minimal",
    "/nologo"
)
Invoke-CleanTool $msbuild (@($endpointsProject) + $commonBuildArguments) $projectRoot
Invoke-CleanTool $msbuild (@($driverProject) + $commonBuildArguments + "/p:SignMode=Off") $projectRoot
Invoke-CleanTool $msbuild (@($toolProject) + $commonBuildArguments) $projectRoot

$builtDriverDirectory = Join-Path $driverRoot "TabletAudioSample\x64\Release"
$builtInf = Join-Path $builtDriverDirectory "VoxRescueVirtualAudio.inf"
$builtSys = Join-Path $builtDriverDirectory "VoxRescueVirtualAudio.sys"
$builtTool = Join-Path $windowsRoot "VoxRescueDeviceTool\x64\Release\VoxRescueDeviceTool.exe"
foreach ($artifact in @($builtInf, $builtSys, $builtTool)) {
    if (-not (Test-Path -LiteralPath $artifact)) {
        throw "Expected release artifact was not created: $artifact"
    }
}

Invoke-CleanTool $infVerif @("/v", $builtInf) $projectRoot

New-Item -ItemType Directory -Path $driverPackage -Force | Out-Null
New-Item -ItemType Directory -Path $toolsPackage -Force | Out-Null
foreach ($fileName in @(
    "VoxRescueVirtualAudio.inf",
    "VoxRescueVirtualAudio.sys",
    "VoxRescueVirtualAudio.cat",
    "SHA256SUMS.txt"
)) {
    $target = Join-Path $driverPackage $fileName
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Force
    }
}
Copy-Item -LiteralPath $builtInf -Destination $driverPackage
Copy-Item -LiteralPath $builtSys -Destination $driverPackage
Copy-Item -LiteralPath (Join-Path $windowsRoot "driver-samples\LICENSE") `
    -Destination (Join-Path $driverPackage "LICENSE.microsoft.txt") -Force
Copy-Item -LiteralPath $builtTool -Destination $toolsPackage -Force
Copy-Item -LiteralPath (Join-Path $windowsRoot "VIRTUAL_MIC_RELEASE.md") `
    -Destination (Join-Path $releaseRoot "VIRTUAL_MIC_RELEASE.md") -Force

Invoke-CleanTool $inf2Cat @(
    "/driver:$driverPackage",
    "/os:10_X64,10_CO_X64,10_NI_X64,10_GE_X64",
    "/verbose"
) $projectRoot

$checksums = Get-ChildItem -LiteralPath $driverPackage -File |
    Where-Object { $_.Name -ne "SHA256SUMS.txt" } |
    Sort-Object Name |
    ForEach-Object {
        $hash = Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
        "$($hash.Hash)  $($_.Name)"
    }
$checksums | Set-Content -LiteralPath (Join-Path $driverPackage "SHA256SUMS.txt") -Encoding ascii

[pscustomobject]@{
    DriverPackage = $driverPackage
    DeviceTool = Join-Path $toolsPackage "VoxRescueDeviceTool.exe"
    DriverBytes = (Get-Item -LiteralPath (Join-Path $driverPackage "VoxRescueVirtualAudio.sys")).Length
    CatalogCreated = Test-Path -LiteralPath (Join-Path $driverPackage "VoxRescueVirtualAudio.cat")
    Signed = $false
}
