; Inno Setup Script - 语音日历工具安装程序
; 用法: 使用 Inno Setup Compiler 编译此脚本
; 前置: 已通过 PyInstaller 生成 dist/VoiceCalendar/ 目录

#define MyAppName "语音日历"
#define MyAppNameEn "VoiceCalendar"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Voice Calendar"
#define MyAppURL "https://github.com/Patrick684/voice-calendar"
#define MyAppExeName "VoiceCalendar.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppNameEn}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
; 输出安装程序
OutputDir=..\dist
OutputBaseFilename=VoiceCalendar_Setup_{#MyAppVersion}
; 图标
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
; 压缩
Compression=lzma2/ultra64
SolidCompression=yes
; 需要管理员权限（全局热键监听）
PrivilegesRequired=admin
; 64 位
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; UI
WizardStyle=modern
; 磁盘空间提示
DiskSpanning=no

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"
Name: "autostart"; Description: "开机自动启动"; GroupDescription: "系统集成:"

[Files]
; PyInstaller 输出的所有文件
Source: "..\dist\VoiceCalendar\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; 开始菜单
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\icon.ico"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
; 桌面快捷方式
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\icon.ico"; Tasks: desktopicon

[Run]
; 安装完成后启动应用
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Registry]
; 开机自启注册表项（仅在用户选择时写入）
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppNameEn}"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: autostart

[UninstallDelete]
; 卸载时清理日志等运行时生成的文件（不删用户数据）
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\*.log"

[Code]
// 卸载前提示用户是否保留配置数据
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: string;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\VoiceCalendar');
    if DirExists(DataDir) then
    begin
      if MsgBox('是否删除用户数据（日历事件、配置文件）？' + #13#10 +
                '数据目录: ' + DataDir, mbConfirmation, MB_YESNO) = IDYES then
      begin
        DelTree(DataDir, True, True, True);
      end;
    end;
  end;
end;
