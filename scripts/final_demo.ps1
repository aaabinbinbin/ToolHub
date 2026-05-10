param(
    [string]$ApiBaseUrl = "http://127.0.0.1:8000",
    [string]$DashboardUrl = "http://localhost:18501",
    [int]$TimeoutSeconds = 90
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Invoke-Json {
    param(
        [string]$Method,
        [string]$Uri,
        [object]$Body = $null
    )

    $params = @{
        Method      = $Method
        Uri         = $Uri
        ContentType = "application/json"
    }
    if ($null -ne $Body) {
        $params.Body = ($Body | ConvertTo-Json -Depth 30)
    }
    return Invoke-RestMethod @params
}

function Get-ToolByName {
    param([string]$Name)
    $encoded = [System.Net.WebUtility]::UrlEncode($Name)
    $result = Invoke-RestMethod "$ApiBaseUrl/api/tools/search?q=$encoded&include_disabled=true"
    foreach ($item in $result.items) {
        if ($item.name -eq $Name) {
            return $item
        }
    }
    throw "Tool not found: $Name"
}

function Wait-Task {
    param([string]$TaskId)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $terminal = @("SUCCESS", "FAILED", "DENIED", "NO_TOOL", "WAITING_APPROVAL", "CANCELLED", "TIMEOUT", "PLANNED")
    do {
        Start-Sleep -Seconds 2
        $task = Invoke-RestMethod "$ApiBaseUrl/api/tasks/$TaskId"
        Write-Host "status=$($task.status), step=$($task.current_step)"
        if ($task.status -in $terminal) {
            return $task
        }
    } while ((Get-Date) -lt $deadline)

    throw "Task did not finish within $TimeoutSeconds seconds. Start worker with: .\.venv\Scripts\celery.exe -A app.workers.celery_app worker --pool=solo --loglevel=INFO --concurrency=1"
}

function Write-TraceLink {
    param([string]$TraceId)
    Write-Host "trace_id = $TraceId"
    Write-Host "trace_api = $ApiBaseUrl/api/traces/$TraceId"
    Write-Host "dashboard = $DashboardUrl"
}

Write-Step "Initialize database and seed canonical demo tools"
& .\.venv\Scripts\python.exe .\scripts\init_db.py
& .\.venv\Scripts\python.exe .\scripts\seed_demo_tools.py | Out-Host

Write-Step "Check API health"
$health = Invoke-RestMethod "$ApiBaseUrl/health/ready"
Write-Host "health.status = $($health.status)"

Write-Step "Demo 1: Routing explanation with top-k candidates"
$route = Invoke-Json -Method "POST" -Uri "$ApiBaseUrl/api/router/select" -Body @{
    user_input          = "请查看 git status"
    intent              = "CLI_EXECUTION"
    suggested_tool_type = "CLI"
    top_k               = 5
    enable_llm_rerank   = $false
    tool_input          = @{
        rule_id = "cli://git/status-short"
        args    = @{}
    }
}
Write-Host "selected_tool = $($route.selected_tool.name)"
Write-Host "score = $($route.score)"
Write-Host "reason = $($route.reason)"
$route.candidate_details |
    Select-Object rank, @{Name="tool";Expression={$_.tool.name}}, score, schema_match |
    Format-Table -AutoSize

Write-Step "Demo 2: HTTP tool direct execution"
$httpTool = Get-ToolByName "toolhub-demo-http-echo"
$httpResult = Invoke-Json -Method "POST" -Uri "$ApiBaseUrl/api/tool-calls/execute" -Body @{
    tool_id    = $httpTool.id
    tool_input = @{
        method = "GET"
        params = @{ q = "toolhub-final-demo" }
    }
    user_id      = "demo-user"
    workspace_id = "default"
}
Write-Host "status = $($httpResult.status)"
Write-TraceLink -TraceId $httpResult.trace_id

Write-Step "Demo 3: MCP calculator direct execution"
$mcpTool = Get-ToolByName "toolhub-demo-mcp-calculator"
$mcpResult = Invoke-Json -Method "POST" -Uri "$ApiBaseUrl/api/tool-calls/execute" -Body @{
    tool_id    = $mcpTool.id
    tool_input = @{ expression = "1 + 2 * 3" }
    user_id      = "demo-user"
    workspace_id = "default"
}
Write-Host "status = $($mcpResult.status)"
Write-Host "output = $($mcpResult.output | ConvertTo-Json -Depth 10)"
Write-TraceLink -TraceId $mcpResult.trace_id

Write-Step "Demo 4: Replay the HTTP tool call from its trace"
$httpTrace = Invoke-RestMethod "$ApiBaseUrl/api/traces/$($httpResult.trace_id)"
$sourceToolCallId = $httpTrace.tool_calls[0].id
Write-Host "source_tool_call_id = $sourceToolCallId"
$replay = Invoke-Json -Method "POST" -Uri "$ApiBaseUrl/api/tool-calls/$sourceToolCallId/replay" -Body @{
    reason         = "final demo replay"
    override_input = @{
        method = "GET"
        params = @{ q = "toolhub-replay-demo" }
    }
    user_id      = "demo-user"
    workspace_id = "default"
}
Write-Host "replay_status = $($replay.status)"
Write-Host "replay_trace_id = $($replay.trace_id)"

Write-Step "Demo 5: High-risk sandbox preflight enters ASK in SAFE_EXECUTE"
$preflight = Invoke-Json -Method "POST" -Uri "$ApiBaseUrl/api/harness/plan" -Body @{
    user_input   = "请在沙箱中运行 Python print('hello from sandbox')"
    run_mode     = "SAFE_EXECUTE"
    priority     = "default"
    user_id      = "demo-user"
    workspace_id = "default"
}
Write-Host "preflight_status = $($preflight.status)"
if ($preflight.permission) {
    Write-Host "permission_decision = $($preflight.permission.decision)"
    Write-Host "permission_reason = $($preflight.permission.reason)"
}
Write-TraceLink -TraceId $preflight.trace_id

Write-Step "Demo 6: Multi-step Agent task, requires Celery worker"
$taskRequest = @{
    user_input   = "请查看 git status 和 diff"
    run_mode     = "SAFE_EXECUTE"
    priority     = "default"
    user_id      = "demo-user"
    workspace_id = "default"
    run_config   = @{
        max_steps       = 3
        max_retries     = 1
        timeout_seconds = 300
    }
}
$submitted = Invoke-Json -Method "POST" -Uri "$ApiBaseUrl/api/tasks" -Body $taskRequest
Write-Host "task_id = $($submitted.task_id)"
Write-Host "run_id = $($submitted.run_id)"
Write-TraceLink -TraceId $submitted.trace_id

try {
    $task = Wait-Task -TaskId $submitted.task_id
    Write-Host "final_status = $($task.status)"
    if ($task.result.summary.final_answer) {
        Write-Host "final_answer = $($task.result.summary.final_answer)"
    }
}
catch {
    Write-Host $_.Exception.Message -ForegroundColor Yellow
}

Write-Step "Final dashboard"
Write-Host "Open $DashboardUrl and inspect Trace / Task / Routing / Replay tabs."
