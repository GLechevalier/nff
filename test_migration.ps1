# test_migration.ps1  - Manual smoke-test for the Rust migration.
# Run from the repo root:  .\test_migration.ps1
# Add -Verbose to see full output from each command.
# Add -Sim to also run the wokwi simulation test (requires arduino-cli + wokwi-cli).
param(
    [switch]$Verbose,
    [switch]$Sim
)

$NFF = Join-Path $PSScriptRoot "nff-rs\target\release\nff.exe"
if (-not (Test-Path $NFF)) {
    Write-Host "Binary not found  - building release first..." -ForegroundColor Yellow
    Push-Location (Join-Path $PSScriptRoot "nff-rs")
    cargo build --release
    Pop-Location
}

$Pass = 0
$Fail = 0

function Test-Case {
    param([string]$Name, [scriptblock]$Body)
    try {
        & $Body
        Write-Host "  PASS  $Name" -ForegroundColor Green
        $script:Pass++
    } catch {
        Write-Host "  FAIL  $Name" -ForegroundColor Red
        Write-Host "        $_" -ForegroundColor DarkRed
        $script:Fail++
    }
}

function Assert-Contains { param($Text, $Pattern, $Msg)
    if ($Text -notmatch [regex]::Escape($Pattern)) { throw "$Msg`nExpected to contain: '$Pattern'`nActual:`n$Text" }
}

function Assert-True { param($Condition, $Msg)
    if (-not $Condition) { throw $Msg }
}

# ---- Temp workspace ---------------------------------------------------
$Tmp = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), "nff_smoke_$(Get-Random)")
New-Item -ItemType Directory -Path $Tmp | Out-Null

Write-Host "`n=== nff Migration Smoke Tests ===" -ForegroundColor Cyan

# -----------------------------------------------------------------------
Write-Host "`n--- Binary basics ---" -ForegroundColor Cyan

Test-Case "nff --version exits 0" {
    $out = & $NFF --version 2>&1
    Assert-True ($LASTEXITCODE -eq 0) "exit code $LASTEXITCODE"
    Assert-Contains ($out -join "`n") "0.2.16" "version string"
}

Test-Case "nff --help exits 0 and lists commands" {
    $out = & $NFF --help 2>&1 | Out-String
    Assert-True ($LASTEXITCODE -eq 0) "exit code $LASTEXITCODE"
    foreach ($cmd in @("init","flash","monitor","doctor","wokwi","mcp","install-deps")) {
        Assert-Contains $out $cmd "command '$cmd' missing from --help"
    }
}

Test-Case "python -m nff --version proxies to Rust binary" {
    $out = python -m nff --version 2>&1 | Out-String
    Assert-Contains $out "0.2.16" "python -m nff should proxy to Rust binary"
}

Test-Case "unknown command exits non-zero" {
    & $NFF definitely-not-a-command 2>&1 | Out-Null
    Assert-True ($LASTEXITCODE -ne 0) "should exit non-zero"
}

# -----------------------------------------------------------------------
Write-Host "`n--- doctor ---" -ForegroundColor Cyan

Test-Case "nff doctor produces output and does not crash" {
    $out = & $NFF doctor 2>&1 | Out-String
    Assert-True ($out.Trim().Length -gt 0) "doctor produced no output"
}

# -----------------------------------------------------------------------
Write-Host "`n--- wokwi init (no hardware needed) ---" -ForegroundColor Cyan

Test-Case "wokwi init creates diagram.json for Arduino Uno" {
    $d = Join-Path $Tmp "uno_init"
    New-Item -ItemType Directory $d | Out-Null
    & $NFF wokwi init --board arduino:avr:uno 2>&1 | Out-Null
    # Run from $d
    Push-Location $d
    & $NFF wokwi init --board arduino:avr:uno 2>&1 | Out-Null
    Pop-Location
    Assert-True (Test-Path "$d\diagram.json") "diagram.json not created"
    $j = Get-Content "$d\diagram.json" | ConvertFrom-Json
    Assert-Contains ($j.parts[0].type) "wokwi-arduino-uno" "wrong chip type"
}

Test-Case "wokwi init creates wokwi.toml for Arduino Uno" {
    $d = Join-Path $Tmp "uno_toml"
    New-Item -ItemType Directory $d | Out-Null
    Push-Location $d
    & $NFF wokwi init --board arduino:avr:uno 2>&1 | Out-Null
    Pop-Location
    Assert-True (Test-Path "$d\wokwi.toml") "wokwi.toml not created"
    $t = Get-Content "$d\wokwi.toml" -Raw
    Assert-Contains $t "[wokwi]" "missing [wokwi] header"
    Assert-Contains $t "arduino.avr.uno" "missing FQBN in elf path"
}

