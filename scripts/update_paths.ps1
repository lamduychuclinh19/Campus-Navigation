param()

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RoutingDir = Join-Path $ProjectRoot 'data\routing'

function Invoke-ProjectPython([string]$ScriptPath) {
    Write-Host "`n> python $ScriptPath" -ForegroundColor Cyan
    & python $ScriptPath
    if ($LASTEXITCODE -ne 0) {
        throw "Lệnh thất bại: python $ScriptPath"
    }
}

function Get-ReviewRows([string]$Path, [string]$Column) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Thiếu file: $Path"
    }
    return @(Import-Csv -LiteralPath $Path | Where-Object {
        ([string]$_.$Column).Trim().ToLowerInvariant() -notin @('yes', 'no', 'y', 'n')
    })
}

Push-Location $ProjectRoot
try {
    Invoke-ProjectPython 'scripts/prepare_routing_data.py'
    Invoke-ProjectPython 'scripts/inspect_way_intersections.py'

    $EndpointCsv = Join-Path $RoutingDir 'nearby_endpoints.csv'
    $IntersectionCsv = Join-Path $RoutingDir 'way_intersections.csv'
    $EndpointReview = Get-ReviewRows $EndpointCsv 'confirmed_connected'
    $IntersectionReview = Get-ReviewRows $IntersectionCsv 'confirmed_connected'

    if ($EndpointReview.Count -gt 0 -or $IntersectionReview.Count -gt 0) {
        Write-Host "`nCó kết nối mới/chưa xác nhận. Mở hai file dưới đây, xem từng dòng REVIEW rồi đổi confirmed_connected thành yes hoặc no:" -ForegroundColor Yellow
        Write-Host "  $EndpointCsv"
        Write-Host "  $IntersectionCsv"
        Write-Host "`nLưu CSV rồi chạy lại: .\scripts\update_paths.ps1"
        return
    }

    Invoke-ProjectPython 'scripts/build_routing_graph.py'
    Invoke-ProjectPython 'scripts/suggest_place_access.py'

    Write-Host "`nĐã dựng lại graph từ GeoJSON. Nếu có cổng vào mới, xem REVIEW trong place_access_candidates_multi.csv; xác nhận cổng thật bằng yes, cổng không dùng bằng no." -ForegroundColor Green
    Write-Host 'Cuối cùng refresh trang bản đồ (Ctrl+R) và bấm Tìm đường để tính tuyến mới.'
}
finally {
    Pop-Location
}
