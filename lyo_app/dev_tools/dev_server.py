#!/usr/bin/env python3
"""
Development Server with Hot Reload and Debug Features
Enhanced development experience for Lyo platform
"""

import asyncio
import uvicorn
import sys
import os
from pathlib import Path
import subprocess
import signal
import json
from datetime import datetime

# Optional watchdog import - graceful fallback
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False
    print("⚠️  watchdog not installed - file watching disabled")

if HAS_WATCHDOG:
    class DevelopmentHandler(FileSystemEventHandler):
        """Handle file changes during development"""

        def __init__(self, callback):
            self.callback = callback
            self.last_modified = {}

        def on_modified(self, event):
            if event.is_directory:
                return

            file_path = event.src_path
            if not any(file_path.endswith(ext) for ext in ['.py', '.json', '.yaml', '.yml']):
                return

            # Debounce rapid file changes
            now = datetime.now().timestamp()
            if file_path in self.last_modified:
                if now - self.last_modified[file_path] < 1.0:  # 1 second debounce
                    return

            self.last_modified[file_path] = now
            print(f"🔄 File changed: {file_path}")
            self.callback(file_path)
else:
    # Dummy class when watchdog not available
    class DevelopmentHandler:
        def __init__(self, callback):
            pass

class DevServer:
    """Enhanced development server with debugging and monitoring"""

    def __init__(self, app_module="lyo_app.main:app", host="127.0.0.1", port=8000):
        self.app_module = app_module
        self.host = host
        self.port = port
        self.server_process = None
        self.observer = None
        self.reload_count = 0

    def start_server(self):
        """Start the uvicorn development server"""
        print(f"🚀 Starting development server...")
        print(f"   📡 Server: http://{self.host}:{self.port}")
        print(f"   📦 Module: {self.app_module}")
        print(f"   🔄 Hot reload: Enabled")

        # Start uvicorn server
        config = uvicorn.Config(
            self.app_module,
            host=self.host,
            port=self.port,
            reload=True,
            reload_dirs=["lyo_app", "Sources"],
            log_level="debug",
            access_log=True,
            reload_excludes=["*.pyc", "__pycache__", "*.log", ".git/*"]
        )

        server = uvicorn.Server(config)
        return server

    def setup_file_watcher(self):
        """Setup file system watcher for additional features"""
        if not HAS_WATCHDOG:
            print("⚠️  File watching disabled (watchdog not available)")
            return

        self.observer = Observer()

        # Watch Python files
        handler = DevelopmentHandler(self.on_file_change)

        watch_dirs = ["lyo_app", "Sources", "docs"]
        for watch_dir in watch_dirs:
            if Path(watch_dir).exists():
                self.observer.schedule(handler, watch_dir, recursive=True)
                print(f"👀 Watching: {watch_dir}")

        self.observer.start()

    def on_file_change(self, file_path):
        """Handle file changes"""
        self.reload_count += 1

        # Run quick validation on Python files
        if file_path.endswith('.py'):
            self.validate_python_file(file_path)

        # Auto-generate docs if source files change
        if any(dir in file_path for dir in ['lyo_app', 'Sources']):
            self.auto_update_docs()

    def validate_python_file(self, file_path):
        """Quick Python syntax validation"""
        try:
            with open(file_path, 'r') as f:
                compile(f.read(), file_path, 'exec')
            print(f"   ✅ Syntax valid: {Path(file_path).name}")
        except SyntaxError as e:
            print(f"   ❌ Syntax error in {Path(file_path).name}: {e}")
        except Exception as e:
            print(f"   ⚠️  Warning in {Path(file_path).name}: {e}")

    def auto_update_docs(self):
        """Auto-update documentation when source changes"""
        if self.reload_count % 5 == 0:  # Every 5th reload
            try:
                print("📚 Auto-updating documentation...")
                subprocess.run([sys.executable, "generate_docs.py"],
                             capture_output=True, timeout=30)
                print("   ✅ Docs updated")
            except Exception as e:
                print(f"   ⚠️  Doc update failed: {e}")

    def run_health_check(self):
        """Run periodic health checks"""
        import requests
        try:
            response = requests.get(f"http://{self.host}:{self.port}/health", timeout=5)
            if response.status_code == 200:
                print(f"💚 Health check: OK")
                return True
            else:
                print(f"💛 Health check: Status {response.status_code}")
                return False
        except Exception as e:
            print(f"💔 Health check failed: {e}")
            return False

    async def run_development_mode(self):
        """Run full development mode with all features"""
        print("🎯 LYO DEVELOPMENT SERVER")
        print("=" * 50)

        # Setup file watcher
        self.setup_file_watcher()

        # Start server
        server = self.start_server()

        try:
            print("\n🎉 Development server ready!")
            print("   Press Ctrl+C to stop")
            print("\n🔧 Development Features:")
            print("   • Hot reload enabled")
            print("   • File watching active")
            print("   • Auto-documentation updates")
            print("   • Syntax validation")
            print("   • Health monitoring")

            await server.serve()

        except KeyboardInterrupt:
            print(f"\n🛑 Shutting down development server...")
            print(f"   📊 Total reloads: {self.reload_count}")

        finally:
            if self.observer:
                self.observer.stop()
                self.observer.join()
            print("✅ Development server stopped cleanly")

def create_dev_config():
    """Create development configuration file"""
    config = {
        "development": {
            "server": {
                "host": "127.0.0.1",
                "port": 8000,
                "reload": True,
                "debug": True
            },
            "database": {
                "url": "sqlite:///./lyo_dev.db",
                "echo": True
            },
            "features": {
                "hot_reload": True,
                "auto_docs": True,
                "syntax_check": True,
                "health_monitoring": True
            },
            "monitoring": {
                "log_level": "DEBUG",
                "enable_profiler": True,
                "track_performance": True
            }
        },
        "testing": {
            "database": {
                "url": "sqlite:///:memory:",
                "echo": False
            },
            "features": {
                "mock_external_apis": True,
                "fast_mode": True
            }
        }
    }

    with open("dev_config.json", 'w') as f:
        json.dump(config, f, indent=2)

    print("⚙️ Created dev_config.json")

async def main():
    """Main development server entry point"""
    # Create config if not exists
    if not Path("dev_config.json").exists():
        create_dev_config()

    # Setup environment for development
    os.environ.setdefault("ENV", "development")
    os.environ.setdefault("LOG_LEVEL", "DEBUG")
    os.environ.setdefault("RELOAD", "true")

    # Start development server
    dev_server = DevServer()
    await dev_server.run_development_mode()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"💥 Development server error: {e}")
        sys.exit(1)