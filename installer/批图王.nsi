; 批图王 NSIS 安装脚本
; 使用说明：先运行 python build.py 生成 dist/批图王/ 目录，再由 build.py 自动调用本脚本。
; 也可手动编译：makensis.exe 批图王.nsi（默认版本 1.0.0，可用 /DAPP_VERSION= 覆盖）

Unicode true

!include "LogicLib.nsh"
!include "WordFunc.nsh"

!ifndef APP_VERSION
  !define APP_VERSION "1.0.0"
!endif
!ifndef APP_NAME
  !define APP_NAME "批图王"
!endif

!define APP_EXE "批图王.exe"
!define INSTALLER_NAME "批图王-Setup.exe"
!define UNINSTALL_EXE "uninstall.exe"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"

Name "${APP_NAME} v${APP_VERSION}"
OutFile "..\dist\${INSTALLER_NAME}"
InstallDir "$LOCALAPPDATA\Programs\${APP_NAME}"
RequestExecutionLevel user
SetCompressor /SOLID lzma
Icon "..\app\resources\app_icon.ico"
UninstallIcon "..\app\resources\app_icon.ico"

; 页面
Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

Section "MainSection" SEC01
    ; 已安装版本比较：本机版本高于安装包版本时中止，防止误装旧版导致降级
    ReadRegStr $0 HKCU "${UNINSTALL_KEY}" "DisplayVersion"
    ${If} $0 != ""
        ${VersionCompare} "$0" "${APP_VERSION}" $1
        ${If} $1 > 0
            MessageBox MB_OK|MB_ICONINFORMATION "本机已安装 v$0，高于安装包版本 v${APP_VERSION}，已取消安装以防降级。"
            Abort
        ${EndIf}
    ${EndIf}

    SetOutPath "$INSTDIR"
    ; 安装版使用 PyInstaller onedir，直接部署所有运行时文件，避免每次启动解压。
    ; 先清理旧版本残留与更新过程留下的临时/备份文件，避免死文件堆积：
    ; - _internal：新版已移除的运行时文件
    ; - *.bak / *_new.exe / *_new.exe.download / *-Setup_new.exe：更新残留
    RMDir /r "$INSTDIR\_internal"
    Delete "$INSTDIR\${APP_EXE}.bak"
    Delete "$INSTDIR\${APP_NAME}_new.exe"
    Delete "$INSTDIR\${APP_NAME}_new.exe.download"
    Delete "$INSTDIR\${APP_NAME}-Setup_new.exe"
    Delete "$INSTDIR\${APP_NAME}-Setup_new.exe.download"

    File /r "..\dist\${APP_NAME}\*"
    File "..\app\resources\app_icon.ico"

    WriteUninstaller "$INSTDIR\${UNINSTALL_EXE}"

    CreateDirectory "$SMPROGRAMS\${APP_NAME}"
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
    CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"

    WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayName" "${APP_NAME}"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayVersion" "${APP_VERSION}"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayIcon" "$INSTDIR\app_icon.ico"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "Publisher" "${APP_NAME}"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "UninstallString" '"$INSTDIR\${UNINSTALL_EXE}"'
    WriteRegStr HKCU "${UNINSTALL_KEY}" "NoModify" "1"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "NoRepair" "1"
SectionEnd

Section "Uninstall"
    Delete "$INSTDIR\${UNINSTALL_EXE}"
    Delete "$INSTDIR\app_icon.ico"

    Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
    RMDir "$SMPROGRAMS\${APP_NAME}"
    Delete "$DESKTOP\${APP_NAME}.lnk"

    DeleteRegKey HKCU "${UNINSTALL_KEY}"
    ; onedir 安装目录包含大量运行时文件，最后统一递归清理。
    RMDir /r "$INSTDIR"
SectionEnd
