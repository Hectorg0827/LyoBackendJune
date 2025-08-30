"""Kubernetes Auto-Scaling Configuration for LyoBackend
Intelligent auto-scaling based on CPU, memory, and custom metrics
"""

# auto-scaling-config.yaml
auto_scaling_config = """
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: lyo-backend-hpa-cpu
  namespace: lyo-backend
  labels:
    app: lyo-backend
    component: autoscaler
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: lyo-backend
  minReplicas: 2
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 50
        periodSeconds: 60
      - type: Pods
        value: 2
        periodSeconds: 60
      selectPolicy: Min
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
      - type: Percent
        value: 100
        periodSeconds: 60
      - type: Pods
        value: 4
        periodSeconds: 60
      selectPolicy: Max

---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: lyo-backend-hpa-request-rate
  namespace: lyo-backend
  labels:
    app: lyo-backend
    component: autoscaler
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: lyo-backend
  minReplicas: 2
  maxReplicas: 50
  metrics:
  - type: External
    external:
      metric:
        name: custom.googleapis.com|lyo_backend|request_rate
        selector:
          matchLabels:
            resource.type: "k8s_container"
            resource.labels.cluster_name: "lyo-backend-cluster"
      target:
        type: Value
        value: "100"
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 600
      policies:
      - type: Percent
        value: 25
        periodSeconds: 120
      selectPolicy: Min
    scaleUp:
      stabilizationWindowSeconds: 120
      policies:
      - type: Percent
        value: 200
        periodSeconds: 60
      selectPolicy: Max

---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: lyo-backend-hpa-trace-duration
  namespace: lyo-backend
  labels:
    app: lyo-backend
    component: autoscaler
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: lyo-backend
  minReplicas: 2
  maxReplicas: 30
  metrics:
  - type: External
    external:
      metric:
        name: custom.googleapis.com|lyo_backend|trace_duration_p95
        selector:
          matchLabels:
            resource.type: "k8s_container"
            resource.labels.cluster_name: "lyo-backend-cluster"
      target:
        type: Value
        value: "2.0"
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 900
      policies:
      - type: Percent
        value: 20
        periodSeconds: 180
      selectPolicy: Min
    scaleUp:
      stabilizationWindowSeconds: 180
      policies:
      - type: Percent
        value: 150
        periodSeconds: 60
      selectPolicy: Max

---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: lyo-backend-hpa-error-rate
  namespace: lyo-backend
  labels:
    app: lyo-backend
    component: autoscaler
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: lyo-backend
  minReplicas: 2
  maxReplicas: 15
  metrics:
  - type: External
    external:
      metric:
        name: custom.googleapis.com|lyo_backend|error_rate
        selector:
          matchLabels:
            resource.type: "k8s_container"
            resource.labels.cluster_name: "lyo-backend-cluster"
      target:
        type: Value
        value: "5"
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 1200
      policies:
      - type: Percent
        value: 10
        periodSeconds: 300
      selectPolicy: Min
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
      - type: Percent
        value: 300
        periodSeconds: 30
      selectPolicy: Max
"""

# Vertical Pod Autoscaler configuration
vpa_config = """
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: lyo-backend-vpa
  namespace: lyo-backend
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: lyo-backend
  updatePolicy:
    updateMode: "Auto"
  resourcePolicy:
    containerPolicies:
    - containerName: lyo-backend
      minAllowed:
        cpu: 100m
        memory: 256Mi
      maxAllowed:
        cpu: 2000m
        memory: 4Gi
      controlledResources: ["cpu", "memory"]
"""

# Cluster Autoscaler configuration for GKE
cluster_autoscaler_config = """
# Enable cluster autoscaler for GKE
gcloud container clusters update lyo-backend-cluster \\
  --enable-autoscaling \\
  --min-nodes 1 \\
  --max-nodes 10 \\
  --node-pool default-pool
"""

# Custom metrics adapter configuration
custom_metrics_config = """
apiVersion: v1
kind: ServiceAccount
metadata:
  name: custom-metrics-stackdriver-adapter
  namespace: custom-metrics
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: custom-metrics-stackdriver-adapter
rules:
- apiGroups:
  - ""
  resources:
  - pods
  - nodes
  verbs:
  - get
  - list
  - watch
- apiGroups:
  - "metrics.k8s.io"
  resources:
  - "*"
  verbs:
  - "*"
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: custom-metrics-stackdriver-adapter
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: custom-metrics-stackdriver-adapter
subjects:
- kind: ServiceAccount
  name: custom-metrics-stackdriver-adapter
  namespace: custom-metrics
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: custom-metrics-stackdriver-adapter
  namespace: custom-metrics
  labels:
    app: custom-metrics-stackdriver-adapter
spec:
  replicas: 1
  selector:
    matchLabels:
      app: custom-metrics-stackdriver-adapter
  template:
    metadata:
      labels:
        app: custom-metrics-stackdriver-adapter
    spec:
      serviceAccountName: custom-metrics-stackdriver-adapter
      containers:
      - name: adapter
        image: gcr.io/gke-release/custom-metrics-stackdriver-adapter:v0.12.0
        ports:
        - containerPort: 8080
        env:
        - name: GOOGLE_APPLICATION_CREDENTIALS
          value: /var/secrets/google/key.json
        volumeMounts:
        - name: google-cloud-key
          mountPath: /var/secrets/google
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "256Mi"
            cpu: "200m"
      volumes:
      - name: google-cloud-key
        secret:
          secretName: lyo-backend-key
"""

