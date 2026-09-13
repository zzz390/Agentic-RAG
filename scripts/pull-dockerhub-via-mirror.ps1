# Pull Docker Hub images through a public mirror, then retag to names expected by compose / Dockerfiles.
# For campus networks where registry-1.docker.io is slow or blocked.
#
# Usage (repo root):
#   pwsh -File scripts/pull-dockerhub-via-mirror.ps1
# Optional:
#   $env:DOCKER_HUB_MIRROR = "docker.m.daocloud.io"

$ErrorActionPreference = "Stop"
$MirrorHost = if ($env:DOCKER_HUB_MIRROR) {
    $env:DOCKER_HUB_MIRROR.TrimEnd("/") -replace "^https?://", ""
} else {
    "docker.m.daocloud.io"
}

$ScriptDir = $PSScriptRoot
$root = Split-Path -Parent $ScriptDir
if (-not (Test-Path (Join-Path $root "compose.yml"))) {
    throw "compose.yml not found next to scripts/. Run from the course repo."
}

function Get-ImagesFromCompose {
    param([string]$ComposePath)
    $text = Get-Content -LiteralPath $ComposePath -Raw
    $rx = [regex]::new('^\s+image:\s*(.+)\s*$', [System.Text.RegularExpressions.RegexOptions]::Multiline)
    foreach ($m in $rx.Matches($text)) {
        $v = $m.Groups[1].Value.Trim().Trim('"').Trim("'")
        if ($v -and $v -notmatch '^\$\{') { $v }
    }
}

function Get-ExtraDockerfileHubImages {
    param([string]$Root)
    $extras = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $dockerfiles = @(
        (Join-Path $Root "Dockerfile"),
        (Join-Path $Root "airflow\Dockerfile")
    )
    foreach ($df in $dockerfiles) {
        if (-not (Test-Path -LiteralPath $df)) { continue }
        Get-Content -LiteralPath $df | ForEach-Object {
            if ($_ -match '^\s*FROM\s+(\S+)') {
                $ref = $Matches[1]
                if ($ref -match '^AS\s') { return }
                if ($ref -match '^(ghcr\.io|gcr\.io|quay\.io|mcr\.microsoft\.com)/') { return }
                # Strip AS stage name if glued (FROM img AS x)
                if ($ref -match '^([^:]+:[^:]+|[^:]+)$') { $ref = $Matches[1] }
                [void]$extras.Add($ref)
            }
        }
    }
    return $extras
}

function Split-ImageRef([string]$Image) {
    $img = $Image.Trim()
    $at = $img.IndexOf("@")
    if ($at -ge 0) { $img = $img.Substring(0, $at) }
    $lastSlash = $img.LastIndexOf("/")
    $lastColon = $img.LastIndexOf(":")
    if ($lastColon -gt $lastSlash) {
        return @{ Repo = $img.Substring(0, $lastColon); Tag = $img.Substring($lastColon + 1) }
    }
    return @{ Repo = $img; Tag = "latest" }
}

function Get-MirrorPullSpec {
    param([string]$Image)
    $img = $Image.Trim()
    if ($img -match '^(ghcr\.io|gcr\.io|quay\.io|mcr\.microsoft\.com|registry\.k8s\.io)/') {
        return $null
    }
    $rest = $img
    if ($rest -match '^docker\.io/(.+)$') { $rest = $Matches[1] }
    $p = Split-ImageRef $rest
    $repo = $p.Repo
    $tag = $p.Tag
    if ($repo -notmatch "/") {
        $mirrorRepo = "library/$repo"
    }
    else {
        $mirrorRepo = $repo
    }
    return @{
        Pull   = "${MirrorHost}/${mirrorRepo}:${tag}"
        Target = $Image.Trim()
    }
}

function Invoke-MirrorPull {
    param([string]$Image)
    $spec = Get-MirrorPullSpec $Image
    if (-not $spec) {
        Write-Host "`n[direct] docker pull $Image"
        docker pull $Image
        return
    }
    Write-Host "`n[mirror] docker pull $($spec.Pull)"
    docker pull $spec.Pull
    Write-Host "[tag] $($spec.Pull) -> $($spec.Target)"
    docker tag $spec.Pull $spec.Target
}

$fromCompose = @(Get-ImagesFromCompose (Join-Path $root "compose.yml"))
$fromDockerfiles = @(Get-ExtraDockerfileHubImages $root)
$all = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($x in $fromCompose + $fromDockerfiles) { [void]$all.Add($x) }
$ordered = $all | Sort-Object

Write-Host "Mirror host: $MirrorHost"
Write-Host "Images to sync: $($ordered.Count)"

foreach ($im in $ordered) {
    Invoke-MirrorPull $im
}

Write-Host "`nDone. Next: docker compose build --build-arg UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple --build-arg UV_REWRITE_HOSTED_PACKAGES=true api"
Write-Host "Then: docker compose up --build -d"
