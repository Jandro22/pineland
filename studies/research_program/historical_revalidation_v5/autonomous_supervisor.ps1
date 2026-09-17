param([int]$Hours = 3)

$ErrorActionPreference = 'Continue'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$out = $PSScriptRoot
$py = 'C:\Python314\python.exe'
$scripts = Join-Path $root 'studies\research_program\scripts'
$statusPath = Join-Path $out 'status.json'
$logPath = Join-Path $out 'autonomous_supervisor.log'
$end = (Get-Date).AddHours($Hours)
$coordMiss = 0
$watchMiss = 0
$completedSeenAt = $null
$nextHeartbeat = Get-Date

function Log([string]$message) {
    $line = "$(Get-Date -Format o) $message"
    Add-Content -Path $logPath -Value $line -Encoding UTF8
    Write-Output $line
}

function MatchingProcesses([string]$needle) {
    @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine.Contains($needle) }
    )
}

function StartHiddenPython(
    [string]$script,
    [string[]]$arguments,
    [string]$stdout,
    [string]$stderr
) {
    $allArgs = @($script) + $arguments
    Start-Process -FilePath $py -ArgumentList $allArgs -WorkingDirectory $root `
        -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr `
        -PassThru
}

function FreeRamGB() {
    $os = Get-CimInstance Win32_OperatingSystem
    [double]$os.FreePhysicalMemory * 1KB / 1GB
}

function EnsureSyntheticJob(
    [string]$label,
    [string]$outputRelative,
    [string[]]$arguments
) {
    $outputPath = Join-Path $root $outputRelative
    $marker = Join-Path $out ("synthetic_retry_" + $label + ".marker")
    if (Test-Path $outputPath) { return }
    if (@(MatchingProcesses([IO.Path]::GetFileName($outputPath))).Count -gt 0) { return }
    if (Test-Path $marker) { return }
    if ((FreeRamGB) -lt 5.0) { return }
    $runner = Join-Path $scripts 'run_spatial_factorial_pilot.py'
    $stdout = Join-Path $out ("synthetic_retry_" + $label + ".stdout.log")
    $stderr = Join-Path $out ("synthetic_retry_" + $label + ".stderr.log")
    try {
        $p = StartHiddenPython $runner $arguments $stdout $stderr
        "pid=$($p.Id) started=$(Get-Date -Format o)" | Set-Content $marker -Encoding UTF8
        Log("restarted synthetic job $label pid=$($p.Id)")
    } catch {
        Log("failed to restart synthetic job ${label}: $($_.Exception.Message)")
    }
}

Log("autonomous supervisor armed for $Hours hours; historical contract remains authoritative")

