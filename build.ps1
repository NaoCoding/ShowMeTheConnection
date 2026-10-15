param(
    [switch]$Console
)

$ErrorActionPreference = 'Stop'
$argsList = @('-m', 'PyInstaller', '--clean', '--noconfirm', '--onefile', '--name', 'ShowMeTheConnection')
if (-not $Console) { $argsList += '--noconsole' }
$argsList += @('--collect-all', 'hid', '--collect-all', 'pystray', '--paths', 'src', 'run_tray.py')
python @argsList
