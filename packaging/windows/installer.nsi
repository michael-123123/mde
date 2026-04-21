; NSIS installer for mde (Markdown Editor) on Windows.
;
; Consumed by packaging/make-installer-windows.sh, which provides the
; variable defines via /D flags. Can also be invoked directly:
;
;   makensis -DSOURCE_DIR=/abs/path/to/mde_launch.dist \
;            -DAPP_VERSION=0.1.13.dev14 \
;            -DAPP_ICON=/abs/path/to/markdown-mark-solid-win10.ico \
;            -DOUTPUT_FILE=/abs/path/to/MarkdownEditor-0.1.13.dev14-x86_64-setup.exe \
;            packaging/windows/installer.nsi
;
; Expected SOURCE_DIR layout: a Nuitka standalone dist with either
; mde_launch.exe or mde.exe at its root (the native build renames via the
; spec's title=mde; the Wine build keeps mde_launch.exe as-is).

Unicode true
SetCompressor /SOLID lzma

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "WinMessages.nsh"
!include "StrFunc.nsh"
${StrRep}
${UnStrRep}

; ----- Metadata --------------------------------------------------------------
!define APP_NAME       "Markdown Editor"
!define APP_PUBLISHER  "mde contributors"
!define APP_URL        "https://github.com/michael-123123/mde"
!define APP_ID         "MarkdownEditor"
!define APP_EXE_MDE    "mde.exe"             ; native build renames to this
!define APP_EXE_WINE   "mde_launch.exe"      ; Wine build keeps this name
!define REG_UNINST     "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}"

!ifndef APP_VERSION
    !define APP_VERSION "0.0.0"
!endif
!ifndef SOURCE_DIR
    !error "SOURCE_DIR must be defined (-DSOURCE_DIR=/path/to/standalone/dist)"
!endif
!ifndef OUTPUT_FILE
    !error "OUTPUT_FILE must be defined (-DOUTPUT_FILE=/path/to/setup.exe)"
!endif

Name "${APP_NAME} ${APP_VERSION}"
OutFile "${OUTPUT_FILE}"
InstallDir "$PROGRAMFILES64\${APP_NAME}"
InstallDirRegKey HKLM "${REG_UNINST}" "InstallLocation"
RequestExecutionLevel admin
ShowInstDetails show
ShowUnInstDetails show

!ifdef APP_ICON
    !define MUI_ICON "${APP_ICON}"
    !define MUI_UNICON "${APP_ICON}"
!endif

; ----- UI pages --------------------------------------------------------------
!define MUI_ABORTWARNING
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE_MDE}"
!define MUI_FINISHPAGE_RUN_TEXT "Launch Markdown Editor"
!define MUI_FINISHPAGE_RUN_FUNCTION "LaunchApp"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

; ----- Variables -------------------------------------------------------------
Var MainExeName

; ----- Core section (required) -----------------------------------------------
Section "Core files" SecCore
    SectionIn RO

    SetOutPath "$INSTDIR"
    File /r "${SOURCE_DIR}\*.*"

    ; Resolve which exe the build produced: native → mde.exe, Wine → mde_launch.exe
    StrCpy $MainExeName "${APP_EXE_MDE}"
    ${IfNot} ${FileExists} "$INSTDIR\$MainExeName"
        StrCpy $MainExeName "${APP_EXE_WINE}"
    ${EndIf}

    ; Start Menu shortcut
    CreateDirectory "$SMPROGRAMS\${APP_NAME}"
    CreateShortCut  "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\$MainExeName"
    CreateShortCut  "$SMPROGRAMS\${APP_NAME}\Uninstall ${APP_NAME}.lnk" "$INSTDIR\uninstall.exe"

    ; Uninstaller + Add/Remove Programs entry
    WriteUninstaller "$INSTDIR\uninstall.exe"
    WriteRegStr   HKLM "${REG_UNINST}" "DisplayName"     "${APP_NAME}"
    WriteRegStr   HKLM "${REG_UNINST}" "DisplayVersion"  "${APP_VERSION}"
    WriteRegStr   HKLM "${REG_UNINST}" "DisplayIcon"     "$INSTDIR\$MainExeName"
    WriteRegStr   HKLM "${REG_UNINST}" "Publisher"       "${APP_PUBLISHER}"
    WriteRegStr   HKLM "${REG_UNINST}" "URLInfoAbout"    "${APP_URL}"
    WriteRegStr   HKLM "${REG_UNINST}" "InstallLocation" "$INSTDIR"
    WriteRegStr   HKLM "${REG_UNINST}" "UninstallString" '"$INSTDIR\uninstall.exe"'
    WriteRegStr   HKLM "${REG_UNINST}" "QuietUninstallString" '"$INSTDIR\uninstall.exe" /S'
    WriteRegDWORD HKLM "${REG_UNINST}" "NoModify" 1
    WriteRegDWORD HKLM "${REG_UNINST}" "NoRepair" 1

    ; Persist MainExeName for the uninstaller section to read
    WriteRegStr HKLM "${REG_UNINST}" "MainExeName" "$MainExeName"
