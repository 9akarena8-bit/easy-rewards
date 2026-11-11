; Easy Rewards per-user installer; generated on Windows with Inno Setup.
#define AppName "Easy Rewards"
#define AppVersion "1.3.8"
#define AppExe "EasyRewards.exe"

[Setup]
AppId={{773F19A1-28F9-4D86-8ABE-EF92C41C29E4}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Easy Rewards
DefaultDirName={localappdata}\Programs\EasyRewards
DefaultGroupName=Easy Rewards
PrivilegesRequired=lowest
OutputDir=release
OutputBaseFilename=EasyRewards_Setup_{#AppVersion}
SetupIconFile=assets\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
UninstallDisplayIcon={app}\EasyRewards.exe
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\EasyRewards\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Easy Rewards"; Filename: "{app}\EasyRewards.exe"; IconFilename: "{app}\EasyRewards.exe"
Name: "{autodesktop}\Easy Rewards"; Filename: "{app}\EasyRewards.exe"; IconFilename: "{app}\EasyRewards.exe"; Tasks: desktopicon

[InstallDelete]
Type: files; Name: "{autodesktop}\Easy Rewards Gold Edition.lnk"
Type: files; Name: "{autoprograms}\Easy Rewards Gold Edition.lnk"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; Flags: checkedonce

[Run]
Filename: "{app}\EasyRewards.exe"; Description: "Запустить Easy Rewards"; Flags: nowait
