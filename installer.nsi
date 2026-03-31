!include "MUI2.nsh"

; ---------------------------------------------------------------
; VERSION — keep in sync with CURRENT_VERSION in ky_doi_autosubmit.py
; ---------------------------------------------------------------
!define VERSION "18.3"
!define PRODUCT_NAME "KY DOI PBM Auto Submitter"

Name "${PRODUCT_NAME} v${VERSION}"
OutFile "KY_DOI_Installer.exe"
InstallDir "C:\KY_DOI"

; Embed version metadata in the .exe (visible in Properties → Details)
VIProductVersion "${VERSION}.0.0"
VIAddVersionKey "ProductName"     "${PRODUCT_NAME}"
VIAddVersionKey "FileVersion"     "${VERSION}"
VIAddVersionKey "ProductVersion"  "${VERSION}"
VIAddVersionKey "LegalCopyright"  ""
VIAddVersionKey "FileDescription" "KY DOI PBM Auto Submitter Installer"

RequestExecutionLevel admin

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_LANGUAGE "English"


Section "Install KY DOI Submitter"

SetOutPath "$INSTDIR"

; --- Create folders ---
CreateDirectory "$INSTDIR"
CreateDirectory "$INSTDIR\incoming"
CreateDirectory "$INSTDIR\archive"
CreateDirectory "$INSTDIR\logs"

; --- Copy program files ---
File "ky_doi_autosubmit.py"
File "ky_doi_config_gui.py"
File "KY_DOI_Readme.pdf"
File "CORRECT KYDOI Primary.rpx"


; ---------------------------------------------------------
; PYTHON CHECK (NO INSTALL)
; ---------------------------------------------------------

DetailPrint "Checking for Python..."
nsExec::ExecToStack 'python -V'
Pop $0
Pop $1

StrCmp "$0" "" NoPython ContinuePython

NoPython:
MessageBox MB_OK "Python is not installed on this system.$\r$\nPlease install Python 3.11+ and re-run this installer."
Abort

ContinuePython:
DetailPrint "Python found: $0"


; ---------------------------------------------------------
; dependency installs
; ---------------------------------------------------------

DetailPrint "Installing required Python packages..."

ExecWait 'python -m pip install --upgrade pip'
ExecWait 'python -m pip install PyPDF2 watchdog playwright requests'
ExecWait 'python -m playwright install chromium'


; ---------------------------------------------------------
; Shortcuts (Desktop)
; ---------------------------------------------------------

CreateShortCut "$DESKTOP\Run KY DOI Auto Submitter.lnk" "python.exe" '"$INSTDIR\ky_doi_autosubmit.py"'
CreateShortCut "$DESKTOP\KY DOI Settings.lnk" "python.exe" '"$INSTDIR\ky_doi_config_gui.py"'
CreateShortCut "$DESKTOP\KY DOI Readme.lnk" "$INSTDIR\KY_DOI_Readme.pdf"
CreateShortCut "$DESKTOP\KY DOI Import Report.lnk" "$INSTDIR\CORRECT KYDOI Primary.rpx"


; ---------------------------------------------------------
; Start Menu
; ---------------------------------------------------------

CreateDirectory "$SMPROGRAMS\KY_DOI"

CreateShortCut "$SMPROGRAMS\KY_DOI\Run Auto Submitter.lnk" "python.exe" '"$INSTDIR\ky_doi_autosubmit.py"'
CreateShortCut "$SMPROGRAMS\KY_DOI\Settings.lnk" "python.exe" '"$INSTDIR\ky_doi_config_gui.py"'
CreateShortCut "$SMPROGRAMS\KY_DOI\Readme.lnk" "$INSTDIR\KY_DOI_Readme.pdf"
CreateShortCut "$SMPROGRAMS\KY_DOI\Import Report.lnk" "$INSTDIR\CORRECT KYDOI Primary.rpx"
CreateShortCut "$SMPROGRAMS\KY_DOI\Uninstall.lnk" "$INSTDIR\Uninstall.exe"


; ---------------------------------------------------------
; Write uninstaller
; ---------------------------------------------------------
WriteUninstaller "$INSTDIR\Uninstall.exe"

SectionEnd


; ---------------------------------------------------------
; UNINSTALLER
; ---------------------------------------------------------
Section "Uninstall"

Delete "$DESKTOP\Run KY DOI Auto Submitter.lnk"
Delete "$DESKTOP\KY DOI Settings.lnk"
Delete "$DESKTOP\KY DOI Readme.lnk"
Delete "$DESKTOP\KY DOI Import Report.lnk"

Delete "$SMPROGRAMS\KY_DOI\Run Auto Submitter.lnk"
Delete "$SMPROGRAMS\KY_DOI\Settings.lnk"
Delete "$SMPROGRAMS\KY_DOI\Readme.lnk"
Delete "$SMPROGRAMS\KY_DOI\Import Report.lnk"
Delete "$SMPROGRAMS\KY_DOI\Uninstall.lnk"

RMDir "$SMPROGRAMS\KY_DOI"

Delete "$INSTDIR\ky_doi_autosubmit.py"
Delete "$INSTDIR\ky_doi_config_gui.py"
Delete "$INSTDIR\KY_DOI_Readme.pdf"
Delete "$INSTDIR\CORRECT KYDOI Primary.rpx"

Delete "$INSTDIR\Uninstall.exe"

RMDir /r "$INSTDIR\incoming"
RMDir /r "$INSTDIR\archive"
RMDir /r "$INSTDIR\logs"

RMDir "$INSTDIR"

SectionEnd
