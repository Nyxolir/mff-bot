using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class DesktopLauncher
{
    [STAThread]
    private static void Main()
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string python = Path.GetFullPath(Path.Combine(root, "..", "..", "work", "mff-venv", "Scripts", "python.exe"));
        string script = Path.Combine(root, "app_gui.py");
        if (!File.Exists(python) || !File.Exists(script))
        {
            MessageBox.Show("Keep this launcher in the mff-auto-modern folder. The configured Python environment is required.", "MFF Auto");
            return;
        }
        try
        {
            var start = new ProcessStartInfo(python, "\"" + script + "\"");
            start.WorkingDirectory = root;
            start.UseShellExecute = false;
            start.CreateNoWindow = true;
            Process.Start(start);
        }
        catch (Exception error)
        {
            MessageBox.Show(error.Message, "MFF Auto could not start");
        }
    }
}
