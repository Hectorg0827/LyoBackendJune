#!/bin/bash
# Fix Xcode project build errors

set -e

IOS_PROJECT="/Users/hectorgarcia/LYO_Da_ONE"
CONFUSING_FOLDER="$IOS_PROJECT/Lyo"
SOURCES_FOLDER="$IOS_PROJECT/Sources"

echo "🔍 Analyzing Xcode Project Build Errors"
echo "========================================"

# Step 1: Check if confusing Lyo folder exists
if [ -d "$CONFUSING_FOLDER" ]; then
    echo "⚠️  Found confusing /Lyo/ folder that's not in the Xcode project"
    echo "   This folder should be deleted to avoid confusion"
    echo ""
    echo "Files in $CONFUSING_FOLDER:"
    find "$CONFUSING_FOLDER" -name "*.swift" -type f
    echo ""
fi

# Step 2: Check Sources folder
echo ""
echo "📁 Checking Sources folder..."
if [ -d "$SOURCES_FOLDER" ]; then
    echo "✅ Sources folder exists"
    echo ""
    echo "Current structure:"
    ls -la "$SOURCES_FOLDER"
    echo ""
    echo "Swift files in Sources:"
    find "$SOURCES_FOLDER" -name "*.swift" -type f 2>/dev/null || echo "   No Swift files found"
else
    echo "❌ Sources folder doesn't exist!"
fi

# Step 3: Try to build and capture errors
echo ""
echo "🔨 Attempting to build project..."
cd "$IOS_PROJECT"

# Clean build folder
echo "Cleaning build folder..."
rm -rf build/

# Build and capture errors
xcodebuild \
    -project Lyo.xcodeproj \
    -scheme Lyo \
    -configuration Debug \
    -destination 'platform=iOS Simulator,name=iPhone 15' \
    clean build 2>&1 | tee /tmp/xcode_build_errors.log

# Parse errors
echo ""
echo "📊 Build Error Summary:"
echo "======================="
grep -i "error:" /tmp/xcode_build_errors.log || echo "No errors found"
echo ""
echo "⚠️  Warnings:"
grep -i "warning:" /tmp/xcode_build_errors.log | head -10 || echo "No warnings found"

echo ""
echo "Full log saved to: /tmp/xcode_build_errors.log"
