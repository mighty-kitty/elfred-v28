$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
chcp 65001 > $null

function Invoke-ScriptCapture {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScriptPath
    )

    $shell = Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\powershell.exe"
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $shell
    $startInfo.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""
    $startInfo.WorkingDirectory = (Get-Location).Path
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $startInfo.StandardErrorEncoding = [System.Text.Encoding]::UTF8

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    $process.Start() | Out-Null
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()

    if ($process.ExitCode -ne 0) {
        throw "Script failed: $ScriptPath`n$stdout`n$stderr"
    }

    return ($stdout + $stderr)
}

$runId = Get-Date -Format "yyyyMMdd_HHmmss_fff"
$demoDir = Join-Path "logs\delivery\demo_runs" $runId
New-Item -ItemType Directory -Path $demoDir -Force | Out-Null

$smokeLog = Join-Path $demoDir "smoke_output.txt"
$integrationLog = Join-Path $demoDir "integration_output.json"
$deliveryLog = Join-Path $demoDir "delivery_pack_output.json"
$summaryPath = Join-Path $demoDir "demo_summary.md"

$smokeOutput = Invoke-ScriptCapture -ScriptPath ".\scripts\run_smoke.ps1"
$smokeOutput | Set-Content -Path $smokeLog -Encoding UTF8

$integrationOutput = Invoke-ScriptCapture -ScriptPath ".\scripts\run_integration_flows.ps1"
$integrationOutput | Set-Content -Path $integrationLog -Encoding UTF8

$deliveryOutput = Invoke-ScriptCapture -ScriptPath ".\scripts\run_delivery_pack.ps1"
$deliveryOutput | Set-Content -Path $deliveryLog -Encoding UTF8

$summary = @"
# EMOS Delivery Demo

- Run id: $runId
- Generated at: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz")
- Demo goal: show the stable EMOS v1 delivery path for operator and handoff review

## Steps Executed

1. `.\scripts\run_smoke.ps1`
2. `.\scripts\run_integration_flows.ps1`
3. `.\scripts\run_delivery_pack.ps1`

## Raw Outputs

- Smoke output: $smokeLog
- Integration-flow output: $integrationLog
- Delivery-pack output: $deliveryLog

## Review Path

1. Review the latest delivery-pack output for the generated `storage_report` and artifact paths.
2. Review the latest integration-flow output for execution-surface and readiness evidence.
3. Use [docs/handoff_example_flows.md](docs/handoff_example_flows.md) for the receiver-facing example flows.
4. Use [docs/acceptance_walkthrough.md](docs/acceptance_walkthrough.md) for the acceptance sequence.

## Notes

- This script intentionally reuses the existing stable delivery scripts instead of introducing a parallel demo-only path.
- Benchmark, official LoCoMo, and paper-facing assets are not touched by this demo script.
"@

$summary = @"
# EMOS Delivery Demo

- Run id: $runId
- Generated at: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz")
- Demo goal: show the stable EMOS v1 delivery path for operator and handoff review

## Steps Executed

1. `.\scripts\run_smoke.ps1`
2. `.\scripts\run_integration_flows.ps1`
3. `.\scripts\run_delivery_pack.ps1`

## Raw Outputs

- Smoke output: $smokeLog
- Integration-flow output: $integrationLog
- Delivery-pack output: $deliveryLog

## Review Path

1. Review the latest delivery-pack output for the generated `storage_report` and artifact paths.
2. Review the delivery-pack shared observability sections for `operator_review_order`, `error_taxonomy`, and `recommended_lifecycle_execution`.
3. Use [docs/final_delivery_manifest.md](docs/final_delivery_manifest.md) as the canonical review wording for delivery acceptance and shared observability posture.
4. Review the latest integration-flow output for execution-surface and readiness evidence.
5. Use [docs/operator_observability_guide.md](docs/operator_observability_guide.md) for the shared observability wording.
6. Use [docs/handoff_example_flows.md](docs/handoff_example_flows.md) for the receiver-facing example flows.
7. Use [docs/acceptance_walkthrough.md](docs/acceptance_walkthrough.md) for the acceptance sequence.

## Notes

- This script intentionally reuses the existing stable delivery scripts instead of introducing a parallel demo-only path.
- Benchmark, official LoCoMo, and paper-facing assets are not touched by this demo script.
"@

$summary | Set-Content -Path $summaryPath -Encoding UTF8
Get-Content $summaryPath
