; S-Mapper Inno Setup Script

[Setup]
; --- Application Metadata ---
AppName=S-Mapper
AppVersion=1.0.0
AppPublisher=Stoffi Software Solutions
AppPublisherURL=https://github.com/StoffiPoff/S-Mapper
AppSupportURL=https://github.com/StoffiPoff/S-Mapper/issues
AppUpdatesURL=https://github.com/StoffiPoff/S-Mapper/releases

; --- Installation Directory ---
DefaultDirName={autopf}\S-Mapper
DefaultGroupName=S-Mapper
DisableDirPage=no
PrivilegesRequired=admin

; --- Output Installer ---
; NOTE: You should convert your PNG to a multi-layer .ico file for best results.
OutputDir=installer
OutputBaseFilename=S-Mapper-v1.0.0-Setup-x64
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

; --- Architecture ---
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64

; --- Uninstall Information ---
UninstallDisplayIcon={app}\s-mapper-app.exe
UninstallDisplayName=S-Mapper

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}";
Name: "runonstartup"; Description: "Run S-Mapper when computer starts";

[Files]
; This includes all files and subdirectories from your PyInstaller build output.
Source: "dist\s-mapper-app\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\S-Mapper"; Filename: "{app}\s-mapper-app.exe"
Name: "{group}\{cm:UninstallProgram,S-Mapper}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\S-Mapper"; Filename: "{app}\s-mapper-app.exe"; Tasks: desktopicon

; This section adds the "Run on Startup" functionality if the user selects the task
[Registry]
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "S-Mapper"; ValueData: """{app}\s-mapper-app.exe"""; Tasks: runonstartup; Check: not IsAdminInstallMode

[Run]
Filename: "{app}\s-mapper-app.exe"; Description: "{cm:LaunchProgram,S-Mapper}"; Flags: nowait postinstall skipifsilent
