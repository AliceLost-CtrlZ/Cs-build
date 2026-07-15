$listener = [System.Net.HttpListener]::new()
$listener.Prefixes.Add("http://localhost:3456/")
$listener.Start()
Write-Host "Serving on http://localhost:3456"
$root = $PSScriptRoot
$mimeTypes = @{
    '.html' = 'text/html; charset=utf-8'
    '.css'  = 'text/css; charset=utf-8'
    '.js'   = 'application/javascript; charset=utf-8'
}
while ($listener.IsListening) {
    $ctx = $listener.GetContext()
    $path = $ctx.Request.Url.LocalPath
    if ($path -eq '/') { $path = '/index.html' }
    $filePath = Join-Path $root $path.Replace('/', '\').TrimStart('\')
    if (Test-Path $filePath -PathType Leaf) {
        $ext = [System.IO.Path]::GetExtension($filePath)
        $mime = if ($mimeTypes.ContainsKey($ext)) { $mimeTypes[$ext] } else { 'application/octet-stream' }
        $ctx.Response.ContentType = $mime
        $bytes = [System.IO.File]::ReadAllBytes($filePath)
        $ctx.Response.ContentLength64 = $bytes.Length
        $ctx.Response.OutputStream.Write($bytes, 0, $bytes.Length)
        $ctx.Response.OutputStream.Flush()
    } else {
        $ctx.Response.StatusCode = 404
        $msg = [System.Text.Encoding]::UTF8.GetBytes("Not found")
        $ctx.Response.ContentLength64 = $msg.Length
        $ctx.Response.OutputStream.Write($msg, 0, $msg.Length)
    }
    $ctx.Response.Close()
}
