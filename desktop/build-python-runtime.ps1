# 构建 Windows 便携 Python 运行时(Embeddable + pip 依赖)
# 用法: .\build-python-runtime.ps1 [-Proxy http://192.168.31.101:7890]
param(
    [string]$PythonVersion = "3.11.9",
    [string]$Proxy = ""
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$build = Join-Path $root "build"
$pyDir = Join-Path $build "python"
$repo = Split-Path $root -Parent

if (Test-Path $pyDir) { Remove-Item -Recurse -Force $pyDir }
New-Item -ItemType Directory -Force -Path $pyDir | Out-Null

function Fetch($url, $out) {
    Write-Host "下载 $url"
    if ($Proxy) { Invoke-WebRequest -Uri $url -OutFile $out -Proxy $Proxy -UseBasicParsing }
    else { Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing }
}

# 1. 下载并解压 Embeddable Python
$zipPath = Join-Path $env:TEMP "python-$PythonVersion-embed-amd64.zip"
Fetch "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip" $zipPath
Expand-Archive -Path $zipPath -DestinationPath $pyDir -Force

# 2. 启用 import site(否则 pip 装的包不可导入)
$pth = Get-ChildItem $pyDir -Filter "python*._pth" | Select-Object -First 1
if (-not $pth) { throw "未找到 ._pth 文件" }
(Get-Content $pth.FullName) -replace '^#\s*import site', 'import site' |
    Set-Content $pth.FullName -Encoding ASCII

# ._pth 模式不会把脚本目录加入 sys.path,需把应用源码目录(与 python 同级)显式加入;
# 打包后为 resources\python 与 resources\app,布局一致
if (-not (Select-String -Path $pth.FullName -Pattern '^\.\.\\app' -Quiet)) {
    Add-Content $pth.FullName "..\app" -Encoding ASCII
}

# 3. 安装 pip
$getpip = Join-Path $build "get-pip.py"
Fetch "https://bootstrap.pypa.io/get-pip.py" $getpip
$py = Join-Path $pyDir "python.exe"
if ($Proxy) { & $py $getpip --no-warn-script-location --proxy $Proxy }
else { & $py $getpip --no-warn-script-location }
if ($LASTEXITCODE -ne 0) { throw "get-pip 失败" }

# 4. 安装项目依赖
$pipArgs = @("-m", "pip", "install", "-r", (Join-Path $repo "requirements.txt"), "--no-warn-script-location")
if ($Proxy) { $pipArgs += @("--proxy", $Proxy) }
& $py @pipArgs
if ($LASTEXITCODE -ne 0) { throw "pip install 失败" }

# 5. 自检
& $py -c "import flask, waitress, rapidocr_onnxruntime, openpyxl, sqlalchemy; print('python runtime ok')"
if ($LASTEXITCODE -ne 0) { throw "运行时自检失败" }

Write-Host ""
Write-Host "Python 运行时就绪: $pyDir" -ForegroundColor Green
