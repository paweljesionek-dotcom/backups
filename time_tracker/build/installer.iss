; Inno Setup: iscc /DAppVersion=0.1.0 build\installer.iss  (wymaga wcześniejszego pyinstaller build\TimeTracker.spec)
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
[Setup]
AppName=Tracker czasu
AppVersion={#AppVersion}
AppId={{6F1D2B6A-3C1E-4F6B-9A55-7A2C0A7E1B10}
DefaultDirName={autopf}\TimeTracker
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=TimeTracker-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
UninstallDisplayName=Tracker czasu
CloseApplications=force

[Files]
Source: "..\dist\TimeTracker\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Tracker czasu"; Filename: "{app}\TimeTracker.exe"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "TimeTracker"; ValueData: """{app}\TimeTracker.exe"""; Flags: uninsdeletevalue

[Run]
Filename: "{app}\TimeTracker.exe"; Description: "Uruchom Tracker czasu"; Flags: nowait postinstall skipifsilent
