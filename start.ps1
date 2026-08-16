# QuizForge ????(PowerShell)
# ??: ????????  .\start.ps1
# ??????? textual ? Python(py ??? / PATH / PYTHON_HOME),
# ???????????

Set-Location -LiteralPath $PSScriptRoot
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# ??? PYTHON_HOME(???????)
if ($env:PYTHON_HOME) { $env:PYTHON_HOME = $env:PYTHON_HOME.TrimEnd('\') }

# ??????????(???????)
function Test-PythonReady {
    param([string]$Exe, [string[]]$ExtraArgs = @())
    if ($ExtraArgs.Count -gt 0) {
        & $Exe @ExtraArgs -c "import textual, requests, bs4, qrcode, Crypto" 2>&1 | Out-Null
    } else {
        & $Exe -c "import textual, requests, bs4, qrcode, Crypto" 2>&1 | Out-Null
    }
    return $LASTEXITCODE -eq 0
}

$pyexe = $null
$pyargs = @()

# ?? 1: py ???
if (-not $pyexe -and (Get-Command py -ErrorAction SilentlyContinue)) {
    if (Test-PythonReady "py" @("-3")) { $pyexe = "py"; $pyargs = @("-3") }
}
# ?? 2: PATH ?? python
if (-not $pyexe -and (Get-Command python -ErrorAction SilentlyContinue)) {
    if (Test-PythonReady "python") { $pyexe = "python" }
}
# ?? 3: PYTHON_HOME ??????
if (-not $pyexe -and $env:PYTHON_HOME -and (Test-Path "$env:PYTHON_HOME\python.exe")) {
    if (Test-PythonReady "$env:PYTHON_HOME\python.exe") {
        $pyexe = "$env:PYTHON_HOME\python.exe"
    }
}
# ??: ?? Python(??????)
if (-not $pyexe) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $pyexe = "py"; $pyargs = @("-3")
    }
    elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $pyexe = "python"
    }
    elseif ($env:PYTHON_HOME -and (Test-Path "$env:PYTHON_HOME\python.exe")) {
        $pyexe = "$env:PYTHON_HOME\python.exe"
    }
}

if (-not $pyexe) {
    Write-Host "[??] ?????? Python ???,??? Python 3.10+ ????" -ForegroundColor Red
    Write-Host "?????: pip install -r requirements.txt ; python main.py"
    Read-Host "?????"
    exit 1
}

# ????(????????)
if (-not (Test-PythonReady $pyexe $pyargs)) {
    Write-Host "????,??????(textual requests beautifulsoup4 qrcode)..."
    & $pyexe @pyargs -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[??] ??????,?????????" -ForegroundColor Red
        Read-Host "?????"
        exit 1
    }
}

Write-Host "?????: $pyexe" -ForegroundColor Cyan
Write-Host "??: ???? Unicode ???(? Windows Terminal)???,? Ctrl+Q ???"
Write-Host ""
& $pyexe @pyargs main.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "??????,??????????" -ForegroundColor Red
    Read-Host "???????"
}