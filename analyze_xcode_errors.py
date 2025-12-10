#!/usr/bin/env python3
"""
Comprehensive Xcode Build Error Analyzer and Fixer
Automatically detects and fixes common Swift build errors
"""

import re
import subprocess
from pathlib import Path
from typing import List, Tuple, Dict

IOS_PROJECT = Path("/Users/hectorgarcia/LYO_Da_ONE")
PROJECT_FILE = IOS_PROJECT / "Lyo.xcodeproj"

class XcodeBuildFixer:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.fixes_applied = []
        
    def build_project(self) -> Tuple[bool, str]:
        """Build the Xcode project and capture output"""
        print("🔨 Building Xcode project...")
        
        cmd = [
            "xcodebuild",
            "-project", str(PROJECT_FILE),
            "-scheme", "Lyo",
            "-configuration", "Debug",
            "-destination", "platform=iOS Simulator,name=iPhone 15",
            "clean", "build"
        ]
        
        try:
            result = subprocess.run(
                cmd,
                cwd=str(IOS_PROJECT),
                capture_output=True,
                text=True,
                timeout=300
            )
            
            output = result.stdout + result.stderr
            return (result.returncode == 0, output)
            
        except subprocess.TimeoutExpired:
            return (False, "Build timeout after 5 minutes")
        except Exception as e:
            return (False, f"Build error: {str(e)}")
    
    def parse_errors(self, build_output: str):
        """Parse build output for errors and warnings"""
        
        # Error patterns
        error_pattern = re.compile(r"^(.*?):(\d+):(\d+): error: (.+)$", re.MULTILINE)
        warning_pattern = re.compile(r"^(.*?):(\d+):(\d+): warning: (.+)$", re.MULTILINE)
        
        # Find errors
        for match in error_pattern.finditer(build_output):
            file_path, line, col, message = match.groups()
            self.errors.append({
                "file": file_path,
                "line": int(line),
                "col": int(col),
                "message": message
            })
        
        # Find warnings
        for match in warning_pattern.finditer(build_output):
            file_path, line, col, message = match.groups()
            self.warnings.append({
                "file": file_path,
                "line": int(line),
                "col": int(col),
                "message": message
            })
    
    def categorize_errors(self) -> Dict[str, List]:
        """Categorize errors by type"""
        categories = {
            "duplicate_symbols": [],
            "missing_imports": [],
            "type_errors": [],
            "undeclared_identifiers": [],
            "other": []
        }
        
        for error in self.errors:
            msg = error["message"].lower()
            
            if "duplicate" in msg or "redefinition" in msg:
                categories["duplicate_symbols"].append(error)
            elif "cannot find" in msg or "no such module" in msg:
                categories["missing_imports"].append(error)
            elif "cannot convert" in msg or "type" in msg:
                categories["type_errors"].append(error)
            elif "undeclared" in msg or "use of unresolved" in msg:
                categories["undeclared_identifiers"].append(error)
            else:
                categories["other"].append(error)
        
        return categories
    
    def fix_duplicate_main(self):
        """Fix duplicate @main entry point"""
        print("\n🔧 Checking for duplicate @main...")
        
        swift_files = list(IOS_PROJECT.rglob("*.swift"))
        main_files = []
        
        for file_path in swift_files:
            try:
                content = file_path.read_text()
                if re.search(r'^\s*@main\s+struct', content, re.MULTILINE):
                    main_files.append(file_path)
            except:
                continue
        
        if len(main_files) > 1:
            print(f"   ❌ Found {len(main_files)} @main entry points:")
            for f in main_files:
                print(f"      - {f.relative_to(IOS_PROJECT)}")
            
            # Keep only LyoApp.swift, comment out others
            for file_path in main_files:
                if file_path.name != "LyoApp.swift":
                    print(f"   🔧 Commenting out @main in {file_path.name}")
                    content = file_path.read_text()
                    content = re.sub(r'@main', '// @main', content)
                    file_path.write_text(content)
                    self.fixes_applied.append(f"Commented @main in {file_path.name}")
        else:
            print("   ✅ No duplicate @main found")
    
    def fix_missing_imports(self):
        """Add missing imports"""
        print("\n🔧 Checking for missing imports...")
        
        common_fixes = {
            "Color": "import SwiftUI",
            "View": "import SwiftUI",
            "Button": "import SwiftUI",
            "Text": "import SwiftUI",
            "VStack": "import SwiftUI",
            "HStack": "import SwiftUI",
            "URLSession": "import Foundation",
            "JSONDecoder": "import Foundation",
            "Date": "import Foundation"
        }
        
        for error in self.errors:
            if "cannot find" in error["message"].lower():
                # Extract the type name
                match = re.search(r"cannot find.*'(\w+)'", error["message"])
                if match:
                    type_name = match.group(1)
                    if type_name in common_fixes:
                        file_path = Path(error["file"])
                        if file_path.exists():
                            print(f"   🔧 Adding {common_fixes[type_name]} to {file_path.name}")
                            content = file_path.read_text()
                            if common_fixes[type_name] not in content:
                                lines = content.split('\n')
                                # Add import after other imports
                                insert_pos = 0
                                for i, line in enumerate(lines):
                                    if line.startswith('import '):
                                        insert_pos = i + 1
                                lines.insert(insert_pos, common_fixes[type_name])
                                file_path.write_text('\n'.join(lines))
                                self.fixes_applied.append(f"Added {common_fixes[type_name]} to {file_path.name}")
    
    def print_summary(self):
        """Print error summary"""
        print("\n" + "=" * 60)
        print("📊 BUILD ERROR ANALYSIS")
        print("=" * 60)
        
        if not self.errors:
            print("✅ No errors found!")
        else:
            print(f"❌ Found {len(self.errors)} errors")
            
            categories = self.categorize_errors()
            for category, errors in categories.items():
                if errors:
                    print(f"\n{category.replace('_', ' ').title()}: {len(errors)}")
                    for error in errors[:3]:  # Show first 3
                        file_name = Path(error["file"]).name
                        print(f"   • {file_name}:{error['line']} - {error['message'][:80]}")
                    if len(errors) > 3:
                        print(f"   ... and {len(errors) - 3} more")
        
        if self.warnings:
            print(f"\n⚠️  {len(self.warnings)} warnings")
        
        if self.fixes_applied:
            print(f"\n🔧 Applied {len(self.fixes_applied)} fixes:")
            for fix in self.fixes_applied:
                print(f"   ✅ {fix}")
    
    def run(self):
        """Main execution"""
        print("🚀 Xcode Build Error Analyzer & Fixer")
        print("=" * 60)
        
        # Apply common fixes first
        self.fix_duplicate_main()
        self.fix_missing_imports()
        
        # Build project
        success, output = self.build_project()
        
        # Parse errors
        self.parse_errors(output)
        
        # Print summary
        self.print_summary()
        
        # Save full log
        log_file = Path("/tmp/xcode_build_full.log")
        log_file.write_text(output)
        print(f"\n📄 Full build log: {log_file}")
        
        return success

if __name__ == "__main__":
    fixer = XcodeBuildFixer()
    success = fixer.run()
    
    if not success and fixer.errors:
        print("\n" + "=" * 60)
        print("🔄 FIXES APPLIED - Rebuild Required")
        print("=" * 60)
        print("\nRun this script again to verify fixes.")
    
    exit(0 if success else 1)
