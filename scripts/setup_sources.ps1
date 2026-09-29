$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
New-Item -ItemType Directory -Force -Path external,artifacts,data,models | Out-Null
function Get-PinnedSource([string]$url, [string]$folder, [string]$revision) {
    if (-not (Test-Path -LiteralPath $folder)) {
        git clone --no-checkout $url $folder
        if ($LASTEXITCODE -ne 0) { throw "Clone failed: $url" }
        git -C $folder checkout --detach $revision
        if ($LASTEXITCODE -ne 0) { throw "Checkout failed: $revision" }
    }
    $actual = git -C $folder rev-parse HEAD
    if ($actual -ne $revision) { throw "Existing source revision differs: $folder ($actual)" }
}
Get-PinnedSource 'https://github.com/Mapika/decider.git' 'external/decider' '23579f7a7e8f10e1045be492af3c1c05a005d67c'
Get-PinnedSource 'https://github.com/EE-zim/nrRRC_Simulator.git' 'external/nrrrc' '228ad4bc7ebce1093e215a9285ee126eb862ee95'
Write-Output 'PINNED_SOURCES_OK'
