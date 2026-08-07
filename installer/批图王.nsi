; 批图王 NSIS 安装脚本
; 使用说明：先运行 python build.py 生成 dist/批图王.exe，再由 build.py 自动调用本脚本。
; 也可手动编译：makensis.exe 批图王.nsi（默认版本 1.0.0，可用 /DAPP_VERSION= 覆盖）

Unicode true

!ifndef APP_VERSION
  !define APP_VERSION "1.0.0"
!endif
!ifndef APP_NAME
  !define APP_NAME "批图王"
!endif

!define APP_EXE "批图王.exe"
!define INSTALLER_NAME "批图王-Setup.exe"
!define UNINSTALL_EXE "uninstall.exe"

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
    SetOutPath "$INSTDIR"
    File "..\dist\${APP_EXE}"
    File "..\app\resources\app_icon.ico"

    WriteUninstaller "$INSTDIR\${UNINSTALL_EXE}"

    CreateDirectory "$SMPROGRAMS\${APP_NAME}"
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
    CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"

    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayName" "${APP_NAME}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayVersion" "${APP_VERSION}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayIcon" "$INSTDIR\app_icon.ico"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "Publisher" "${APP_NAME}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "UninstallString" '"$INSTDIR\${UNINSTALL_EXE}"'
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "NoModify" "1"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "NoRepair" "1"
SectionEnd

Section "Uninstall"
    Delete "$INSTDIR\${UNINSTALL_EXE}"
    Delete "$INSTDIR\${APP_EXE}"
    Delete "$INSTDIR\${APP_EXE}.bak"
    Delete "$INSTDIR\${APP_NAME}_new.exe"
    Delete "$INSTDIR\app_icon.ico"
    RMDir "$INSTDIR"

    Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
    RMDir "$SMPROGRAMS\${APP_NAME}"
    Delete "$DESKTOP\${APP_NAME}.lnk"

    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
SectionEnd