# Prometheus adapter for custom metrics
prometheus_adapter_config = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: prometheus-adapter-config
  namespace: custom-metrics
data:
  config.yaml: |
    rules:
    - seriesQuery: 'http_requests_total{namespace="lyo-backend"}'
      resources:
        overrides:
          namespace: {resource: "namespace"}
          pod: {resource: "pod"}
      name:
        matches: "^(.*)_total$"
        as: "${1}_per_second"
      metricsQuery: 'rate(<<.Series>>{<<.LabelMatchers>>}[5m])'

    - seriesQuery: 'trace_duration_seconds{quantile="0.95", namespace="lyo-backend"}'
      resources:
        overrides:
          namespace: {resource: "namespace"}
          pod: {resource: "pod"}
      name:
        matches: "^(.*)$"
        as: "${1}"
      metricsQuery: '<<.Series>>{<<.LabelMatchers>>}'

    - seriesQuery: 'http_requests_total{status=~"5..", namespace="lyo-backend"}'
      resources:
        overrides:
          namespace: {resource: "namespace"}
          pod: {resource: "pod"}
      name:
        matches: "^(.*)_total$"
        as: "${1}_per_second"
      metricsQuery: 'rate(<<.Series>>{<<.LabelMatchers>>}[5m])'
"""

# Auto-scaling deployment script
auto_scaling_deployment_script = """
#!/bin/bash
# Deploy Auto-Scaling Infrastructure

set -e

NAMESPACE=${1:-lyo-backend}
PROJECT_ID=${2:-your-project-id}
CLUSTER_NAME=${3:-lyo-backend-cluster}

echo "🚀 Deploying Auto-Scaling Infrastructure..."
echo "Namespace: $NAMESPACE"
echo "Project: $PROJECT_ID"
echo "Cluster: $CLUSTER_NAME"
echo ""

# Create namespace
kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

# Deploy HPA configurations
echo "📈 Deploying Horizontal Pod Autoscalers..."
python3 -c "
from lyo_app.core.auto_scaling_config import generate_hpa_config
config = generate_hpa_config('$NAMESPACE')
with open('hpa-config.yaml', 'w') as f:
    f.write(config)
"
kubectl apply -f hpa-config.yaml

# Deploy VPA
echo "📊 Deploying Vertical Pod Autoscaler..."
python3 -c "
from lyo_app.core.auto_scaling_config import generate_vpa_config
config = generate_vpa_config('$NAMESPACE')
with open('vpa-config.yaml', 'w') as f:
    f.write(config)
"
kubectl apply -f vpa-config.yaml

# Deploy custom metrics adapter
echo "🔧 Deploying Custom Metrics Adapter..."
kubectl create namespace custom-metrics --dry-run=client -o yaml | kubectl apply -f -
python3 -c "
from lyo_app.core.auto_scaling_config import generate_custom_metrics_config
config = generate_custom_metrics_config()
with open('custom-metrics-config.yaml', 'w') as f:
    f.write(config)
"
kubectl apply -f custom-metrics-config.yaml

# Deploy Prometheus adapter
echo "📊 Deploying Prometheus Adapter..."
python3 -c "
from lyo_app.core.auto_scaling_config import generate_prometheus_adapter_config
config = generate_prometheus_adapter_config()
with open('prometheus-adapter-config.yaml', 'w') as f:
    f.write(config)
"
kubectl apply -f prometheus-adapter-config.yaml

# Enable cluster autoscaler
echo "🔄 Enabling Cluster Autoscaler..."
gcloud container clusters update $CLUSTER_NAME \\
  --enable-autoscaling \\
  --min-nodes 1 \\
  --max-nodes 10 \\
  --node-pool default-pool

# Wait for deployments
echo "⏳ Waiting for deployments..."
kubectl wait --for=condition=available --timeout=300s deployment/custom-metrics-stackdriver-adapter -n custom-metrics

echo ""
echo "✅ Auto-Scaling Infrastructure Deployed!"
echo ""
echo "📋 Auto-Scaling Policies:"
echo "• CPU Utilization: Scale at 70% (2-20 replicas)"
echo "• Memory Utilization: Scale at 80% (2-20 replicas)"
echo "• Request Rate: Scale at 100 req/s (2-50 replicas)"
echo "• Trace Duration P95: Scale at 2.0s (2-30 replicas)"
echo "• Error Rate: Scale at 5% (2-15 replicas)"
echo ""
echo "🔍 Monitor scaling with:"
echo "kubectl get hpa -n $NAMESPACE"
echo "kubectl get vpa -n $NAMESPACE"
"""

def generate_hpa_config(namespace: str = "lyo-backend") -> str:
    """Generate HPA configuration"""
    return auto_scaling_config.replace("lyo-backend", namespace)

def generate_vpa_config(namespace: str = "lyo-backend") -> str:
    """Generate VPA configuration"""
    return vpa_config.replace("lyo-backend", namespace)

def generate_custom_metrics_config() -> str:
    """Generate custom metrics adapter configuration"""
    return custom_metrics_config

def generate_prometheus_adapter_config() -> str:
    """Generate Prometheus adapter configuration"""
    return prometheus_adapter_config

def generate_cluster_autoscaler_config(cluster_name: str = "lyo-backend-cluster") -> str:
    """Generate cluster autoscaler configuration"""
    return cluster_autoscaler_config.replace("lyo-backend-cluster", cluster_name)
