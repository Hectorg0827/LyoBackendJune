#!/bin/bash
# Complete Xcode Build Fix Workflow

set -e

echo "🚀 Starting Complete Xcode Build Fix"
echo "======================================"

# Step 1: Merge integration files
echo ""
echo "📁 Step 1: Merging integration files..."
python3 merge_integration_files.py

# Step 2: Analyze and fix build errors
echo ""
echo "🔍 Step 2: Analyzing build errors..."
python3 analyze_xcode_errors.py

echo ""
echo "======================================"
echo "✅ Complete! Check output above for results."
