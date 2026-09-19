param([string]$Out = "C:\Users\Llyam\allodex-captures\game.png")
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public class W {
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref POINT p);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
}
"@
[W]::SetProcessDPIAware() | Out-Null
$p = Get-Process AOgame -ErrorAction Stop | Select-Object -First 1
$h = $p.MainWindowHandle
$cr = New-Object W+RECT; [W]::GetClientRect($h, [ref]$cr) | Out-Null
$pt = New-Object W+POINT; $pt.X = 0; $pt.Y = 0; [W]::ClientToScreen($h, [ref]$pt) | Out-Null
$w = $cr.R - $cr.L; $hh = $cr.B - $cr.T
$bmp = New-Object System.Drawing.Bitmap $w, $hh
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($pt.X, $pt.Y, 0, 0, $bmp.Size)
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
Write-Output "$w x $hh at $($pt.X),$($pt.Y) -> $Out"
