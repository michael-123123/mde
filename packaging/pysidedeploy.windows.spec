[app]

# title of your application
title = mde

# project directory - REWRITTEN by packaging/build.sh to point at $BUILD_DIR
# where a staged copy of this spec and mde_launch.py live for the build.
project_dir = @BUILD_DIR@

# source file path - REWRITTEN by packaging/build.sh
input_file = @BUILD_DIR@/mde_launch.py

# directory where the executable output is generated - REWRITTEN
exec_directory = @BUILD_DIR@

# path to .pyproject project file
project_file =

# application icon - REWRITTEN by packaging/build.sh to the absolute path of
# src/markdown_editor/markdown6/icons/markdown-editor-256.png in the repo.
icon = @ICON@

[python]

# python path - left empty; pyside6-deploy picks up whichever python is invoking it
# (under `mamba run -n algo pyside6-deploy`, that's the conda env's python).
python_path =

# python packages to install
packages = Nuitka==4.0.8

# buildozer = for deploying Android application
android_packages = buildozer==1.5.0,cython==0.29.33

[qt]

# comma separated path to qml files required
# normally all the qml files required by the project are added automatically
qml_files = 

# excluded qml plugin binaries
excluded_qml_plugins = 

# qt modules used. comma separated
modules = 

# qt plugins used by the application. only relevant for desktop deployment. for qt plugins used
# in android application see [android][plugins]
plugins = 

[android]

# path to pyside wheel
wheel_pyside = 

# path to shiboken wheel
wheel_shiboken = 

# plugins to be copied to libs folder of the packaged application. comma separated
plugins = 

[nuitka]

# usage description for permissions requested by the app as found in the info.plist file
# of the app bundle
# eg = extra_args = --show-modules --follow-stdlib
macos.permissions = 

# mode of using nuitka. accepts standalone or onefile. default is onefile.
mode = onefile

# (str) specify any extra nuitka arguments
extra_args = --noinclude-qt-translations --include-package=markdown_editor --include-package-data=markdown_editor --include-package=pygments --include-package=markdown --include-package-data=docx

[buildozer]

# build mode
# possible options = [release, debug]
# release creates an aab, while debug creates an apk
mode = debug

# contrains path to pyside6 and shiboken6 recipe dir
recipe_dir = 

# path to extra qt android jars to be loaded by the application
jars_dir = 

# if empty uses default ndk path downloaded by buildozer
ndk_path = 

# if empty uses default sdk path downloaded by buildozer
sdk_path = 

# other libraries to be loaded. comma separated.
# loaded at app startup
local_libs = 

# architecture of deployed platform
# possible values = ["aarch64", "armv7a", "i686", "x86_64"]
arch = 

