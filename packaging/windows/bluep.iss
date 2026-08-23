; ─────────────────────────────────────────────────────────────────────────────
; Inno Setup script for BlueP — produces BlueP-Setup-<version>.exe
; Run after PyInstaller has produced dist/BlueP/ (onedir) on Windows:
;   ISCC.exe /DAPP_VERSION=<version> packaging/windows/bluep.iss
; ─────────────────────────────────────────────────────────────────────────────

#ifndef APP_VERSION
  #error "Compile with /DAPP_VERSION=<version> (e.g. 0.1.0)"
#endif

#define APP_NAME "BlueP"
#define APP_PUBLISHER "BlueP Project"
#define APP_URL "https://discoveryfox.github.io/bluep/"
#define APP_ID "io.bluep.BlueP"
#define APP_EXE "BlueP.exe"

[Setup]
AppName={#APP_NAME}
AppVersion={#APP_VERSION}
AppVerName={#APP_NAME} {#APP_VERSION}
AppPublisher={#APP_PUBLISHER}
AppPublisherURL={#APP_URL}
AppSupportURL={#APP_URL}
AppUpdatesURL={#APP_URL}
AppContact={#APP_URL}
DefaultDirName={autopf}\{#APP_NAME}
DefaultGroupName={#APP_NAME}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#APP_EXE}
UninstallDisplayName={#APP_NAME} {#APP_VERSION}
OutputDir=..\..\dist
OutputBaseFilename=BlueP-Setup-{#APP_VERSION}
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
LicenseFile=..\..\LICENSE
PrivilegesRequiredOverridesAllowed=dialog
DisableWelcomePage=no
WizardStyle=modern
; This GUID is BlueP's static installer ID — do not change between releases.
AppId={{7B4A1F2C-3E5D-4B6C-9F8A-1A2B3C4D5E6F}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The PyInstaller onedir build output lives in dist/BlueP/
Source: "..\..\dist\BlueP\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#APP_NAME}"; Filename: "{app}\{#APP_EXE}"
Name: "{group}\Uninstall {#APP_NAME}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#APP_NAME}"; Filename: "{app}\{#APP_EXE}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#APP_EXE}"; Description: "{cm:LaunchProgram,{#APP_NAME}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
