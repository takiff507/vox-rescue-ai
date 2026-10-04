[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$project = Join-Path $PSScriptRoot "model_guard.vcxproj"
$generatedHeader = Join-Path $PSScriptRoot "model_key.generated.h"
$msbuild = "C:\Program Files\Microsoft Visual Studio\18\VoxDriverKit\MSBuild\Current\Bin\amd64\MSBuild.exe"
if (-not (Test-Path -LiteralPath $generatedHeader)) {
    throw "Generated model key header is missing: $generatedHeader"
}
if (-not (Test-Path -LiteralPath $msbuild)) {
    throw "MSBuild was not found: $msbuild"
}

$pythonExecutable = (Get-Command python -ErrorAction Stop).Source
$pythonRoot = Split-Path -Parent $pythonExecutable
if (-not (Test-Path -LiteralPath (Join-Path $pythonRoot "include\Python.h"))) {
    throw "Python development headers were not found below $pythonRoot"
}

$arguments = @(
    $project,
    "/m",
    "/nologo",
    "/v:minimal",
    "/p:Configuration=Release",
    "/p:Platform=x64",
    "/p:PythonRoot=$pythonRoot"
)
$start = [System.Diagnostics.ProcessStartInfo]::new()
$start.FileName = $msbuild
$start.UseShellExecute = $false
$start.RedirectStandardOutput = $true
$start.RedirectStandardError = $true
$start.CreateNoWindow = $true
foreach ($argument in $arguments) {
    [void]$start.ArgumentList.Add($argument)
}

$cleanEnvironment = [System.Collections.Generic.SortedDictionary[string,string]]::new(
    [System.StringComparer]::OrdinalIgnoreCase
)
foreach ($entry in Get-ChildItem Env:) {
    $cleanEnvironment[$entry.Name] = $entry.Value
}
$start.Environment.Clear()
foreach ($entry in $cleanEnvironment.GetEnumerator()) {
    $start.Environment[$entry.Key] = $entry.Value
}

$process = [System.Diagnostics.Process]::new()
$process.StartInfo = $start
[void]$process.Start()
$stdout = $process.StandardOutput.ReadToEnd()
$stderr = $process.StandardError.ReadToEnd()
$process.WaitForExit()
if ($stdout) { Write-Output $stdout.TrimEnd() }
if ($stderr) { Write-Error $stderr.TrimEnd() }
if ($process.ExitCode -ne 0) {
    throw "Native model guard build failed with exit code $($process.ExitCode)"
}

$output = Join-Path $PSScriptRoot "x64\Release\model_guard.pyd"
if (-not (Test-Path -LiteralPath $output)) {
    throw "Native model guard output is missing: $output"
}
Get-Item -LiteralPath $output | Select-Object FullName, Length
