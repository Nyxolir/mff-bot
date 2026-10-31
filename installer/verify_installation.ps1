param([Parameter(Mandatory=$true)][string]$Installer,[Parameter(Mandatory=$true)][string]$WorkRoot)
$ErrorActionPreference = 'Stop'
$base = [IO.Path]::GetFullPath($WorkRoot)
$installPath = [IO.Path]::GetFullPath((Join-Path $base 'installed app'))
if (!$installPath.StartsWith($base + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Smoke installation must stay inside its work directory' }
if (Test-Path -LiteralPath $installPath) { throw 'Use a fresh work directory for installer validation' }
$uninstallKey = 'HKCU:/Software/Microsoft/Windows/CurrentVersion/Uninstall/{265CBA4C-EC58-4BC0-9E83-6DDD0C35DA44}_is1'
if (Test-Path -LiteralPath $uninstallKey) { throw 'An installed MFF Bot already exists; do not replace it for a smoke test' }
New-Item -ItemType Directory -Force -Path $base | Out-Null
$smokeProfile = Join-Path $base 'isolated profile'
$env:MFF_DATA_DIR = $smokeProfile
$env:QT_QPA_PLATFORM = 'offscreen'
function Get-SmokeHash([string]$Path) {
    $stream = [IO.File]::OpenRead($Path)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-','') }
    finally { $stream.Dispose(); $algorithm.Dispose() }
}
function Install-SmokeCopy {
    $installLog = Join-Path $base ('setup-' + [Guid]::NewGuid().ToString('N') + '.log')
    $run = Start-Process -FilePath $Installer -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/NOICONS',('/DIR="' + $installPath + '"'),('/LOG="' + $installLog + '"')) -WindowStyle Hidden -Wait -PassThru
    if ($run.ExitCode -ne 0 -and (Test-Path -LiteralPath $installLog)) { Get-Content -LiteralPath $installLog -Tail 35 | Write-Output }
    if ($run.ExitCode -ne 0) { throw ('Silent installer failed: ' + $run.ExitCode) }
}
Install-SmokeCopy
$application = Join-Path $installPath 'MFF Bot.exe'
$reportPath = Join-Path $base 'installed-selftest.json'
$appRun = Start-Process -FilePath $application -ArgumentList @('--self-test',('"' + $reportPath + '"')) -WindowStyle Hidden -Wait -PassThru
if ($appRun.ExitCode -ne 0 -or !(Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json).passed) { throw 'Installed application self-test failed' }
$pending = Join-Path $smokeProfile 'settings/gui/pending-clear.json'
$answers = Join-Path $smokeProfile 'settings/gui/trivia-answers.json'
[IO.File]::WriteAllText($pending,'{"pending":["installer-preservation-sentinel"]}')
[IO.File]::WriteAllText($answers,'{"version":1,"answers":{"A local installer preservation question?":"Preserved"}}')
$pendingHash = Get-SmokeHash $pending
$answersHash = Get-SmokeHash $answers
Install-SmokeCopy
if ((Get-SmokeHash $pending) -ne $pendingHash -or (Get-SmokeHash $answers) -ne $answersHash) { throw 'Upgrade changed local user data' }
# Exercise the real GUI -> copied helper -> silent installer -> offline check
# -> restarted app flow. The synthetic queue records resume intent only; no
# emulator is connected and the probe exits before any queue can start.
[IO.File]::WriteAllText($pending,'{"pending":null,"updater_preservation_sentinel":true}')
$pendingHash = Get-SmokeHash $pending
$buildInfo = Join-Path $installPath '_internal/build-info.json'
$versionInfo = Get-Content -LiteralPath $buildInfo -Raw | ConvertFrom-Json
$updateVersion = $versionInfo.version
$versionInfo.version = '0.0.0'
[IO.File]::WriteAllText($buildInfo,($versionInfo | ConvertTo-Json))
$updateRequest = Join-Path $base 'update-selftest-request.json'
[IO.File]::WriteAllText($updateRequest,(@{version=$updateVersion;installer=[IO.Path]::GetFullPath($Installer);resume=$true} | ConvertTo-Json))
$env:MFF_UPDATER_SELFTEST = '1'
$handoff = Start-Process -FilePath $application -ArgumentList @('--update-self-test',('"' + $updateRequest + '"')) -WindowStyle Hidden -PassThru
if (!$handoff.WaitForExit(90000) -or $handoff.ExitCode -ne 0) { throw 'Update GUI did not exit through its verified handoff' }
$updateJob = Join-Path $smokeProfile ('.cache/updates/' + $updateVersion)
$probe = Join-Path $updateJob 'resume-probe.json'
$deadline = [DateTime]::UtcNow.AddSeconds(240)
while (!(Test-Path -LiteralPath $probe) -and [DateTime]::UtcNow -lt $deadline) {
    $resultFile = Join-Path $updateJob 'result.json'
    if (Test-Path -LiteralPath $resultFile) {
        $updateResult = Get-Content -LiteralPath $resultFile -Raw | ConvertFrom-Json
        if ($updateResult.stage -eq 'failed') { throw ('Updater helper failed: ' + $updateResult.error) }
    }
    Start-Sleep -Milliseconds 250
}
if (!(Test-Path -LiteralPath $probe)) { throw 'Updated app did not return its resume probe' }
$probeResult = Get-Content -LiteralPath $probe -Raw | ConvertFrom-Json
if (!$probeResult.passed -or !$probeResult.resume -or !$probeResult.connected -or $probeResult.queue_index -ne 2 -or $probeResult.version -ne $updateVersion -or $probeResult.game_connected -or $probeResult.queue_started) { throw 'Updated app resume intent/version did not verify offline' }
if ((Get-SmokeHash $pending) -ne $pendingHash -or (Get-SmokeHash $answers) -ne $answersHash) { throw 'Automatic update changed saved user data' }
Remove-Item Env:MFF_UPDATER_SELFTEST
$uninstaller = Join-Path $installPath 'unins000.exe'
if (![IO.Path]::GetFullPath($uninstaller).StartsWith($installPath + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected uninstaller location' }
$remove = Start-Process -FilePath $uninstaller -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART') -WindowStyle Hidden -Wait -PassThru
if ($remove.ExitCode -ne 0 -or (Test-Path -LiteralPath $application)) { throw 'Uninstall did not remove the installed application' }
if ((Get-SmokeHash $pending) -ne $pendingHash -or (Get-SmokeHash $answers) -ne $answersHash) { throw 'Uninstall changed local user data' }
$evidence = @{passed=$true;installed_ocr=$true;upgrade_preserved_pending=$true;upgrade_preserved_answers=$true;uninstall_preserved_data=$true;automatic_update_handoff=$true;automatic_update_resume_intent=$true;automatic_update_preserved_data=$true;game_connected=$false}
[IO.File]::WriteAllText((Join-Path $base 'installer-validation.json'),($evidence | ConvertTo-Json))
$evidence | ConvertTo-Json -Compress
