# AI-EqfLow MCP 一行安装入口（PowerShell）
#
# 用法（远端一行执行）：
#   irm https://raw.githubusercontent.com/<YOUR_GITHUB_USERNAME>/ai-eqflow-mcp/main/setup.ps1 | iex
#
# 带 Key 免交互：
#   $env:AIEQFLOW_API_KEY="sk-xxx"; irm https://raw.githubusercontent.com/<YOUR_GITHUB_USERNAME>/ai-eqflow-mcp/main/setup.ps1 | iex
#
# 本地执行：  powershell -ExecutionPolicy Bypass -File setup.ps1
# 发布前：把本文件与 README.md 里的 <YOUR_GITHUB_USERNAME> 替换为实际 GitHub 用户名。

$ErrorActionPreference = 'Stop'
$RepoRaw = 'https://raw.githubusercontent.com/<YOUR_GITHUB_USERNAME>/ai-eqflow-mcp/main'

Write-Host ''
Write-Host '=== AI-EqfLow MCP 一键安装 ===' -ForegroundColor Cyan

# ---- 1. 找 Python ----
$py = $null
foreach ($cand in @('python', 'py', 'python3')) {
    try {
        $v = & $cand --version 2>$null
        if ($LASTEXITCODE -eq 0 -and $v) { $py = $cand; break }
    } catch { }
}
if (-not $py) {
    Write-Host '✗ 未检测到 Python。请先安装：https://www.python.org/downloads/ （务必勾选 Add python.exe to PATH），装好后重跑本命令。' -ForegroundColor Red
    exit 1
}
$pyVer = (& $py --version 2>&1) -join ''
Write-Host "✓ 使用 Python：$py ($pyVer)"

# ---- 2. 下载安装器到临时目录 ----
$tmp = Join-Path $env:TEMP ('ai-eqflow-mcp-' + (Get-Date -Format 'yyyyMMddHHmmss'))
New-Item -ItemType Directory -Force -Path (Join-Path $tmp 'server') | Out-Null
$files = @('install.py', 'install.bat', 'server/aieqflow_mcp.py', 'server/aieqflow_client.py')
foreach ($f in $files) {
    $dest = Join-Path $tmp ($f -replace '/', '\')
    $url = "$RepoRaw/$f"
    try {
        Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
    } catch {
        Write-Host "✗ 下载失败：$url" -ForegroundColor Red
        Write-Host $_.Exception.Message
        exit 1
    }
}
Write-Host "✓ 安装器已就绪：$tmp"

# ---- 3. 运行 install.py（交互输入 Key，或读环境变量） ----
$installPy = Join-Path $tmp 'install.py'
if ($env:AIEQFLOW_API_KEY) {
    & $py $installPy --key $env:AIEQFLOW_API_KEY
} else {
    & $py $installPy
}

if ($LASTEXITCODE -ne 0) {
    Write-Host '✗ 安装未完成，请查看上方报错信息。' -ForegroundColor Red
    exit 1
}
Write-Host ''
Write-Host '✓ 完成！重启对应 AI 工具后说一句「查一下我的 AI-EqfLow 令牌余额」验证。' -ForegroundColor Green
