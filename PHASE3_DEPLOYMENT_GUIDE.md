# Phase 3 Deployment Guide
# Choose the right deployment option for your needs

## 🎯 Quick Start (Recommended)

If you want to get Phase 3 running quickly without complex setup:

```bash
# One-command deployment
./quick-phase3-setup.sh lyobackend
```

This will:
- ✅ Enable all required APIs automatically
- ✅ Deploy to Cloud Run (simplest option)
- ✅ Include all Phase 3 features
- ✅ Provide monitoring and logging
- ⏱️ Takes ~10-15 minutes

## 🚀 Deployment Options

### Option 1: Quick Cloud Run Deployment (Easiest)
**Best for:** Testing Phase 3 features, development, small production workloads

```bash
./quick-phase3-setup.sh lyobackend
```

**Features:**
- ✅ No Kubernetes knowledge required
- ✅ Automatic scaling (1-10 instances)
- ✅ Built-in monitoring and logging
- ✅ HTTPS by default
- ✅ Pay-per-use pricing
- ⚠️ Limited to Cloud Run capabilities

---

### Option 2: Full GKE Deployment (Most Powerful)
**Best for:** Production workloads, complex scaling requirements, full control

```bash
# Step 1: Enable APIs
./enable-apis.sh lyobackend

# Step 2: Deploy (after APIs are ready)
./minimal-phase3-deploy.sh lyo lyobackend lyo-backend-cluster us-central1
```

**Features:**
- ✅ Full Kubernetes control
- ✅ Advanced auto-scaling with HPA/VPA
- ✅ Jaeger distributed tracing UI
- ✅ Custom metrics and monitoring
- ✅ Enterprise-grade features
- ⚠️ Requires Kubernetes knowledge
- ⚠️ More complex setup

---

### Option 3: Test Existing Deployment
**Best for:** Checking if deployment is working

```bash
./test-phase3.sh lyo lyobackend
```

**Features:**
- ✅ Validates all components
- ✅ Provides health reports
- ✅ Shows service URLs
- ✅ Troubleshooting guidance

## 🔧 Manual API Enabling

If you prefer to enable APIs manually:

1. Go to: https://console.cloud.google.com/apis/library
2. Enable these APIs:
   - Kubernetes Engine API (`container.googleapis.com`)
   - Cloud Build API (`cloudbuild.googleapis.com`)
   - Container Registry API (`containerregistry.googleapis.com`)
   - Cloud Run API (`run.googleapis.com`)
   - Cloud Monitoring API (`monitoring.googleapis.com`)

Or use the automated script:
```bash
./enable-apis.sh lyobackend
```

## 📊 Feature Comparison

| Feature | Cloud Run | GKE Minimal | GKE Full |
|---------|-----------|-------------|----------|
| **Setup Time** | 10 min | 20 min | 45 min |
| **Complexity** | Low | Medium | High |
| **Auto-scaling** | ✅ Basic | ✅ Advanced | ✅ Enterprise |
| **Distributed Tracing** | ✅ Console | ✅ Jaeger UI | ✅ Full Jaeger |
| **AI Optimization** | ✅ Ready | ✅ Ready | ✅ Full |
| **Monitoring** | ✅ Basic | ✅ Advanced | ✅ Enterprise |
| **Cost** | Pay-per-use | Fixed nodes | Fixed nodes |
| **Kubernetes Access** | ❌ | ✅ Limited | ✅ Full |

## 🎯 Recommendation

**For most users:** Start with Cloud Run deployment
```bash
./quick-phase3-setup.sh lyobackend
```

**For production with full control:** Use GKE deployment
```bash
./enable-apis.sh lyobackend
./minimal-phase3-deploy.sh lyo lyobackend lyo-backend-cluster us-central1
```

## 🔍 Troubleshooting

### Common Issues:

1. **"API not enabled" error:**
   ```bash
   ./enable-apis.sh lyobackend
   ```

2. **"Project not found" error:**
   - Check project ID: `gcloud config get-value project`
   - Set correct project: `gcloud config set project YOUR_PROJECT_ID`

3. **Authentication error:**
   ```bash
   gcloud auth login
   ```

4. **Deployment timeout:**
   - Cloud Run: Increase timeout in script
   - GKE: Check cluster resources

### Useful Commands:

```bash
# Check project
gcloud config get-value project

# List services
gcloud run services list

# View logs
gcloud logs read --filter="resource.type=cloud_run_revision"

# Check APIs
gcloud services list --enabled
```

## 📞 Support

If you encounter issues:

1. Run the test script: `./test-phase3.sh lyo lyobackend`
2. Check the logs in Cloud Console
3. Verify API status in Google Cloud Console
4. Ensure billing is enabled for your project

## 🎉 Success Checklist

After deployment, verify:

- [ ] Service is accessible via HTTPS URL
- [ ] Health endpoint responds: `/health`
- [ ] Logs are visible in Cloud Console
- [ ] Auto-scaling is working
- [ ] Monitoring data is being collected

**Happy deploying! 🚀**
