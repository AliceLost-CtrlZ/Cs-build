param([int]$Port = 8777)
# Tiny zero-dependency local web server (built-in .NET). Run, then open http://localhost:8777/
$Root = $PSScriptRoot
$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://localhost:$Port/")
$listener.Start()
Write-Host "Serving $Root at http://localhost:$Port/  (Ctrl+C to stop)"
$mime = @{ ".html"="text/html"; ".css"="text/css"; ".js"="application/javascript";
           ".png"="image/png"; ".md"="text/markdown"; ".json"="application/json" }
while ($listener.IsListening) {
  try {
    $ctx = $listener.GetContext()
    $rel = [Uri]::UnescapeDataString($ctx.Request.Url.AbsolutePath.TrimStart('/'))
    if ([string]::IsNullOrWhiteSpace($rel)) { $rel = "index.html" }
    $path = Join-Path $Root $rel
    if (Test-Path $path -PathType Leaf) {
      $bytes = [System.IO.File]::ReadAllBytes($path)
      $ext = [System.IO.Path]::GetExtension($path).ToLower()
      if ($mime.ContainsKey($ext)) { $ctx.Response.ContentType = $mime[$ext] }
      $ctx.Response.OutputStream.Write($bytes, 0, $bytes.Length)
    } else {
      $ctx.Response.StatusCode = 404
      $msg = [System.Text.Encoding]::UTF8.GetBytes("Not found: $rel")
      $ctx.Response.OutputStream.Write($msg, 0, $msg.Length)
    }
    $ctx.Response.Close()
  } catch { }
}
