param(
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$project = Join-Path $root "CodexU.Windows\CodexU.Windows.csproj"

if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    throw "dotnet SDK was not found on PATH."
}

dotnet restore $project
dotnet build $project -c $Configuration --no-restore
