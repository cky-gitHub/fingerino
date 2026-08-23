; Inno Setup script for the Fingerino Windows installer.
;
; Not run by hand — packaging/build.py passes the paths in:
;   ISCC /DMyAppVersion=... /DMyAppSource=... /DMyOutputDir=... /DMyIcon=...
;        /DMyOutputBase=... packaging\fingerino.iss
;
; Installs per-user into %LOCALAPPDATA%\Programs\Fingerino so there is no UAC
; prompt: for an unsigned app, a consent dialog on top of the SmartScreen
; warning is one scare too many, and nothing here needs machine-wide access.

#define MyAppName "Fingerino"
#define MyAppPublisher "cky"
#define MyAppURL "https://github.com/cky-gitHub/fingerino"
#define MyAppExeName "Fingerino.exe"

[Setup]
AppId={{D7C06B7D-1E2D-4281-AD9A-58EB8964F88F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#MyOutputDir}
OutputBaseFilename={#MyOutputBase}
SetupIconFile={#MyIcon}
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#MyAppSource}\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
    AppUserModelID: "cky.fingerino"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
    Tasks: desktopicon; AppUserModelID: "cky.fingerino"

[Run]
Filename: "{app}\{#MyAppExeName}"; \
    Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; The cached hand-landmark model and generated icon, written on first run.
Type: filesandordirs; Name: "{localappdata}\fingerino"