Test-Case "wokwi init creates diagram.json for ESP32" {
    $d = Join-Path $Tmp "esp32_init"
    New-Item -ItemType Directory $d | Out-Null
    Push-Location $d
    & $NFF wokwi init --board esp32:esp32:esp32 2>&1 | Out-Null
    Pop-Location
    $j = Get-Content "$d\diagram.json" | ConvertFrom-Json
    Assert-Contains ($j.parts[0].type) "wokwi-esp32-devkit-v1" "wrong chip for ESP32"
}

Test-Case "wokwi init fails cleanly for unsupported board" {
    $d = Join-Path $Tmp "bad_board"
    New-Item -ItemType Directory $d | Out-Null
    Push-Location $d
    & $NFF wokwi init --board bad:board:fqbn 2>&1 | Out-Null
    $code = $LASTEXITCODE
    Pop-Location
    Assert-True ($code -ne 0) "should exit non-zero for unsupported board"
}

Test-Case "wokwi run fails with clear message when no wokwi.toml" {
    $d = Join-Path $Tmp "no_toml"
    New-Item -ItemType Directory $d | Out-Null
    Push-Location $d
    $out = & $NFF wokwi run 2>&1 | Out-String
    Pop-Location
    Assert-Contains $out "wokwi.toml" "should mention wokwi.toml"
}

# -----------------------------------------------------------------------
Write-Host "`n--- MCP server (JSON-RPC over stdio) ---" -ForegroundColor Cyan

function Invoke-Mcp {
    param([string[]]$Messages)
    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo.FileName = $NFF
    $proc.StartInfo.Arguments = "mcp"
    $proc.StartInfo.RedirectStandardInput = $true
    $proc.StartInfo.RedirectStandardOutput = $true
    $proc.StartInfo.RedirectStandardError = $true
    $proc.StartInfo.UseShellExecute = $false
    $null = $proc.Start()
    $enc = [System.Text.Encoding]::UTF8
    foreach ($msg in $Messages) {
        $bytes = $enc.GetBytes($msg + "`n")
        $proc.StandardInput.BaseStream.Write($bytes, 0, $bytes.Length)
    }
    $proc.StandardInput.BaseStream.Flush()
    $proc.StandardInput.Close()
    $stdout = $proc.StandardOutput.ReadToEnd()
    $proc.WaitForExit(5000) | Out-Null
    return $stdout
}

$INIT_MSG = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0"}}}'
$INIT_NOTIF = '{"jsonrpc":"2.0","method":"notifications/initialized"}'
$LIST_TOOLS = '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'

Test-Case "MCP initialize returns valid JSON" {
    $out = Invoke-Mcp @($INIT_MSG)
    $parsed = $null
    foreach ($line in ($out -split "`n")) {
        if ($line.Trim() -eq "") { continue }
        try { $parsed = $line | ConvertFrom-Json; break } catch {}
    }
    Assert-True ($null -ne $parsed) "no valid JSON in MCP output: $out"
}

Test-Case "MCP stdout contains only JSON lines (no stray print)" {
    $out = Invoke-Mcp @($INIT_MSG)
    foreach ($line in ($out -split "`n")) {
        if ($line.Trim() -eq "") { continue }
        try { $null = $line | ConvertFrom-Json }
        catch { throw "Non-JSON line would corrupt MCP framing: '$line'" }
    }
}

Test-Case "MCP tools/list returns all 9 expected tools" {
    $out = Invoke-Mcp @($INIT_MSG, $INIT_NOTIF, $LIST_TOOLS)
    $tools = @("list_devices","flash","serial_read","serial_write","reset_device",
               "get_device_info","wokwi_flash","wokwi_serial_read","wokwi_get_diagram")
    foreach ($t in $tools) {
        Assert-Contains $out $t "tool '$t' missing from tools/list"
    }
}

Test-Case "MCP tools/list has exactly 9 tools" {
    $out = Invoke-Mcp @($INIT_MSG, $INIT_NOTIF, $LIST_TOOLS)
    $listResp = $out -split "`n" | Where-Object { $_ -match '"id":2' } | Select-Object -First 1
    $parsed = $listResp | ConvertFrom-Json
    $count = $parsed.result.tools.Count
    Assert-True ($count -eq 9) "expected 9 tools, got $count"
}

