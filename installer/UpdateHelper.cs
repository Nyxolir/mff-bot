// Runs from the private update cache, so it never locks installed app files.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;

class UpdateHelper {
    static JavaScriptSerializer Json = new JavaScriptSerializer();
    static Dictionary<string, object> Plan;
    static string Job, Exe, Profile, Token;
    static bool ParentExited, Committed, OtherInstance;
    static string Text(string key) { return Convert.ToString(Plan[key]); }
    static bool Flag(string key) { return Plan.ContainsKey(key) && Plan[key] is bool && (bool)Plan[key]; }
    static string Full(string path) {
        if (String.IsNullOrWhiteSpace(path) || path.IndexOfAny(new char[]{'"','\r','\n'}) >= 0 || !Path.IsPathRooted(path)) throw new Exception("Invalid update path");
        return Path.GetFullPath(path).TrimEnd(Path.DirectorySeparatorChar);
    }
    static bool Same(string a, string b) { return String.Equals(Full(a),Full(b),StringComparison.OrdinalIgnoreCase); }
    static Dictionary<string, object> Read(string path) {
        if (new FileInfo(path).Length > 65536) throw new Exception("Update record too large");
        return Json.Deserialize<Dictionary<string, object>>(File.ReadAllText(path));
    }
    static void Write(string name, object data) {
        string path=Path.Combine(Job,name), temp=path+".tmp";
        File.WriteAllText(temp,Json.Serialize(data),new UTF8Encoding(false));
        if(File.Exists(path)) File.Delete(path);
        File.Move(temp,path);
    }
    static bool Marker(string name) {
        string path=Path.Combine(Job,name);
        return File.Exists(path) && Convert.ToString(Read(path)["token"])==Token;
    }
    static string Digest(string file) {
        using(var input=File.OpenRead(file)) using(var hash=SHA256.Create())
            return BitConverter.ToString(hash.ComputeHash(input)).Replace("-","").ToLowerInvariant();
    }
    static string Quote(string value) {
        int trailing=0;
        for(int i=value.Length-1;i>=0 && value[i]=='\\';i--)trailing++;
        return "\""+value+new String('\\',trailing)+"\"";
    }
    static ProcessStartInfo StartInfo(string executable,string arguments) {
        var info=new ProcessStartInfo(executable,arguments);
        info.UseShellExecute=false;info.CreateNoWindow=true;info.WorkingDirectory=Path.GetDirectoryName(executable);
        info.EnvironmentVariables["MFF_DATA_DIR"]=Profile;
        return info;
    }
    static void CheckOtherInstances() {
        DateTime deadline=DateTime.UtcNow.AddSeconds(5);
        while(true) {
            bool found=false;
            foreach(var process in Process.GetProcessesByName(Path.GetFileNameWithoutExtension(Exe))) {
                try { if(Same(process.MainModule.FileName,Exe))found=true; }
                catch(InvalidOperationException) { }
                catch(System.ComponentModel.Win32Exception) { OtherInstance=true;throw new Exception("Cannot verify whether another copy of MFF Bot is running"); }
                finally { process.Dispose(); }
            }
            if(!found)return;
            if(DateTime.UtcNow>=deadline) { OtherInstance=true;throw new Exception("Another copy of MFF Bot is still using this installation"); }
            Thread.Sleep(250);
        }
    }
    static void RestartApp() {
        string arguments="--update-result "+Quote(Path.Combine(Job,"handoff.json"));
        // The smoke probe verifies resume intent without connecting to a game.
        if (Environment.GetEnvironmentVariable("MFF_UPDATER_SELFTEST")=="1")
            arguments+=" --update-probe "+Quote(Path.Combine(Job,"resume-probe.json"));
        Process.Start(StartInfo(Exe,arguments));
    }
    static int Apply(string path) {
        path=Full(path);Job=Path.GetDirectoryName(path);Plan=Read(path);
        if(Convert.ToInt32(Plan["protocol"])!=1 || Path.GetFileName(path)!="handoff.json") throw new Exception("Unsupported update protocol");
        Profile=Full(Text("profile"));Exe=Full(Text("executable"));Token=Text("token");
        string version=Text("version");
        if(!Regex.IsMatch(Token,"\\A[0-9a-f]{32}\\z") || !Regex.IsMatch(version,"\\A[0-9]+\\.[0-9]+\\.[0-9]+\\z")) throw new Exception("Invalid update identity");
        foreach(string part in version.Split('.')) if(Int32.Parse(part)>65535) throw new Exception("Invalid update version");
        if (!Same(Job,Path.Combine(Profile,".cache","updates",version)) || Path.GetFileName(Exe)!="MFF Bot.exe") throw new Exception("Update paths do not match the app profile");
        DateTimeOffset created=DateTimeOffset.Parse(Text("created_at"));
        if(created>DateTimeOffset.UtcNow || DateTimeOffset.UtcNow-created>TimeSpan.FromHours(1)) throw new Exception("Update request expired");
        string installer=Full(Text("installer"));
        if(!Same(installer,Path.Combine(Job,"MFF-Bot-Setup.exe")) || !Regex.IsMatch(Text("sha256"),"\\A[0-9a-f]{64}\\z") || Digest(installer)!=Text("sha256")) throw new Exception("Installer checksum mismatch");
        using(var updateLock=new FileStream(Path.Combine(Profile,".cache","updates","helper.lock"),FileMode.OpenOrCreate,FileAccess.ReadWrite,FileShare.None)) {
            Process parent=null;
            try { parent=Process.GetProcessById(Convert.ToInt32(Plan["parent_pid"])); }
            catch(ArgumentException) { ParentExited=true; }
            if(parent!=null && !Same(parent.MainModule.FileName,Exe)) throw new Exception("Parent app identity changed");
            Write("ready.json",new { token=Token,stage="waiting_for_app" });
            DateTime deadline=DateTime.UtcNow.AddSeconds(120);
            while(DateTime.UtcNow<deadline) {
                if(Marker("cancel.json")) throw new Exception("Update cancelled before app shutdown");
                Committed=Marker("commit.json");
                ParentExited=parent==null || parent.WaitForExit(250);
                if(ParentExited) break;
            }
            if(parent!=null)parent.Dispose();
            if(!ParentExited) throw new Exception("App did not close; update was not installed");
            Committed=Marker("commit.json");
            if(!Committed || Marker("cancel.json")) throw new Exception("App did not authorize installation");
            CheckOtherInstances();
            // Recheck after waiting; the installer must still match its release.
            if(Digest(installer)!=Text("sha256")) throw new Exception("Installer changed during handoff");
            Write("result.json",new {token=Token,stage="installing"});
            string args="/VERYSILENT /SUPPRESSMSGBOXES /SP- /NORESTART /NOCLOSEAPPLICATIONS /NORESTARTAPPLICATIONS /DIR="+Quote(Path.GetDirectoryName(Exe))+" /LOG="+Quote(Path.Combine(Job,"installation.log"));
            using(var install=Process.Start(StartInfo(installer,args))) {
                // Do not terminate an installer midway through a transaction.
                install.WaitForExit();
                if(install.ExitCode!=0) throw new Exception("Installer returned exit code "+install.ExitCode);
            }
            var info=Read(Path.Combine(Path.GetDirectoryName(Exe),"_internal","build-info.json"));
            if(Convert.ToString(info["version"])!=version) throw new Exception("Installed app version does not match this update");
            string report=Path.Combine(Job,"application-check.json");
            if(File.Exists(report))File.Delete(report);
            var smoke=StartInfo(Exe,"--self-test "+Quote(report));
            smoke.EnvironmentVariables["MFF_DATA_DIR"]=Path.Combine(Job,"verification-profile");
            smoke.EnvironmentVariables["QT_QPA_PLATFORM"]="offscreen";
            using(var check=Process.Start(smoke)) {
                if(!check.WaitForExit(180000)) throw new Exception("Updated app verification timed out; queue remains stopped");
                var evidence=Read(report);
                if(check.ExitCode!=0 || !(bool)evidence["passed"] || (bool)evidence["game_connected"] || (bool)evidence["queue_started"]) throw new Exception("Updated app verification failed; queue remains stopped");
            }
            Write("result.json",new {token=Token,stage="success"});
            RestartApp();return 0;
        }
    }
    [STAThread] static int Main(string[] args) {
        try { if(args.Length!=1)throw new Exception("Expected an update handoff file");return Apply(args[0]); }
        catch(Exception error) {
            try {
                if(Job!=null && Token!=null)Write("result.json",new {token=Token,stage="failed",error=error.Message});
                if(Committed && ParentExited && !OtherInstance && File.Exists(Exe))RestartApp();
            } catch { }
            return 1;
        }
    }
}
