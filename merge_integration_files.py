#!/usr/bin/env python3
"""
Merge integration files into the correct Xcode project structure
and clean up the confusing duplicate folder.
"""

import os
import shutil
from pathlib import Path

# Paths
IOS_PROJECT = Path("/Users/hectorgarcia/LYO_Da_ONE")
CONFUSING_FOLDER = IOS_PROJECT / "Lyo"
SOURCES_FOLDER = IOS_PROJECT / "Sources"

# Integration files to merge
INTEGRATION_FILES = {
    "Services": [
        "AIClassroomService.swift",
        "APIConfig.swift",
        "InteractiveCinemaService.swift",
        "SmartAIService.swift",
        "LyoAppAPIClient+Production.swift"
    ],
    "Views": [
        "ContentView.swift",
        "AIClassroomView.swift",
        "InteractiveCinemaView.swift"
    ],
    "Utils": [
        "AdMobIntegration.swift",
        "CelebrationAnimations.swift",
        "NavigationIntegration.swift"
    ]
}

def main():
    print("🔧 Merging Integration Files into Xcode Project")
    print("=" * 50)
    
    # Check if confusing folder exists
    if not CONFUSING_FOLDER.exists():
        print(f"❌ Confusing folder not found: {CONFUSING_FOLDER}")
        return False
    
    # Check if Sources folder exists
    if not SOURCES_FOLDER.exists():
        print(f"⚠️  Sources folder doesn't exist: {SOURCES_FOLDER}")
        print("   Creating Sources folder structure...")
        SOURCES_FOLDER.mkdir(parents=True, exist_ok=True)
    
    print(f"✅ Found confusing folder: {CONFUSING_FOLDER}")
    print(f"✅ Target folder: {SOURCES_FOLDER}")
    print()
    
    # Copy files from confusing folder to Sources
    copied_files = []
    skipped_files = []
    
    for folder, files in INTEGRATION_FILES.items():
        source_dir = CONFUSING_FOLDER / folder
        target_dir = SOURCES_FOLDER / folder
        
        # Create target directory if it doesn't exist
        target_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"📁 Processing {folder}/")
        
        for filename in files:
            source_file = source_dir / filename
            target_file = target_dir / filename
            
            if source_file.exists():
                # Check if target already exists
                if target_file.exists():
                    print(f"   ⚠️  {filename} already exists in Sources/{folder}/")
                    print(f"      Backing up as {filename}.backup")
                    backup_file = target_dir / f"{filename}.backup"
                    shutil.copy2(target_file, backup_file)
                
                # Copy the file
                shutil.copy2(source_file, target_file)
                print(f"   ✅ Copied {filename}")
                copied_files.append(f"{folder}/{filename}")
            else:
                print(f"   ❌ Not found: {filename}")
                skipped_files.append(f"{folder}/{filename}")
    
    # Handle LyoApp.swift specially (root level)
    lyo_app_source = CONFUSING_FOLDER / "LyoApp.swift"
    lyo_app_target = SOURCES_FOLDER / "LyoApp.swift"
    
    if lyo_app_source.exists():
        if lyo_app_target.exists():
            print(f"   ⚠️  LyoApp.swift already exists in Sources/")
            print(f"      Backing up as LyoApp.swift.backup")
            shutil.copy2(lyo_app_target, SOURCES_FOLDER / "LyoApp.swift.backup")
        
        shutil.copy2(lyo_app_source, lyo_app_target)
        print(f"   ✅ Copied LyoApp.swift")
        copied_files.append("LyoApp.swift")
    
    print()
    print("📊 Summary:")
    print(f"   ✅ Copied {len(copied_files)} files")
    if skipped_files:
        print(f"   ⚠️  Skipped {len(skipped_files)} files")
    
    # Ask to delete confusing folder
    print()
    print("🗑️  Cleaning up confusing folder...")
    print(f"   Deleting: {CONFUSING_FOLDER}")
    
    try:
        shutil.rmtree(CONFUSING_FOLDER)
        print("   ✅ Confusing folder deleted")
    except Exception as e:
        print(f"   ❌ Error deleting folder: {e}")
        return False
    
    print()
    print("=" * 50)
    print("✅ Integration files merged successfully!")
    print()
    print("📍 Next steps:")
    print("   1. Open Xcode project")
    print("   2. Build the project (Cmd+B)")
    print("   3. Fix any remaining errors")
    
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
