; Inno Setup 6 script for DocBot.
; 1. Run build.bat in the project folder (creates dist\DocBot with the exe, Chromium and docs).
; 2. Open this file in Inno Setup Compiler and press Compile (or: ISCC.exe installer\DocBot.iss).
; Output: installer\Output\DocBot_Setup_<version>.exe

#define MyAppName "DocBot"
#define MyAppVersion "3.1.0"
#define MyAppPublisher "Silver Touch Technologies Ltd."
#define MyAppExeName "DocBot.exe"
; Paths are relative to this .iss file, whatever folder the compiler starts in.
#define SourceDir AddBackslash(SourcePath) + "..\dist\DocBot"

#if !FileExists(SourceDir + "\" + MyAppExeName)
  #error "dist\DocBot\DocBot.exe not found - run build.bat first."
#endif

[Setup]
AppId={{8F3C2A51-6B7D-4E2A-9C1F-5D0B7A3E9F21}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Setup
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Per-user install by default (no administrator rights needed); the user can
; choose "Install for all users" on the first page.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=Output
OutputBaseFilename=DocBot_Setup_{#MyAppVersion}
SetupIconFile={#SourcePath}..\assets\docbot.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
LZMAUseSeparateProcess=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Remove files of a previous version before copying the new build.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{#MyAppName} User Manual"; Filename: "{app}\docs\DocBot_User_Manual_v1.1.docx"
Name: "{group}\{#MyAppName} Installation Check"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--selftest --show"; Comment: "Checks that DocBot and its browser work on this computer"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[Code]
// The workspace (%LOCALAPPDATA%\DocBot) holds recordings, manuals, client
// profiles and API keys. It is kept on uninstall unless the user agrees.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\{#MyAppName}');
    if DirExists(DataDir) and not UninstallSilent() then
    begin
      if MsgBox('Do you also want to delete your DocBot workspace?' + #13#10 + #13#10 +
                DataDir + #13#10 + #13#10 +
                'It contains your recordings, generated manuals, client profiles and saved API keys. ' +
                'Choose No to keep them for a later installation.',
                mbConfirmation, MB_YESNO or MB_DEFAULTBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
