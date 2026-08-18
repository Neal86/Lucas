$ErrorActionPreference = "Stop"

$remote = "windows-mcp-upstream"
$url = "https://github.com/CursorTouch/Windows-MCP.git"

$existing = git remote
if ($existing -contains $remote) {
  git remote set-url $remote $url
} else {
  git remote add $remote $url
}

git fetch $remote
Write-Host "Configured $remote -> $url"
