#!/bin/bash

# Dependency Management Script
# Usage: ./deps.sh [install|install-dev|update|check|clean]

set -e

case "${1:-help}" in
    "install")
        echo "Installing production dependencies..."
        pip install -r requirements.txt
        ;;
    "install-dev")
        echo "Installing development dependencies..."
        pip install -r requirements.txt
        pip install -r requirements-dev.txt
        ;;
    "install-all")
        echo "Installing all dependencies..."
        pip install -r requirements.txt
        pip install -r requirements-dev.txt
        ;;
    "update")
        echo "Updating all dependencies..."
        pip install --upgrade -r requirements.txt
        pip install --upgrade -r requirements-dev.txt
        ;;
    "check")
        echo "Checking for outdated packages..."
        pip list --outdated
        ;;
    "clean")
        echo "Cleaning pip cache..."
        pip cache purge
        ;;
    "size")
        echo "Analyzing dependency sizes..."
        pip install pipdeptree
        pipdeptree --total-avg
        ;;
    "help"|*)
        echo "Dependency Management Script"
        echo ""
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  install      Install production dependencies only"
        echo "  install-dev  Install production + development dependencies"
        echo "  install-all  Install all dependencies (same as install-dev)"
        echo "  update       Update all dependencies to latest versions"
        echo "  check        Check for outdated packages"
        echo "  clean        Clean pip cache"
        echo "  size         Analyze dependency sizes (requires pipdeptree)"
        echo "  help         Show this help message"
        ;;
esac
