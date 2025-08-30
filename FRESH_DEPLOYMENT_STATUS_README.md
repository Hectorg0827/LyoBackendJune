# 🚀 Fresh Deployment Status Checker

A comprehensive, auto-discovery deployment status checker for LyoBackend that provides a fresh perspective on your Google Cloud Run deployments.

## 🎯 **THE ULTIMATE FRESH START COMMAND**

For the quickest fresh deployment status check, run:
```bash
./start_fresh_deployment_check.sh
```
This master script provides a complete 4-phase analysis:
1. **Environment Validation** - Python, Google Cloud SDK, dependencies
2. **Configuration Assessment** - Environment files, Docker configs
3. **Service Discovery & Status** - Auto-discovers and tests all deployments  
4. **Summary & Recommendations** - Actionable next steps

## ✨ Features

- **Auto-Discovery**: Automatically finds all Cloud Run services in your project
- **Comprehensive Testing**: Tests health, API endpoints, documentation, and advanced features
- **Smart Recommendations**: Provides actionable insights based on test results
- **No Manual Configuration**: Works without requiring service URLs or manual setup
- **Detailed Reporting**: Color-coded status reports with latency metrics
- **Production Ready**: Handles errors gracefully and provides useful exit codes

## 🎯 Quick Start

### 1. **Master Fresh Check (Recommended)**
```bash
# Complete 4-phase deployment analysis
./start_fresh_deployment_check.sh
```

### 2. Simple Check
```bash
# Auto-discover and test all deployments
./fresh_deployment_check.sh
```

### 3. **Interactive Dashboard**
```bash
# Live deployment dashboard
python3 deployment_dashboard.py

# Auto-refreshing dashboard
python3 deployment_dashboard.py --refresh-rate 30
```

### 4. Detailed Analysis
```bash
# Get comprehensive analysis with advanced tests
./fresh_deployment_check.sh --detailed
```

### 5. Quick Status
```bash
# Fast status check
./quick_status.sh

# Demo mode (no GCP required)
./quick_status.sh --demo
```

## 📋 Prerequisites

- Python 3.6+
- Google Cloud SDK (`gcloud`)
- Authenticated Google Cloud session
- Requests library (auto-installed if missing)

## 🛠️ Usage Options

### Command Line Interface
```bash
# Basic usage
python3 check_deployment_status_fresh.py

# Specify project and region
python3 check_deployment_status_fresh.py --project my-project --region us-west1

# Detailed analysis with performance tests
python3 check_deployment_status_fresh.py --detailed

# Check specific service only
python3 check_deployment_status_fresh.py --service lyo-backend

# Get help
python3 check_deployment_status_fresh.py --help
```

### Shell Script Wrapper
```bash
# Auto-installs dependencies and runs checks
./fresh_deployment_check.sh [options]
```

## 📊 What Gets Tested

### Basic Health Checks
- ✅ Root endpoint (`/`)
- ✅ Health check (`/health`)
- ✅ API v1 info (`/api/v1`)
- ✅ API documentation (`/docs`)
- ✅ OpenAPI specification (`/openapi.json`)
- ✅ Features endpoint (`/api/v1/features`)
- ✅ Smoke test endpoint (`/api/v1/smoke-test`)

### Advanced Tests (with --detailed flag)
- 🤖 AI model endpoints
- 🔐 Authentication flows
- ⚡ Performance testing (5 concurrent requests)
- 📈 Latency analysis

## 🎨 Output Format

The tool provides color-coded output:
- 🟢 **Green**: All tests passed (Excellent health)
- 🔵 **Blue/Cyan**: Most tests passed (Good health)  
- 🟡 **Yellow**: Some issues detected (Fair health)
- 🔴 **Red**: Major problems (Poor health)

## 📈 Health Status Levels

| Status | Success Rate | Description |
|--------|--------------|-------------|
| **EXCELLENT** | 90-100% | All systems operational |
| **GOOD** | 75-89% | Minor issues, mostly healthy |
| **FAIR** | 50-74% | Some endpoints failing |
| **POOR** | 0-49% | Major deployment problems |

## 🔧 Troubleshooting

### No GCP Project
```bash
gcloud config set project YOUR_PROJECT_ID
```

### Not Authenticated
```bash
gcloud auth login
```

### Missing Dependencies
The script auto-installs `requests` if missing, but you can manually install:
```bash
pip3 install requests
```

### No Services Found
If no Cloud Run services are discovered:
1. Check you're in the right project: `gcloud config get-value project`
2. Verify services exist: `gcloud run services list --region=us-central1`
3. Make sure you have the right region specified

## 🚀 Integration

### CI/CD Pipeline
```bash
# Use exit codes for pipeline decisions
if python3 check_deployment_status_fresh.py; then
    echo "Deployment healthy, proceeding..."
else
    echo "Deployment issues detected, stopping pipeline"
    exit 1
fi
```

### Monitoring Scripts
```bash
# Run checks every 5 minutes
*/5 * * * * /path/to/fresh_deployment_check.sh --detailed >> /var/log/deployment-status.log
```

## 📝 Output Examples

### Healthy Deployment
```
🎉 ALL SYSTEMS OPERATIONAL
   2/2 services are healthy

🏷️  lyo-backend: EXCELLENT (100.0% success rate)
   📍 https://lyo-backend-abc123-uc.a.run.app
   🧪 Tests: 7/7 passed
```

### Issues Detected
```
⚠️  PARTIAL DEPLOYMENT ISSUES  
   1/2 services are healthy

🏷️  lyo-backend-staging: FAIR (57.1% success rate)
   📍 https://lyo-backend-staging-xyz456-uc.a.run.app
   🧪 Tests: 4/7 passed
```

## 🤝 Contributing

This tool is part of the LyoBackend deployment infrastructure. To contribute:

1. Test your changes with the demo mode
2. Ensure backwards compatibility
3. Update documentation for new features
4. Test with various deployment scenarios

## 📄 License

Part of the LyoBackend project. See main project license for details.

---

## 🛠️ Complete Tool Suite

| Script | Purpose | Best For |
|--------|---------|----------|
| `start_fresh_deployment_check.sh` | **Master fresh start** - Complete 4-phase analysis | First-time deployment checks, comprehensive analysis |
| `fresh_deployment_check.sh` | Simple auto-discovery deployment testing | Quick deployment validation |
| `deployment_dashboard.py` | Interactive deployment dashboard | Live monitoring, continuous oversight |
| `quick_status.sh` | Fast status check with fallbacks | CI/CD pipelines, quick validation |
| `check_deployment_status_fresh.py` | Core deployment testing engine | Advanced users, custom integrations |
| `demo_deployment_status.py` | Demo mode for testing/training | Learning how the tools work |

**Start with**: `./start_fresh_deployment_check.sh` for your first fresh deployment status check!