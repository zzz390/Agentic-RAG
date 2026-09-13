# 在 Windows 上安装 Ollama 并拉取 deepseek-r1:7b
# 用法（管理员 PowerShell）:
#   Set-ExecutionPolicy -Scope Process Bypass
#   .\scripts\setup_ollama.ps1

$ErrorActionPreference = "Stop"
$OllamaRoot = "D:\APP\Ollama"
$InstallerPath = Join-Path $OllamaRoot "OllamaSetup.exe"
$ModelsDir = Join-Path $OllamaRoot "models"

New-Item -ItemType Directory -Force -Path $OllamaRoot | Out-Null
New-Item -ItemType Directory -Force -Path $ModelsDir | Out-Null

# 模型文件默认存到此目录（需在新终端生效）
[Environment]::SetEnvironmentVariable("OLLAMA_MODELS", $ModelsDir, "User")
$env:OLLAMA_MODELS = $ModelsDir

Write-Host ">> 下载 Ollama 安装包到 $InstallerPath ..."
Invoke-WebRequest -Uri "https://ollama.com/download/OllamaSetup.exe" -OutFile $InstallerPath

Write-Host ">> 运行安装程序（若弹出 UAC 请确认）..."
Start-Process -FilePath $InstallerPath -Wait

Write-Host ">> 等待 Ollama 服务就绪..."
Start-Sleep -Seconds 5

Write-Host ">> 拉取模型 deepseek-r1:7b（体积较大，请耐心等待）..."
ollama pull deepseek-r1:7b

Write-Host ">> 已安装模型列表:"
ollama list

Write-Host ""
Write-Host "完成。请在项目 .env 中设置:"
Write-Host "  OLLAMA_HOST=http://localhost:11434"
Write-Host "  OLLAMA_MODEL=deepseek-r1:7b"
Write-Host "模型目录: $ModelsDir"
