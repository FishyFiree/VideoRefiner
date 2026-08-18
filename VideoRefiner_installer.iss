; VideoRefiner Inno Setup 安装程序脚本
; 用法：ISCC.exe VideoRefiner_installer.iss（需先运行 build.py 生成 dist\VideoRefiner）

#define MyAppName "VideoRefiner"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Yuh-Hypnotized"
#define MyAppURL "https://github.com/Yuh-Hypnotized/VideoRefiner"
#define MyAppExeName "VideoRefiner.exe"

[Setup]
AppId={{B8E9C3F5-2A47-4D6E-9B1C-7F5A2E8D4C61}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\VideoRefiner
DefaultGroupName=VideoRefiner
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=VideoRefiner-setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=120
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
MinVersion=10.0
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=VideoRefiner AI 视频插帧工具
VersionInfoProductName={#MyAppName}

[Languages]
; 简体中文语言文件（ChineseSimplified.isl）放回 Inno Setup 的 Languages 目录后，
; 取消下面这行的注释即可启用中文向导界面：
; Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\VideoRefiner\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "运行 VideoRefiner"; Flags: nowait postinstall skipifsilent
