# Sets up whatever is missing for the ArduPilot workshop and starts the GCS. Safe to run again.
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/starbound-team/ardupilot-workshop/main/setup/start.ps1 | iex"
# Everything is in a function that runs on the last line, so a download cut short runs nothing.

function Start-Workshop {
    $ErrorActionPreference = "Stop"
    $StartPyUrl = "https://raw.githubusercontent.com/starbound-team/ardupilot-workshop/main/setup/start.py"
    $PythonVersion = "3.12"

    # 1. uv: installs Python and the packages without needing admin rights or any Python already installed
    $Uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
    if (-not $Uv -and (Test-Path "$HOME\.local\bin\uv.exe")) {
        $Uv = "$HOME\.local\bin\uv.exe"
    }
    if (-not $Uv) {
        Write-Host "[..] Installing uv (it gets Python for the GCS)"
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        $Uv = "$HOME\.local\bin\uv.exe"
    }
    Write-Host "[ok] uv: $Uv"

    # 2. start.py does the rest: next to this script, or in the workshop code, or downloaded
    if ($PSScriptRoot -and (Test-Path "$PSScriptRoot\start.py")) {
        $StartPy = "$PSScriptRoot\start.py"
    } elseif (Test-Path "$HOME\ardupilot-workshop\setup\start.py") {
        $StartPy = "$HOME\ardupilot-workshop\setup\start.py"
    } else {
        $Folder = Join-Path ([System.IO.Path]::GetTempPath()) "ardupilot-workshop-setup"
        New-Item -ItemType Directory -Force -Path $Folder | Out-Null
        $StartPy = "$Folder\start.py"
        Invoke-WebRequest -UseBasicParsing $StartPyUrl -OutFile $StartPy
    }
    & $Uv run --no-project --python $PythonVersion $StartPy @args
}

Start-Workshop @args