while ((Get-Date) -lt $end) {
    if (-not (Test-Path $statusPath)) {
        Log('status.json missing; no destructive action taken')
        Start-Sleep -Seconds 30
        continue
    }

    try {
        $state = Get-Content $statusPath -Raw | ConvertFrom-Json
    } catch {
        Log("could not parse status.json: $($_.Exception.Message)")
        Start-Sleep -Seconds 30
        continue
    }

    if ((Get-Date) -ge $nextHeartbeat) {
        $free = [math]::Round((FreeRamGB), 1)
        $coordCount = @(MatchingProcesses('run_v5_historical_confrontation.py')).Count
        $watchCount = @(MatchingProcesses('watch_v5_historical_confrontation.py')).Count
        Log("heartbeat status=$($state.status) stage=$($state.current_stage) completed=$($state.completed_stages.Count) free_ram_gb=$free coordinators=$coordCount watchers=$watchCount")
        $nextHeartbeat = (Get-Date).AddMinutes(2)
    }

    if ($state.status -eq 'running') {
        $coordinators = @(MatchingProcesses('run_v5_historical_confrontation.py'))
        if ($coordinators.Count -eq 0) { $coordMiss++ } else { $coordMiss = 0 }
        if ($coordMiss -ge 2) {
            try {
                $runner = Join-Path $scripts 'run_v5_historical_confrontation.py'
                $stdout = Join-Path $out 'autonomous_resumed_coordinator.stdout.log'
                $stderr = Join-Path $out 'autonomous_resumed_coordinator.stderr.log'
                $p = StartHiddenPython $runner @() $stdout $stderr
                Log("historical coordinator absent for two checks; resumed pid=$($p.Id)")
            } catch {
                Log("historical coordinator resume failed: $($_.Exception.Message)")
            }
            $coordMiss = 0
        }

        $watchers = @(MatchingProcesses('watch_v5_historical_confrontation.py'))
        if ($watchers.Count -eq 0) { $watchMiss++ } else { $watchMiss = 0 }
        if ($watchMiss -ge 4) {
            try {
                $watcher = Join-Path $scripts 'watch_v5_historical_confrontation.py'
                $stdout = Join-Path $out 'autonomous_resumed_watcher.stdout.log'
                $stderr = Join-Path $out 'autonomous_resumed_watcher.stderr.log'
                $p = StartHiddenPython $watcher @() $stdout $stderr
                Log("readout watcher absent for four checks; resumed pid=$($p.Id)")
            } catch {
                Log("readout watcher resume failed: $($_.Exception.Message)")
            }
            $watchMiss = 0
        }
    }

    if ($state.status -eq 'failed') {
        Log("primary historical confrontation recorded failure at stage=$($state.current_stage); preserving failure and refusing automatic scientific retry")
    }

    EnsureSyntheticJob `
        'spatial_full' `
        'studies\research_program\spatial_factorial_full_v5_20260905.json' `
        @('--full','--output','studies\research_program\spatial_factorial_full_v5_20260905.json')
    EnsureSyntheticJob `
        'contact_full' `
        'studies\research_program\spatial_factorial_contact_challenge_full_v5_20260905.json' `
        @('--full','--challenge','--output','studies\research_program\spatial_factorial_contact_challenge_full_v5_20260905.json')

    if ($state.status -eq 'completed') {
        if ($null -eq $completedSeenAt) {
            $completedSeenAt = Get-Date
            Log('primary historical computation completed; allowing existing post-completion helper to finalize first')
        }
        $gate = Join-Path $out 'historical_confrontation_gate.json'
        if (-not (Test-Path $gate) -and ((Get-Date) - $completedSeenAt).TotalSeconds -ge 120) {
            Log('final gate still missing after grace period; running read-only diagnosis/finalization fallback')
            $env:PYTHONPATH = Join-Path $root 'src'
            $afgDiag = Join-Path $out 'afghanistan_theory_diagnosis.json'
            if (-not (Test-Path $afgDiag)) {
                & $py (Join-Path $scripts 'diagnose_v5_afghanistan_confrontation.py') *> (Join-Path $out 'autonomous_afghanistan_diagnosis.log')
                Log("Afghanistan diagnostic fallback rc=$LASTEXITCODE")
            }
            if (Test-Path $afgDiag) {
                & $py (Join-Path $scripts 'finalize_v5_historical_confrontation.py') *> (Join-Path $out 'autonomous_finalize.log')
                Log("historical finalizer fallback rc=$LASTEXITCODE")
            }
        }

        if ((Test-Path $gate) -and -not (Test-Path (Join-Path $out 'post_gate_audit.marker'))) {
            $auditDir = Join-Path $out 'post_gate_audit'
            New-Item -ItemType Directory -Force -Path $auditDir | Out-Null
            $env:PYTHONPATH = Join-Path $root 'src'
            & $py (Join-Path $scripts 'validate_estimand_registry.py') *> (Join-Path $auditDir 'estimand_registry_validation.log')
            $estimandRc = $LASTEXITCODE
            & $py (Join-Path $scripts 'build_paper_prerequisite_status.py') `
                --output (Join-Path $auditDir 'paper_prerequisite_status.json') `
                --claim-output (Join-Path $auditDir 'paper_claim_evidence_matrix.json') `
                *> (Join-Path $auditDir 'paper_prerequisite_build.log')
            $paperRc = $LASTEXITCODE
            & $py (Join-Path $scripts 'audit_program.py') `
                --output (Join-Path $auditDir 'program_audit.json') `
                *> (Join-Path $auditDir 'program_audit.log')
            $auditRc = $LASTEXITCODE
            "estimand_rc=$estimandRc paper_rc=$paperRc audit_rc=$auditRc time=$(Get-Date -Format o)" | `
                Set-Content (Join-Path $out 'post_gate_audit.marker') -Encoding UTF8
            Log("post-gate audits finished estimand_rc=$estimandRc paper_rc=$paperRc audit_rc=$auditRc")
        }
    }

    Start-Sleep -Seconds 30
}

Log('three-hour autonomous supervision window ended; active child computations are left intact rather than killed')
