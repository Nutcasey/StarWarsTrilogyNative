@echo off
rem Builds Star Wars Trilogy Native: extracts the ROM, recompiles it and builds with MSVC.
rem Usage: build.bat [path to swtrilgy.zip]   (or set SWT_ROM_ZIP, or put it next to
rem this file; only needed the first time)
setlocal
cd /d "%~dp0"
rem Started with a double click (cmd /c): keep the window open at the end so the
rem message can be read
set "PAUSE_AT_END="
for %%a in (%cmdcmdline%) do if /i "%%~a"=="/c" set PAUSE_AT_END=1
rem update.bat and install.bat run it and pause themselves
if defined SWT_NO_PAUSE set "PAUSE_AT_END="
set ZIP=%~1
if "%ZIP%"=="" set ZIP=%SWT_ROM_ZIP%
if "%ZIP%"=="" set ZIP=%~dp0swtrilgy.zip

python -c "" >nul 2>&1 || goto no_python
rem drive_program.bin too: data\ from an older build.bat can lack it (a set without
rem epr-21119), and the game then stops at FAILED FEEDBACK LEVER INITIALIZE
if exist data\crom.bin if exist data\drive_program.bin goto rom_ok
if not exist "%ZIP%" goto no_rom
python tools\romtool.py "%ZIP%" data || goto fail
:rom_ok
python tools\recomp.py data\crom.bin build\gen || goto fail
rem NVIDIA DLSS SDK (not in the repository): fetched from NVIDIA's GitHub the first time
if not exist third_party\ngx\lib\nvsdk_ngx_d.lib (
    call tools\get_dlss.bat || goto fail
)

rem Visual Studio 2022 (Build Tools or any edition) with the C++ tools and its
rem CMake, found with vswhere; the Build Tools default path if vswhere is missing
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
set "VSDIR="
if exist "%VSWHERE%" for /f "usebackq delims=" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 Microsoft.VisualStudio.Component.VC.CMake.Project -property installationPath`) do set "VSDIR=%%i"
if "%VSDIR%"=="" set "VSDIR=%ProgramFiles(x86)%\Microsoft Visual Studio\2022\BuildTools"
if not exist "%VSDIR%\VC\Auxiliary\Build\vcvars64.bat" goto no_vs
call "%VSDIR%\VC\Auxiliary\Build\vcvars64.bat" >nul || goto fail
set "CMAKE=%VSDIR%\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
set "CTEST=%VSDIR%\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\ctest.exe"
if not exist "%CMAKE%" goto no_vs
"%CMAKE%" -S . -B build\cmake -G Ninja -DCMAKE_BUILD_TYPE=Release || goto fail
"%CMAKE%" --build build\cmake || goto fail
"%CTEST%" --test-dir build\cmake --output-on-failure || goto fail
copy /y build\cmake\StarWarsTrilogy.exe StarWarsTrilogy.exe >nul
rem NVIDIA DLSS runtime (official signed DLL) for --aa dlaa
if exist third_party\ngx\bin\nvngx_dlss.dll copy /y third_party\ngx\bin\nvngx_dlss.dll nvngx_dlss.dll >nul
echo.
echo Done: StarWarsTrilogy.exe
if defined PAUSE_AT_END pause
exit /b 0

:fail
echo.
echo Build failed: see the message above.
if defined PAUSE_AT_END pause
exit /b 1

:no_rom
echo ROM not found ^("%ZIP%"^): pass the path to swtrilgy.zip as an argument ^(build.bat D:\roms\swtrilgy.zip^),
echo in the SWT_ROM_ZIP environment variable, or put it next to build.bat. Only needed the first time: it is extracted into data\.
goto fail

:no_python
echo Python 3 not found. Run install.bat instead: it installs Python and the C++ tools, then builds.
goto fail

:no_vs
echo Visual Studio 2022 with the x64 C++ tools and CMake not found ^(looked in "%VSDIR%"^).
echo Run install.bat instead: it installs them, then builds.
goto fail
