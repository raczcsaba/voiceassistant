#!/bin/zsh
# Builds ADB Keeper without Gradle: aapt2 + javac + d8 + apksigner
set -e
cd "$(dirname $0)"
SDK=${ANDROID_SDK:-$HOME/Library/Android/sdk}; BT=$SDK/build-tools/36.0.0; AJ=$SDK/platforms/android-35/android.jar
JAVA_HOME=${JAVA_HOME:-/Library/Java/JavaVirtualMachines/jdk-21.jdk/Contents/Home}; export JAVA_HOME PATH=$JAVA_HOME/bin:$PATH
rm -rf build && mkdir -p build/classes build/dex build/res
$BT/aapt2 compile --dir res -o build/res.zip
$BT/aapt2 link -o build/base.apk build/res.zip --java build/gen --manifest AndroidManifest.xml -I $AJ --min-sdk-version 30 --target-sdk-version 34 --version-code 8 --version-name 1.6.1
javac --release 11 -classpath $AJ -d build/classes src/hu/csabi/adbkeeper/*.java build/gen/hu/csabi/adbkeeper/R.java
$BT/d8 --release --min-api 30 --lib $AJ --output build/dex build/classes/hu/csabi/adbkeeper/*.class
(cd build/dex && zip -q ../base.apk classes.dex)
$BT/zipalign -f 4 build/base.apk build/aligned.apk
[ -f keystore.jks ] || keytool -genkeypair -keystore keystore.jks -storepass adbkeeper -keypass adbkeeper -alias key -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=ADB Keeper" >/dev/null 2>&1
$BT/apksigner sign --ks keystore.jks --ks-pass pass:adbkeeper --out adbkeeper.apk build/aligned.apk
echo built adbkeeper.apk
