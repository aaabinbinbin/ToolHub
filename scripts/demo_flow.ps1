param(
    [string]$ApiBaseUrl = "http://127.0.0.1:8000",
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
        Method = $Method
        Uri = $Uri
        ContentType = "application/json"
    }
    if ($null -ne $Body) {
        $params.Body = ($Body | ConvertTo-Json -Depth 20)
    }
    return Invoke-RestMethod @params
}

Write-Step "初始化 PostgreSQL 表"
& .\.venv\Scripts\python.exe .\scripts\init_db.py

Write-Step "注册或复用四类 demo 工具"
& .\.venv\Scripts\python.exe .\scripts\seed_demo_tools.py

Write-Step "检查 API 健康状态"
$health = Invoke-RestMethod "$ApiBaseUrl/health"
Write-Host "health.status = $($health.status)"

Write-Step "提交后台任务"
$taskRequest = @{
    user_input = "请使用 toolhub-demo-cli-git-status 查看 git status"
    run_mode = "SAFE_EXECUTE"
    priority = "default"
}
$submitted = Invoke-Json -Method "POST" -Uri "$ApiBaseUrl/api/tasks" -Body $taskRequest
$taskId = $submitted.task_id
Write-Host "task_id = $taskId"
Write-Host "run_id  = $($submitted.run_id)"
Write-Host "trace_id= $($submitted.trace_id)"

Write-Step "轮询任务状态"
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
do {
    Start-Sleep -Seconds 2
    $task = Invoke-RestMethod "$ApiBaseUrl/api/tasks/$taskId"
    Write-Host "status=$($task.status), step=$($task.current_step)"
    if ($task.status -in @("SUCCESS", "FAILED", "DENIED", "NO_TOOL")) {
        break
    }
} while ((Get-Date) -lt $deadline)

if ($task.status -notin @("SUCCESS", "FAILED", "DENIED", "NO_TOOL")) {
    throw "Task did not finish within $TimeoutSeconds seconds."
}

Write-Step "最终答案"
if ($task.result.summary.final_answer) {
    Write-Host $task.result.summary.final_answer -ForegroundColor Green
}
else {
    Write-Host "No final_answer found." -ForegroundColor Yellow
}

Write-Step "任务事件链路"
$events = Invoke-RestMethod "$ApiBaseUrl/api/tasks/$taskId/events"
$events | Select-Object event_type, step, message, created_at | Format-Table -AutoSize

Write-Step "Dashboard"
Write-Host "Start dashboard with:"
Write-Host ".\.venv\Scripts\streamlit.exe run dashboard/streamlit_app.py --server.port=18501"
