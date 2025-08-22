#!/usr/bin/env python3
"""
🎉 Complete LyoBackend Prompt with Integrated Smoke Tests
========================================================

This script provides the complete prompt experience with integrated smoke testing.
It serves as the unified entry point for understanding and validating the LyoBackend system.

Usage: python complete_prompt_with_smoke_tests.py
"""

import os
import sys
import subprocess
import webbrowser
from pathlib import Path
from datetime import datetime

class LyoBackendPromptRunner:
    """Complete prompt runner with integrated smoke tests."""
    
    def __init__(self):
        self.base_dir = Path(__file__).parent
        self.documentation_files = {
            "comprehensive_prompt": "COMPREHENSIVE_PROMPT_WITH_SMOKE_TESTS.md",
            "smoke_tests_readme": "SMOKE_TESTS_README.md",
            "delivery_complete": "DELIVERY_COMPLETE.md",
            "readme": "README.md"
        }
    
    def print_banner(self):
        """Print the main banner."""
        print("🎉" + "="*68 + "🎉")
        print("🚀        LyoBackend Complete Prompt with Smoke Tests           🚀")
        print("🎉" + "="*68 + "🎉")
        print()
        print("Welcome to the comprehensive LyoBackend experience!")
        print("This system combines full documentation with integrated testing.")
        print()
    
    def show_main_menu(self):
        """Show the main menu options."""
        print("📋 What would you like to do?")
        print()
        print("📖 DOCUMENTATION & GUIDES:")
        print("   1. 🎯 View Complete System Prompt")
        print("   2. 🧪 View Smoke Testing Guide") 
        print("   3. 📊 View System Architecture & Features")
        print("   4. 🔧 View Setup & Installation Guide")
        print()
        print("🧪 TESTING & VALIDATION:")
        print("   5. 🚀 Run Simple Smoke Test (2 minutes)")
        print("   6. ⚡ Run Quick Validation Tests (5-10 minutes)")
        print("   7. 🔬 Run Full System Tests (15-20 minutes)")
        print("   8. 🎮 Interactive Testing Demo")
        print()
        print("🌐 SYSTEM ACCESS:")
        print("   9. 🖥️  Open API Documentation")
        print("   10. 💻 Check Server Status")
        print("   11. 🔍 System Health Check")
        print()
        print("🚪 12. Exit")
        print()
    
    def view_documentation(self, doc_key: str):
        """View documentation file."""
        doc_file = self.documentation_files.get(doc_key)
        if not doc_file:
            print(f"❌ Documentation key '{doc_key}' not found!")
            return
        
        file_path = self.base_dir / doc_file
        if not file_path.exists():
            print(f"❌ Documentation file not found: {doc_file}")
            return
        
        print(f"\n📖 Opening {doc_file}...")
        
        try:
            # Try to open with system's default markdown viewer
            if sys.platform == "darwin":  # macOS
                subprocess.run(["open", str(file_path)], check=False)
            elif sys.platform == "win32":  # Windows
                subprocess.run(["start", str(file_path)], shell=True, check=False)
            else:  # Linux and others
                subprocess.run(["xdg-open", str(file_path)], check=False)
            
            print(f"✅ Opened {doc_file} with system default viewer")
            
        except Exception as e:
            # Fallback: display content in terminal
            print(f"⚠️  Could not open with system viewer: {e}")
            print("📄 Displaying content in terminal:")
            print("-" * 60)
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Show first 2000 characters to avoid overwhelming terminal
                    if len(content) > 2000:
                        print(content[:2000])
                        print("\n... (content truncated)")
                        print(f"💡 Full content available in: {doc_file}")
                    else:
                        print(content)
            except Exception as read_error:
                print(f"❌ Error reading file: {read_error}")
    
    def run_smoke_test(self, test_type: str):
        """Run smoke tests."""
        test_commands = {
            "simple": "python simple_smoke_test.py",
            "quick": "python smoke_tests_runner.py --quick", 
            "full": "python smoke_tests_runner.py --full",
            "demo": "python smoke_test_demo.py"
        }
        
        command = test_commands.get(test_type)
        if not command:
            print(f"❌ Unknown test type: {test_type}")
            return
        
        print(f"\n🧪 Starting {test_type} smoke test...")
        print(f"Command: {command}")
        print("-" * 50)
        
        try:
            # Run the test command
            result = subprocess.run(command.split(), check=False, cwd=self.base_dir)
            
            if result.returncode == 0:
                print("\n✅ Smoke test completed successfully!")
            else:
                print(f"\n⚠️  Smoke test completed with issues (exit code: {result.returncode})")
                
        except FileNotFoundError:
            print(f"❌ Test script not found for command: {command}")
            print("💡 Make sure you're in the correct directory and scripts exist")
        except Exception as e:
            print(f"❌ Error running smoke test: {e}")
    
    def open_api_docs(self):
        """Open API documentation in browser."""
        api_url = "http://localhost:8000/docs"
        print(f"\n🌐 Opening API documentation: {api_url}")
        
        try:
            webbrowser.open(api_url)
            print("✅ API documentation opened in your default browser")
            print("💡 If server isn't running, start it with: python start_server.py")
        except Exception as e:
            print(f"❌ Could not open browser: {e}")
            print(f"💡 Manually visit: {api_url}")
    
    def check_server_status(self):
        """Check if the server is running."""
        print("\n💻 Checking LyoBackend server status...")
        
        try:
            import requests
            response = requests.get("http://localhost:8000/health", timeout=5)
            
            if response.status_code == 200:
                print("✅ Server is running and healthy!")
                try:
                    data = response.json()
                    if isinstance(data, dict) and 'status' in data:
                        print(f"📊 Status: {data['status']}")
                        if 'checks' in data:
                            print(f"🔍 Health checks: {len(data['checks'])}")
                except:
                    pass
            else:
                print(f"⚠️  Server responded with status: {response.status_code}")
                
        except requests.exceptions.ConnectionError:
            print("❌ Server is not running or not accessible")
            print("💡 Start the server with: python start_server.py")
        except ImportError:
            print("❌ requests library not available")
            print("💡 Install with: pip install requests")
        except Exception as e:
            print(f"❌ Error checking server: {e}")
    
    def system_health_check(self):
        """Perform comprehensive system health check."""
        print("\n🔍 Performing system health check...")
        
        # Check Python version
        version = sys.version_info
        if version.major == 3 and version.minor >= 8:
            print(f"✅ Python version: {version.major}.{version.minor}.{version.micro}")
        else:
            print(f"❌ Python version too old: {version.major}.{version.minor}.{version.micro}")
        
        # Check required files
        required_files = [
            "simple_smoke_test.py",
            "smoke_tests_runner.py",
            "requirements.txt",
            "lyo_app/main.py"
        ]
        
        print("\n📁 Checking required files:")
        for file in required_files:
            if Path(file).exists():
                print(f"   ✅ {file}")
            else:
                print(f"   ❌ {file} - Missing")
        
        # Check critical imports
        print("\n📦 Checking critical packages:")
        critical_packages = ["fastapi", "sqlalchemy", "redis", "httpx"]
        
        for package in critical_packages:
            try:
                __import__(package)
                print(f"   ✅ {package}")
            except ImportError:
                print(f"   ❌ {package} - Not installed")
        
        print("\n💡 Run 'pip install -r requirements.txt' to install missing packages")
    
    def run_interactive_session(self):
        """Run the interactive prompt session."""
        while True:
            try:
                self.show_main_menu()
                choice = input("👉 Enter your choice (1-12): ").strip()
                
                if choice == "1":
                    self.view_documentation("comprehensive_prompt")
                
                elif choice == "2":
                    self.view_documentation("smoke_tests_readme")
                
                elif choice == "3":
                    self.view_documentation("delivery_complete")
                
                elif choice == "4":
                    self.view_documentation("readme")
                
                elif choice == "5":
                    self.run_smoke_test("simple")
                
                elif choice == "6":
                    self.run_smoke_test("quick")
                
                elif choice == "7":
                    self.run_smoke_test("full")
                
                elif choice == "8":
                    self.run_smoke_test("demo")
                
                elif choice == "9":
                    self.open_api_docs()
                
                elif choice == "10":
                    self.check_server_status()
                
                elif choice == "11":
                    self.system_health_check()
                
                elif choice == "12":
                    print("\n👋 Thank you for using LyoBackend!")
                    print("🚀 Your comprehensive AI-powered educational platform is ready!")
                    break
                
                else:
                    print("❌ Invalid choice! Please enter a number from 1-12.")
                
                # Pause before showing menu again
                input("\n⏸️  Press Enter to continue...")
                
            except KeyboardInterrupt:
                print("\n\n👋 Thank you for using LyoBackend!")
                break
            except Exception as e:
                print(f"❌ Unexpected error: {e}")
    
    def show_quick_start(self):
        """Show quick start information."""
        print("🎯 QUICK START GUIDE:")
        print("1. 📖 Read the complete prompt: COMPREHENSIVE_PROMPT_WITH_SMOKE_TESTS.md")
        print("2. 🧪 Run simple smoke test: python simple_smoke_test.py")
        print("3. 🌐 Check API docs: http://localhost:8000/docs")
        print("4. 🚀 Start building your app!")
        print()

def main():
    """Main entry point."""
    prompt_runner = LyoBackendPromptRunner()
    
    # Show banner
    prompt_runner.print_banner()
    
    # Check if this is a non-interactive environment
    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        prompt_runner.show_quick_start()
        return
    
    # Show system status
    print("🔍 Quick System Check:")
    print(f"📁 Working directory: {Path.cwd()}")
    print(f"🐍 Python version: {sys.version_info.major}.{sys.version_info.minor}")
    print(f"⏰ Current time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Start interactive session
    prompt_runner.run_interactive_session()

if __name__ == "__main__":
    main()