#!/bin/bash
# Complete Phase 3 Deployment Script
# Deploys Distributed Tracing, Auto-Scaling, and AI Optimization

set -e

# Configuration
NAMESPACE=${1:-lyo-backend}
PROJECT_ID=${2:-your-project-id}
CLUSTER_NAME=${3:-lyo-backend-cluster}
REGION=${4:-us-central1}

echo "🚀 Starting Complete Phase 3 Deployment..."
echo "Namespace: $NAMESPACE"
echo "Project: $PROJECT_ID"
echo "Cluster: $CLUSTER_NAME"
echo "Region: $REGION"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check if gcloud is installed
    if ! command -v gcloud &> /dev/null; then
        log_error "gcloud CLI is not installed. Please install it first."
        exit 1
    fi

    # Check if kubectl is installed
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed. Please install it first."
        exit 1
    fi

    # Check if authenticated
    if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | head -n 1 > /dev/null; then
        log_error "Not authenticated with gcloud. Please run 'gcloud auth login' first."
        exit 1
    fi

    log_success "Prerequisites check passed"
}

# Set up GKE cluster
setup_gke_cluster() {
    log_info "Setting up GKE cluster..."

    # Check if cluster exists
    if gcloud container clusters describe $CLUSTER_NAME --region=$REGION &> /dev/null; then
        log_info "Cluster $CLUSTER_NAME already exists"
    else
        log_info "Creating GKE cluster $CLUSTER_NAME..."
        gcloud container clusters create $CLUSTER_NAME \
            --region=$REGION \
            --num-nodes=3 \
            --machine-type=e2-standard-4 \
            --enable-autoscaling \
            --min-nodes=1 \
            --max-nodes=10 \
            --enable-ip-alias \
            --enable-stackdriver-kubernetes
        log_success "GKE cluster created"
    fi

    # Get cluster credentials
    gcloud container clusters get-credentials $CLUSTER_NAME --region=$REGION
    log_success "Cluster credentials configured"
}

# Create namespace
create_namespace() {
    log_info "Creating namespace $NAMESPACE..."
    kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
    log_success "Namespace created"
}

