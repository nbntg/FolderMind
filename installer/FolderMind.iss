[Setup]
AppId={{6C5D1C25-918B-4E20-9B1F-90C60A6D1001}
AppName=FolderMind
AppVersion=0.1.0
AppPublisher=FolderMind
DefaultDirName={localappdata}\Programs\FolderMind
DefaultGroupName=FolderMind
DisableDirPage=no
OutputDir=..\release
OutputBaseFilename=FolderMindSetup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\release\FolderMind\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\FolderMind"; Filename: "{app}\FolderMind.exe"
Name: "{autodesktop}\FolderMind"; Filename: "{app}\FolderMind.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\FolderMind.exe"; Description: "{cm:LaunchProgram,FolderMind}"; Flags: nowait postinstall skipifsilent
