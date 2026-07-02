param(
    [string]$Configuration = "Release",
    [string]$Runtime = "win-x64",
    [switch]$SelfContained
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$project = Join-Path $root "CodexU.Windows\CodexU.Windows.csproj"
$artifacts = Join-Path $root "artifacts"
$publishDir = Join-Path $artifacts "publish\$Runtime"
$mode = if ($SelfContained) { "self-contained" } else { "framework-dependent" }
$zipPath = Join-Path $artifacts "codexU-windows-$Runtime-$mode.zip"

if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    throw "dotnet SDK was not found on PATH."
}

New-Item -ItemType Directory -Force -Path $artifacts | Out-Null
if (Test-Path $publishDir) {
    Remove-Item -Recurse -Force $publishDir
}

dotnet publish $project `
    -c $Configuration `
    -r $Runtime `
    --self-contained:$($SelfContained.IsPresent.ToString().ToLowerInvariant()) `
    /p:PublishSingleFile=true `
    /p:IncludeNativeLibrariesForSelfExtract=true `
    -o $publishDir

if (Test-Path $zipPath) {
    Remove-Item -Force $zipPath
}

Compress-Archive -Path (Join-Path $publishDir "*") -DestinationPath $zipPath
Write-Host "Wrote $zipPath"
