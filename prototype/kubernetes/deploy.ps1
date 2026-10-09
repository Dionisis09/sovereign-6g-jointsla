param([switch]$SkipBuild, [switch]$Validate)
$ErrorActionPreference = 'Stop'
$repoPath = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Push-Location $repoPath
try {
    $runtimePath = Join-Path $repoPath '.cache/infra-venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $runtimePath)) {
        $projectPython = Join-Path $repoPath '.venv/Scripts/python.exe'
        if (Test-Path -LiteralPath $projectPython) {
            & $projectPython -m venv .cache/infra-venv
        } else {
            py -3.12 -m venv .cache/infra-venv
        }
        if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 with the py launcher.' }
    }
    & $runtimePath -m pip install --disable-pip-version-check -r prototype/requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Infrastructure dependency installation failed.' }
    $arguments = @('-m', 'prototype.kubernetes.deploy')
    if ($SkipBuild) { $arguments += '--skip-build' }
    if ($Validate) { $arguments += '--validate' }
    & $runtimePath @arguments
    if ($LASTEXITCODE -ne 0) { throw 'Deployment/validation failed; inspect the output above.' }
} finally { Pop-Location }