Test-Case "MCP call list_devices returns devices array" {
    $call = '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"list_devices","arguments":{}}}'
    $out = Invoke-Mcp @($INIT_MSG, $INIT_NOTIF, $call)
    $resp = $out -split "`n" | Where-Object { $_ -match '"id":3' } | Select-Object -First 1
    $parsed = $resp | ConvertFrom-Json
    $text = $parsed.result.content[0].text
    $data = $text | ConvertFrom-Json
    Assert-True ($null -ne $data.devices) "list_devices response should have 'devices' key"
    Assert-True ($data.devices -is [array]) "'devices' should be an array"
}

Test-Case "MCP call wokwi_get_diagram for arduino:avr:uno" {
    $call = '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"wokwi_get_diagram","arguments":{"board":"arduino:avr:uno"}}}'
    $out = Invoke-Mcp @($INIT_MSG, $INIT_NOTIF, $call)
    $resp = $out -split "`n" | Where-Object { $_ -match '"id":3' } | Select-Object -First 1
    $parsed = $resp | ConvertFrom-Json
    $text = $parsed.result.content[0].text
    $diagram = $text | ConvertFrom-Json
    Assert-Contains ($diagram.parts[0].type) "wokwi-arduino-uno" "wrong chip type"
    Assert-True ($diagram.version -eq 1) "version should be 1"
}

Test-Case "MCP call wokwi_get_diagram unsupported board returns ERROR:" {
    $call = '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"wokwi_get_diagram","arguments":{"board":"not:a:board"}}}'
    $out = Invoke-Mcp @($INIT_MSG, $INIT_NOTIF, $call)
    $resp = $out -split "`n" | Where-Object { $_ -match '"id":3' } | Select-Object -First 1
    $parsed = $resp | ConvertFrom-Json
    $text = $parsed.result.content[0].text
    Assert-True ($text.StartsWith("ERROR:")) "should start with ERROR: got: $text"
}

# -----------------------------------------------------------------------
if ($Sim) {
    Write-Host "`n--- Simulation (arduino-cli + wokwi-cli required) ---" -ForegroundColor Cyan

    Test-Case "nff flash --sim compiles and simulates blink" {
        $d = Join-Path $Tmp "sim_blink"
        $sketch = Join-Path $d "blink"
        New-Item -ItemType Directory $sketch | Out-Null
        Set-Content "$sketch\blink.ino" @'
void setup() { Serial.begin(9600); }
void loop() { Serial.println("tick"); delay(500); }
'@
        $out = & $NFF flash --sim $sketch --board arduino:avr:uno --sim-timeout 3000 2>&1 | Out-String
        Assert-True ($LASTEXITCODE -eq 0) "simulation failed (exit $LASTEXITCODE):`n$out"
    }

    Test-Case "MCP wokwi_flash returns serial_output" {
        $code = 'void setup(){Serial.begin(9600);} void loop(){Serial.println(42);delay(500);}'
        $call = [PSCustomObject]@{
            jsonrpc = '2.0'; id = 3; method = 'tools/call'
            params  = [PSCustomObject]@{
                name      = 'wokwi_flash'
                arguments = [PSCustomObject]@{ code = $code; board = 'arduino:avr:uno'; timeout_ms = 3000 }
            }
        } | ConvertTo-Json -Compress -Depth 5
        $out = Invoke-Mcp @($INIT_MSG, $INIT_NOTIF, $call)
        Assert-Contains $out "serial_output" "wokwi_flash response missing serial_output"
    }
}

# -----------------------------------------------------------------------
Write-Host "`n--- Python package check ---" -ForegroundColor Cyan

Test-Case "No stray Python imports remain in nff package" {
    # Verify none of the deleted modules are importable
    $deleted = @("nff.config","nff.cli","nff.mcp_server",
                 "nff.tools.boards","nff.tools.serial","nff.tools.toolchain",
                 "nff.tools.wokwi","nff.commands.flash","nff.commands.wokwi")
    foreach ($mod in $deleted) {
        $result = python -c "import $mod" 2>&1
        Assert-True ($LASTEXITCODE -ne 0) "module '$mod' should not be importable after migration"
    }
}

Test-Case "nff.__init__ is importable and has __version__" {
    $ver = python -c "import nff; print(nff.__version__)" 2>&1
    Assert-Contains ($ver -join "") "0.2.16" "__version__ mismatch"
}

# -----------------------------------------------------------------------
Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue

Write-Host ""
Write-Host ("=" * 40) -ForegroundColor Cyan
$total = $Pass + $Fail
if ($Fail -eq 0) {
    Write-Host "  ALL $total TESTS PASSED" -ForegroundColor Green
} else {
    Write-Host "  $Pass/$total passed, $Fail FAILED" -ForegroundColor Red
}
Write-Host ("=" * 40) -ForegroundColor Cyan
Write-Host ""
if ($Fail -gt 0) { exit 1 }
