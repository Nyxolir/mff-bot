#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#ifndef BundleDir
  #error BundleDir is required
#endif
#ifndef OutputDir
  #error OutputDir is required
#endif

[Setup]
AppId={{265CBA4C-EC58-4BC0-9E83-6DDD0C35DA44}
AppName=MFF Bot
AppVersion={#AppVersion}
AppPublisher=Nyxolir
AppPublisherURL=https://github.com/Nyxolir/mff-bot
AppSupportURL=https://github.com/Nyxolir/mff-bot/issues
AppUpdatesURL=https://github.com/Nyxolir/mff-bot/releases/latest
DefaultDirName={localappdata}\Programs\Nyxolir MFF Bot
DefaultGroupName=Nyxolir\MFF Bot
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
WizardStyle=modern
DisableProgramGroupPage=yes
Compression=lzma2/fast
SolidCompression=yes
OutputDir={#OutputDir}
OutputBaseFilename=MFF-Bot-Setup
SetupIconFile=..\icon.ico
UninstallDisplayIcon={app}\MFF Bot.exe
VersionInfoCompany=Nyxolir
VersionInfoDescription=Nyxolir MFF Bot Setup
VersionInfoVersion={#AppVersion}
CloseApplications=yes
RestartApplications=no
LicenseFile={#BundleDir}\_internal\licenses\DISTRIBUTION-LICENSE.txt
InfoAfterFile=QUICK-START.txt

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Nyxolir\MFF Bot"; Filename: "{app}\MFF Bot.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\MFF Bot"; Filename: "{app}\MFF Bot.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\MFF Bot.exe"; Description: "Open MFF Bot"; Flags: nowait postinstall skipifsilent

; Account/queue data lives outside {app}, and is intentionally preserved by
; upgrades and uninstall. No uninstaller rule deletes user data.
