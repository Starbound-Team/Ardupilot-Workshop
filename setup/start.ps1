# Sets up whatever is missing for the ArduPilot workshop and starts the GCS. Safe to run again.
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/starbound-team/ardupilot-workshop/main/setup/start.ps1 | iex"
# From the organisers' laptop, without internet: the same with http://<their laptop>:8080/setup/start.ps1
# Everything is in a function that runs on the last line, so a download cut short runs nothing.

function Start-Workshop {
    $ErrorActionPreference = "Stop"
    $StartPyUrl = "https://raw.githubusercontent.com/starbound-team/ardupilot-workshop/main/setup/start.py"
    $PythonVersion = "3.12"
    # Set when this script came from the organisers' laptop: everything from there first, the internet if not there
    $Mirror = $env:WORKSHOP_MIRROR
    if ($Mirror) {
        $env:WORKSHOP_MIRROR = $Mirror # For start.py
    }

    # 1. uv: installs Python and the packages without needing admin rights or any Python already installed
    $Uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
    if (-not $Uv -and (Test-Path "$HOME\.local\bin\uv.exe")) {
        $Uv = "$HOME\.local\bin\uv.exe"
    }
    if (-not $Uv -and $Mirror) {
        Write-Host "[..] Installing uv from the organisers' laptop"
        try {
            $Zip = Join-Path ([System.IO.Path]::GetTempPath()) "uv-for-the-workshop.zip"
            Invoke-WebRequest -UseBasicParsing "$Mirror/uv/uv-x86_64-pc-windows-msvc.zip" -OutFile $Zip
            New-Item -ItemType Directory -Force -Path "$HOME\.local\bin" | Out-Null
            Expand-Archive -Force -Path $Zip -DestinationPath "$HOME\.local\bin"
            $Uv = "$HOME\.local\bin\uv.exe"
        } catch {
            Write-Host "[--] Not from the organisers' laptop ($_), from the internet instead"
        }
    }
    if (-not $Uv) {
        Write-Host "[..] Installing uv (it gets Python for the GCS)"
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        $Uv = "$HOME\.local\bin\uv.exe"
    }
    Write-Host "[ok] uv: $Uv"

    # 2. Python for the GCS: from the organisers' laptop if this laptop has none (otherwise uv gets it from the internet)
    if ($Mirror) {
        $ErrorActionPreference = "Continue" # A native program's messages mustn't stop the script here
        & $Uv python find $PythonVersion 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[..] Python $PythonVersion from the organisers' laptop"
            $env:UV_PYTHON_INSTALL_MIRROR = "$Mirror/python"
            & $Uv python install $PythonVersion
            Remove-Item Env:UV_PYTHON_INSTALL_MIRROR
        }
        $ErrorActionPreference = "Stop"
    }

    # 3. start.py does the rest: next to this script, or in the workshop code, or downloaded
    if ($PSScriptRoot -and (Test-Path "$PSScriptRoot\start.py")) {
        $StartPy = "$PSScriptRoot\start.py"
    } elseif (Test-Path "$HOME\ardupilot-workshop\setup\start.py") {
        $StartPy = "$HOME\ardupilot-workshop\setup\start.py"
    } else {
        $Folder = Join-Path ([System.IO.Path]::GetTempPath()) "ardupilot-workshop-setup"
        New-Item -ItemType Directory -Force -Path $Folder | Out-Null
        $StartPy = "$Folder\start.py"
        $Got = $false
        if ($Mirror) {
            try {
                Invoke-WebRequest -UseBasicParsing "$Mirror/start.py" -OutFile $StartPy
                $Got = $true
            } catch {
                Write-Host "[--] start.py not from the organisers' laptop, from the internet instead"
            }
        }
        if (-not $Got) {
            Invoke-WebRequest -UseBasicParsing $StartPyUrl -OutFile $StartPy
        }
    }
    & $Uv run --no-project --python $PythonVersion $StartPy @args
}

Start-Workshop @args
