; Inno-Setup-Skript: baut Sprechhilfe-Setup.exe aus dist\Sprechhilfe (siehe .github/workflows/build.yml).
#define AppVersion GetEnv("SPRECHHILFE_VERSION")
#if AppVersion == ""
  #define AppVersion "1.0"
#endif

[Setup]
AppId={{3F1B6C2E-8A4D-4E57-9C1A-5D7E2B9F4A10}
AppName=Sprechhilfe
AppVersion={#AppVersion}
AppPublisher=Sprechhilfe
DefaultDirName={localappdata}\Programs\Sprechhilfe
DefaultGroupName=Sprechhilfe
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=Sprechhilfe-Setup
UninstallDisplayIcon={app}\Sprechhilfe.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "autostart"; Description: "Sprechhilfe beim Anmelden automatisch im Hintergrund starten"; GroupDescription: "Zusätzlich:"
Name: "desktopicon"; Description: "Symbol auf dem Desktop"; GroupDescription: "Zusätzlich:"

[Files]
Source: "dist\Sprechhilfe\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Sprechhilfe"; Filename: "{app}\Sprechhilfe.exe"
Name: "{group}\Sprechhilfe – Einstellungen"; Filename: "{app}\Sprechhilfe.exe"; Parameters: "--einstellungen"
Name: "{group}\Sprechhilfe deinstallieren"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Sprechhilfe"; Filename: "{app}\Sprechhilfe.exe"; Tasks: desktopicon
Name: "{userstartup}\Sprechhilfe"; Filename: "{app}\Sprechhilfe.exe"; Tasks: autostart

[Run]
Filename: "{app}\Sprechhilfe.exe"; Description: "Sprechhilfe jetzt starten"; Flags: nowait postinstall skipifsilent
