# 快速重建 API 镜像：清华 PyPI + CPU 版 PyTorch（无 ~3GB NVIDIA CUDA 包）
# 用法: .\scripts\rebuild-api-docker.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Wait-DockerReady {
    param([int]$TimeoutSec = 180)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        docker info 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { return }
        Write-Host "Waiting for Docker Desktop..."
        Start-Sleep -Seconds 5
    }
    throw "Docker is not running. Start Docker Desktop and retry."
}

Wait-DockerReady

Write-Host "Stopping old rag-api (if any)..."
docker stop rag-api 2>$null | Out-Null
docker rm rag-api 2>$null | Out-Null

Write-Host "Building API image (Tsinghua PyPI + official CPU PyTorch, no CUDA)..."
docker build `
  --build-arg UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple `
  --build-arg UV_REWRITE_HOSTED_PACKAGES=true `
  -t production-agentic-rag-course-api `
  .

if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Build OK. Start stack with your usual docker run / compose command."
Write-Host "Example health check: curl.exe http://localhost:8000/api/v1/health"
