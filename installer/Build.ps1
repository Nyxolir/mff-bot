param(
    [string]$Version = '0.1.0',
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$toolsRoot = Join-Path $projectRoot 'build/tools'
New-Item -ItemType Directory -Force -Path $toolsRoot | Out-Null
$inputs = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'runtime-inputs.json') -Raw | ConvertFrom-Json
function Get-VerifiedDownload($Metadata, $Target) {
    if (!(Test-Path -LiteralPath $Target)) { Invoke-WebRequest -Uri $Metadata.url -OutFile $Target }
    $digest = (Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($digest -ne $Metadata.sha256) { throw ('Downloaded input hash mismatch: ' + (Split-Path -Leaf $Target)) }
}
$nodeZip = Join-Path $toolsRoot 'node-runtime.zip'
Get-VerifiedDownload $inputs.node $nodeZip
$nodeRoot = Join-Path $toolsRoot ('node-v' + $inputs.node.version + '-win-x64')
if (!(Test-Path -LiteralPath (Join-Path $nodeRoot 'node.exe'))) { Expand-Archive -LiteralPath $nodeZip -DestinationPath $toolsRoot }
$compilerSetup = Join-Path $toolsRoot 'inno-setup.exe'
Get-VerifiedDownload $inputs.inno $compilerSetup
$compilerRoot = Join-Path $toolsRoot 'inno'
if (!(Test-Path -LiteralPath (Join-Path $compilerRoot 'ISCC.exe'))) {
    $signature = Get-AuthenticodeSignature -LiteralPath $compilerSetup
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Pyrsys') { throw 'Inno compiler signature did not verify' }
    $install = Start-Process -FilePath $compilerSetup -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CURRENTUSER','/NOICONS',('/DIR="' + $compilerRoot + '"')) -WindowStyle Hidden -Wait -PassThru
    if ($install.ExitCode -ne 0) { throw 'Inno compiler setup failed' }
}
$compressedModel = Join-Path $toolsRoot 'eng.traineddata.gz'
Get-VerifiedDownload $inputs.english_model $compressedModel
$model = Join-Path $toolsRoot 'eng.traineddata'
if (!(Test-Path -LiteralPath $model)) {
    $inputStream = [IO.File]::OpenRead($compressedModel)
    $gzipStream = [IO.Compression.GzipStream]::new($inputStream,[IO.Compression.CompressionMode]::Decompress)
    $outputStream = [IO.File]::Create($model)
    try { $gzipStream.CopyTo($outputStream) } finally { $outputStream.Dispose(); $gzipStream.Dispose(); $inputStream.Dispose() }
}
if ((Get-FileHash -LiteralPath $model -Algorithm SHA256).Hash.ToLowerInvariant() -ne $inputs.english_model.uncompressed_sha256) { throw 'English model hash mismatch' }
& $Python -m pip install -r (Join-Path $PSScriptRoot 'requirements-build.txt')
if ($LASTEXITCODE -ne 0) { throw 'Build dependencies failed' }
& (Join-Path $nodeRoot 'npm.cmd') ci --prefix (Join-Path $PSScriptRoot 'ocr') --ignore-scripts --omit=dev
if ($LASTEXITCODE -ne 0) { throw 'Pinned OCR dependencies failed' }
& $Python (Join-Path $projectRoot 'build.py') --version $Version --node (Join-Path $nodeRoot 'node.exe') --model $model --iscc (Join-Path $compilerRoot 'ISCC.exe')
if ($LASTEXITCODE -ne 0) { throw 'Installer build or validation failed' }
