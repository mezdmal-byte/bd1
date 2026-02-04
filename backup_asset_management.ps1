$src = "D:\python111\asset_management"
$dst = "D:\backups\asset_management"

# create backup folder if not exists
New-Item -ItemType Directory -Force -Path $dst | Out-Null

# archive name with timestamp
$timestamp = Get-Date -Format "yyyyMMdd_HHmm"
$zipPath = Join-Path $dst "backup_$timestamp.zip"

# what to backup: code + db + uploaded files
$items = @(
    (Join-Path $src "app.py"),
    (Join-Path $src "schema.sql"),
    (Join-Path $src "assets.db"),
    (Join-Path $src "uploads")
)

Write-Host "Creating backup archive: $zipPath"

Compress-Archive -Path $items -DestinationPath $zipPath -Force

# keep only last 7 archives
Get-ChildItem $dst -Filter "backup_*.zip" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 7 |
    Remove-Item -Force

Write-Host "Done. Backup saved to $zipPath"