SectionEnd

; ----- Optional: add install dir to user PATH --------------------------------
; User-scoped PATH (HKCU\Environment) — doesn't affect other users, doesn't
; need special admin beyond the install itself. Off by default; user opts in.
;
; Implemented with pure NSIS (no EnVar plugin) — read the existing PATH,
; append ;$INSTDIR if not already present, write back, broadcast
; WM_SETTINGCHANGE so running Explorer/cmd sessions pick it up.
Section /o "Add mde to user PATH" SecPath
    ReadRegStr $0 HKCU "Environment" "Path"
    ; Don't duplicate on reinstall.
    ${StrRep} $1 "$0" "$INSTDIR" "##FOUND##"
    ${If} $0 == $1
        ; $INSTDIR not in PATH yet — append.
        ${If} $0 == ""
            StrCpy $0 "$INSTDIR"
        ${Else}
            StrCpy $0 "$0;$INSTDIR"
        ${EndIf}
        WriteRegExpandStr HKCU "Environment" "Path" "$0"
        SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=5000
        DetailPrint "Added $INSTDIR to user PATH"
    ${Else}
        DetailPrint "$INSTDIR already on user PATH; skipping"
    ${EndIf}
SectionEnd

; ----- Optional: associate .md files with this app ---------------------------
; Opt-in because many users already have a preferred editor for .md.
Section /o "Associate .md files with ${APP_NAME}" SecAssoc
    WriteRegStr HKLM "Software\Classes\.md"                                       "" "${APP_ID}.Document"
    WriteRegStr HKLM "Software\Classes\${APP_ID}.Document"                        "" "Markdown Document"
    WriteRegStr HKLM "Software\Classes\${APP_ID}.Document\DefaultIcon"            "" "$INSTDIR\$MainExeName,0"
    WriteRegStr HKLM "Software\Classes\${APP_ID}.Document\shell\open\command"     "" '"$INSTDIR\$MainExeName" "%1"'
SectionEnd

; ----- Section descriptions (tooltips in the Components page) ----------------
LangString DESC_SecCore  ${LANG_ENGLISH} "The ${APP_NAME} application files, Start Menu shortcut, and uninstaller. Required."
LangString DESC_SecPath  ${LANG_ENGLISH} "Add the install directory to your user PATH so `mde` can be invoked from any terminal. Takes effect in new shells."
LangString DESC_SecAssoc ${LANG_ENGLISH} "Set ${APP_NAME} as the default application for opening .md files. You can change this later via Windows' 'Open with' dialog."

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SecCore}  $(DESC_SecCore)
    !insertmacro MUI_DESCRIPTION_TEXT ${SecPath}  $(DESC_SecPath)
    !insertmacro MUI_DESCRIPTION_TEXT ${SecAssoc} $(DESC_SecAssoc)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; ----- Launch helper for the Finish page -------------------------------------
Function LaunchApp
    ReadRegStr $MainExeName HKLM "${REG_UNINST}" "MainExeName"
    ${If} $MainExeName == ""
        StrCpy $MainExeName "${APP_EXE_MDE}"
    ${EndIf}
    ExecShell "" "$INSTDIR\$MainExeName"
FunctionEnd

; ----- Uninstaller -----------------------------------------------------------
Section "Uninstall"
    ; Remove app files (whole install dir). Done first so shortcut targets
    ; disappear before we unlink the shortcuts.
    RMDir /r "$INSTDIR"

    ; Remove Start Menu entries
    Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
    Delete "$SMPROGRAMS\${APP_NAME}\Uninstall ${APP_NAME}.lnk"
    RMDir  "$SMPROGRAMS\${APP_NAME}"

    ; Undo PATH addition (idempotent — no-op if not present). StrFunc
    ; macros have un.-prefixed variants for use in the uninstall section.
    ReadRegStr $0 HKCU "Environment" "Path"
    ${UnStrRep} $1 "$0" ";$INSTDIR" ""
    ${UnStrRep} $1 "$1" "$INSTDIR;" ""
    ${UnStrRep} $1 "$1" "$INSTDIR"  ""
    ${If} $1 != $0
        WriteRegExpandStr HKCU "Environment" "Path" "$1"
        SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=5000
    ${EndIf}

    ; Undo file-association (only if we own the entry)
    ReadRegStr $0 HKLM "Software\Classes\.md" ""
    ${If} $0 == "${APP_ID}.Document"
        DeleteRegKey HKLM "Software\Classes\.md"
    ${EndIf}
    DeleteRegKey HKLM "Software\Classes\${APP_ID}.Document"

    ; Remove Add/Remove Programs entry last
    DeleteRegKey HKLM "${REG_UNINST}"
SectionEnd