# Deploy Jaeger (Phase 3.1)
deploy_jaeger() {
    log_info "🚀 Deploying Jaeger Distributed Tracing..."

    # Generate Jaeger configuration
    python3 -c "
from lyo_app.core.jaeger_config import generate_jaeger_deployment
config = generate_jaeger_deployment('$NAMESPACE')
with open('jaeger-deployment.yaml', 'w') as f:
    f.write(config)
"

    # Deploy Jaeger
    kubectl apply -f jaeger-deployment.yaml
    log_success "Jaeger deployment applied"

    # Wait for Jaeger to be ready
    log_info "Waiting for Jaeger to be ready..."
    kubectl wait --for=condition=available --timeout=300s deployment/jaeger-collector -n $NAMESPACE
    kubectl wait --for=condition=available --timeout=300s deployment/jaeger-query -n $NAMESPACE

    # Get Jaeger service URL
    JAEGER_URL=$(kubectl get svc jaeger-query -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
    log_success "Jaeger deployed at: http://$JAEGER_URL:16686"
}

# Deploy OpenTelemetry Collector
deploy_otel_collector() {
    log_info "🔧 Deploying OpenTelemetry Collector..."

    # Generate OTEL collector configuration
    python3 -c "
from lyo_app.core.jaeger_config import generate_otel_collector_deployment
config = generate_otel_collector_deployment('$NAMESPACE')
with open('otel-collector-deployment.yaml', 'w') as f:
    f.write(config)
"

    # Deploy OTEL collector
    kubectl apply -f otel-collector-deployment.yaml
    log_success "OpenTelemetry Collector deployment applied"

    # Wait for OTEL collector to be ready
    kubectl wait --for=condition=available --timeout=300s deployment/otel-collector -n $NAMESPACE
    log_success "OpenTelemetry Collector ready"
}

# Deploy Auto-Scaling (Phase 3.2)
deploy_auto_scaling() {
    log_info "📈 Deploying Auto-Scaling Infrastructure..."

    # Generate HPA configuration
    python3 -c "
from lyo_app.core.auto_scaling_config import generate_hpa_config
config = generate_hpa_config('$NAMESPACE')
with open('hpa-config.yaml', 'w') as f:
    f.write(config)
"

    # Generate VPA configuration
    python3 -c "
from lyo_app.core.auto_scaling_config import generate_vpa_config
config = generate_vpa_config('$NAMESPACE')
with open('vpa-config.yaml', 'w') as f:
    f.write(config)
"

    # Generate custom metrics configuration
    python3 -c "
from lyo_app.core.auto_scaling_config import generate_custom_metrics_config
config = generate_custom_metrics_config()
with open('custom-metrics-config.yaml', 'w') as f:
    f.write(config)
"

    # Generate Prometheus adapter configuration
    python3 -c "
from lyo_app.core.auto_scaling_config import generate_prometheus_adapter_config
config = generate_prometheus_adapter_config()
with open('prometheus-adapter-config.yaml', 'w') as f:
    f.write(config)
"

    # Create custom-metrics namespace
    kubectl create namespace custom-metrics --dry-run=client -o yaml | kubectl apply -f -

    # Deploy configurations
    kubectl apply -f hpa-config.yaml
    kubectl apply -f vpa-config.yaml
    kubectl apply -f custom-metrics-config.yaml
    kubectl apply -f prometheus-adapter-config.yaml

    log_success "Auto-scaling infrastructure deployed"
}

# Deploy Prometheus and Grafana
deploy_monitoring() {
    log_info "📊 Deploying Monitoring Stack..."

    # Add Helm repo for Prometheus
    helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
    helm repo update

    # Install Prometheus
    helm upgrade --install prometheus prometheus-community/prometheus \
        --namespace monitoring \
        --create-namespace \
        --set server.service.type=LoadBalancer

    # Add Grafana Helm repo
    helm repo add grafana https://grafana.github.io/helm-charts

    # Install Grafana
    helm upgrade --install grafana grafana/grafana \
        --namespace monitoring \
        --set adminPassword='admin' \
        --set service.type=LoadBalancer

    log_success "Monitoring stack deployed"
}

# Deploy LyoBackend with Phase 3 features
deploy_lyo_backend() {
    log_info "🚀 Deploying LyoBackend with Phase 3 features..."

    # Build and push Docker image
    log_info "Building Docker image..."
    docker build -t gcr.io/$PROJECT_ID/lyo-backend:phase3 .
    docker push gcr.io/$PROJECT_ID/lyo-backend:phase3

    # Generate Kubernetes deployment
    cat > lyo-backend-deployment.yaml << EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: lyo-backend
  namespace: $NAMESPACE
  labels:
    app: lyo-backend
spec:
  replicas: 2
  selector:
    matchLabels:
      app: lyo-backend
  template:
    metadata:
      labels:
        app: lyo-backend
    spec:
      containers:
      - name: lyo-backend
        image: gcr.io/$PROJECT_ID/lyo-backend:phase3
        ports:
        - containerPort: 8000
        env:
        - name: OTEL_TRACES_EXPORTER
          value: "otlp"
        - name: OTEL_EXPORTER_OTLP_ENDPOINT
          value: "http://otel-collector:4318"
        - name: OTEL_SERVICE_NAME
          value: "lyo-backend"
        - name: OTEL_TRACES_SAMPLER
          value: "parentbased_always_on"
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
          limits:
            memory: "1Gi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5

---
apiVersion: v1
kind: Service
metadata:
  name: lyo-backend
  namespace: $NAMESPACE
spec:
  selector:
    app: lyo-backend
  ports:
  - port: 80
    targetPort: 8000
  type: LoadBalancer
EOF

    # Deploy application
    kubectl apply -f lyo-backend-deployment.yaml

    # Wait for deployment
    kubectl wait --for=condition=available --timeout=600s deployment/lyo-backend -n $NAMESPACE

    # Get service URL
    BACKEND_URL=$(kubectl get svc lyo-backend -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
    log_success "LyoBackend deployed at: http://$BACKEND_URL"
}

# Configure Ingress
configure_ingress() {
    log_info "🔗 Configuring Ingress..."

    cat > ingress.yaml << EOF
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: lyo-backend-ingress
  namespace: $NAMESPACE
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  rules:
  - host: api.your-domain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: lyo-backend
            port:
              number: 80
  - host: jaeger.your-domain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: jaeger-query
            port:
              number: 16686
EOF

    kubectl apply -f ingress.yaml
    log_success "Ingress configured"
}

# Setup CI/CD pipeline
setup_cicd() {
    log_info "🔄 Setting up CI/CD pipeline..."

    # Generate Cloud Build configuration
    cat > cloudbuild-phase3.yaml << EOF
steps:
- name: 'gcr.io/cloud-builders/docker'
  args: ['build', '-t', 'gcr.io/\$PROJECT_ID/lyo-backend:\$COMMIT_SHA', '.']
- name: 'gcr.io/cloud-builders/docker'
  args: ['push', 'gcr.io/\$PROJECT_ID/lyo-backend:\$COMMIT_SHA']
- name: 'gcr.io/cloud-builders/gke-deploy'
  args:
  - run
  - --filename=lyo-backend-deployment.yaml
  - --image=gcr.io/\$PROJECT_ID/lyo-backend:\$COMMIT_SHA
  - --location=$REGION
  - --cluster=$CLUSTER_NAME
  - --namespace=$NAMESPACE
EOF

    log_success "CI/CD pipeline configured"
}

# Main deployment function
main() {
    log_info "Starting Complete Phase 3 Deployment"

    check_prerequisites
    setup_gke_cluster
    create_namespace
    deploy_jaeger
    deploy_otel_collector
    deploy_auto_scaling
    deploy_monitoring
    deploy_lyo_backend
    configure_ingress
    setup_cicd

    log_success "🎉 Phase 3 Deployment Complete!"
    echo ""
    echo "📋 Deployment Summary:"
    echo "• Jaeger UI: http://jaeger.your-domain.com"
    echo "• API Endpoint: http://api.your-domain.com"
    echo "• Grafana: http://grafana.your-domain.com"
    echo "• Prometheus: http://prometheus.your-domain.com"
    echo ""
    echo "🔧 Next Steps:"
    echo "1. Update DNS records for your domains"
    echo "2. Configure Grafana dashboards"
    echo "3. Set up alerting rules"
    echo "4. Monitor auto-scaling behavior"
    echo "5. Validate AI optimization decisions"
    echo ""
    echo "📊 Monitoring Commands:"
    echo "• kubectl get hpa -n $NAMESPACE"
    echo "• kubectl get vpa -n $NAMESPACE"
    echo "• kubectl logs -f deployment/lyo-backend -n $NAMESPACE"
}

# Run main function
main "$@"
