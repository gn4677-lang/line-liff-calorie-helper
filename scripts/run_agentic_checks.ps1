param(
    [string]$PythonExe = "C:\Users\exsaf\AppData\Local\Programs\Python\Python312\python.exe",
    [switch]$FullBackend,
    [switch]$IncludeFrontend,
    [switch]$Fast,
    [switch]$RequireRemoteLlmRuntime
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $PSScriptRoot

function Write-Step {
    param([string]$Message)

    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Read-DotEnv {
    param([string]$Path)

    $values = @{}
    if (-not (Test-Path $Path)) {
        return $values
    }

    foreach ($line in Get-Content $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }

        $parts = $trimmed -split "=", 2
        if ($parts.Count -ne 2) {
            continue
        }

        $values[$parts[0].Trim()] = $parts[1].Trim()
    }

    return $values
}

function Get-SettingValue {
    param(
        [hashtable]$DotEnv,
        [string]$Name
    )

    $fromProcess = [Environment]::GetEnvironmentVariable($Name)
    if (-not [string]::IsNullOrWhiteSpace($fromProcess)) {
        return $fromProcess
    }

    if ($DotEnv.ContainsKey($Name)) {
        return $DotEnv[$Name]
    }

    return $null
}

function Format-Presence {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return "missing"
    }

    return "present"
}

function Assert-Command {
    param([string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found on PATH."
    }
}

Push-Location $RepoRoot
try {
    $dotEnv = Read-DotEnv ".env"

    $aiProvider = Get-SettingValue -DotEnv $dotEnv -Name "AI_PROVIDER"
    $aiBuilderToken = Get-SettingValue -DotEnv $dotEnv -Name "AI_BUILDER_TOKEN"
    $googlePlacesApiKey = Get-SettingValue -DotEnv $dotEnv -Name "GOOGLE_PLACES_API_KEY"
    $lineChannelSecret = Get-SettingValue -DotEnv $dotEnv -Name "LINE_CHANNEL_SECRET"
    $lineChannelAccessToken = Get-SettingValue -DotEnv $dotEnv -Name "LINE_CHANNEL_ACCESS_TOKEN"
    $liffChannelId = Get-SettingValue -DotEnv $dotEnv -Name "LIFF_CHANNEL_ID"
    $supabaseUrl = Get-SettingValue -DotEnv $dotEnv -Name "SUPABASE_URL"
    $supabaseServiceRoleKey = Get-SettingValue -DotEnv $dotEnv -Name "SUPABASE_SERVICE_ROLE_KEY"

    $remoteLlmReady = ($aiProvider -eq "builderspace") -and -not [string]::IsNullOrWhiteSpace($aiBuilderToken)

    Write-Step "Agentic runtime snapshot"
    Write-Host ("AI_PROVIDER              : {0}" -f ($(if ([string]::IsNullOrWhiteSpace($aiProvider)) { "<unset>" } else { $aiProvider })))
    Write-Host ("Remote LLM runtime       : {0}" -f ($(if ($remoteLlmReady) { "ready" } else { "gated" })))
    Write-Host ("GOOGLE_PLACES_API_KEY    : {0}" -f (Format-Presence $googlePlacesApiKey))
    Write-Host ("LINE_CHANNEL_SECRET      : {0}" -f (Format-Presence $lineChannelSecret))
    Write-Host ("LINE_CHANNEL_ACCESS_TOKEN: {0}" -f (Format-Presence $lineChannelAccessToken))
    Write-Host ("LIFF_CHANNEL_ID          : {0}" -f (Format-Presence $liffChannelId))
    Write-Host ("SUPABASE_URL             : {0}" -f (Format-Presence $supabaseUrl))
    Write-Host ("SUPABASE_SERVICE_ROLE_KEY: {0}" -f (Format-Presence $supabaseServiceRoleKey))

    if ($RequireRemoteLlmRuntime -and -not $remoteLlmReady) {
        throw "Remote LLM runtime is gated. Set AI_PROVIDER=builderspace and provide AI_BUILDER_TOKEN before re-running with -RequireRemoteLlmRuntime."
    }

    Write-Step "Toolchain checks"
    Assert-Command "ffmpeg"
    Assert-Command "ffprobe"
    if (Get-Command "tesseract" -ErrorAction SilentlyContinue) {
        Write-Host "tesseract                : present"
    }
    else {
        Write-Host "tesseract                : optional / missing"
    }

    if (-not (Test-Path $PythonExe)) {
        throw "Python executable not found: $PythonExe"
    }

    if ($Fast) {
        Write-Step "Run pytest fast agentic suites"
        $fastTemp = "backend\.pytest_tmp_agentic_fast_" + [DateTime]::UtcNow.ToString("yyyyMMddHHmmssfff")
        $fastSuites = @(
            "backend\tests\test_llm_integration_wiring.py"
            "backend\tests\test_knowledge_packets.py"
            "backend\tests\test_confirmation_and_qa.py"
            "backend\tests\test_summary_and_recommendations.py"
            "backend\tests\test_video_intake.py"
            "backend\tests\test_observability_console.py"
            "backend\tests\test_observability_admin.py"
            "backend\tests\test_runtime_controls.py"
        )
        & $PythonExe -m pytest @fastSuites -q "--basetemp=$fastTemp"
        if ($LASTEXITCODE -ne 0) {
            throw "Fast agentic pytest suites failed."
        }
    }
    else {
        Write-Step "Run pytest agentic marker suite"
        $temp = "backend\.pytest_tmp_agentic_" + [DateTime]::UtcNow.ToString("yyyyMMddHHmmssfff")
        & $PythonExe -m pytest backend\tests -q -m agentic "--basetemp=$temp"
        if ($LASTEXITCODE -ne 0) {
            throw "Agentic pytest marker suite failed."
        }
    }

    if ($FullBackend) {
        Write-Step "Run full backend suite"
        $fullTemp = "backend\.pytest_tmp_agentic_full_" + [DateTime]::UtcNow.ToString("yyyyMMddHHmmssfff")
        & $PythonExe -m pytest backend\tests -q "--basetemp=$fullTemp"
        if ($LASTEXITCODE -ne 0) {
            throw "Full backend suite failed."
        }
    }

    if ($IncludeFrontend) {
        Write-Step "Run frontend quality checks"
        Push-Location (Join-Path $RepoRoot "frontend")
        try {
            & npm run build
            if ($LASTEXITCODE -ne 0) {
                throw "Frontend build failed."
            }

            & npm run lint
            if ($LASTEXITCODE -ne 0) {
                throw "Frontend lint failed."
            }

            & npm test
            if ($LASTEXITCODE -ne 0) {
                throw "Frontend tests failed."
            }
        }
        finally {
            Pop-Location
        }
    }

    Write-Step "Agentic checks passed"
    if (-not $remoteLlmReady) {
        Write-Warning "Code wiring and tests passed, but real remote LLM execution is still gated by configuration."
    }
}
finally {
    Pop-Location
}
