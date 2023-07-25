$programFilesPath = "C:\Program Files"
$latestVersion = [Version]::Parse("0.0.0")
$latestDirectory = ""
$pythonScriptPath = Join-Path -Path $PSScriptRoot -ChildPath "run.py"

$directories = Get-ChildItem -Path $programFilesPath -Directory -Filter "QGIS *"
foreach ($directory in $directories) {
    $versionString = $directory.Name -replace "QGIS ", ""
    $version = [Version]::Parse($versionString)
    
    if ($version -gt $latestVersion) {
        $latestVersion = $version
        $latestDirectory = $directory.FullName
    }
}

if ($latestDirectory -ne "") {
    $pythonInterpreterPath = Join-Path -Path $latestDirectory -ChildPath "bin\python-qgis-ltr.bat"
    if (!(Test-Path $pythonInterpreterPath)) {
        $pythonInterpreterPath = Join-Path -Path $latestDirectory -ChildPath "bin\python-qgis.bat"
    }
    
    if (Test-Path $pythonInterpreterPath) {
        Write-Host "Starting process with QGIS $latestVersion ($pythonInterpreterPath, $pythonScriptPath)"
        Start-Process -FilePath $pythonInterpreterPath -ArgumentList $pythonScriptPath
    } else {
        Write-Host "Python script launcher not found in the latest QGIS directory."
    }
} else {
    Write-Host "No QGIS installations found in $programFilesPath."
}

