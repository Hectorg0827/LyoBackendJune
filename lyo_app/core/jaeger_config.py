"""Jaeger Distributed Tracing Configuration for Kubernetes
Complete Jaeger deployment with OpenTelemetry integration
"""

# jaeger-deployment.yaml
jaeger_k8s_config = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: jaeger-config
  namespace: lyo-backend
data:
  jaeger-config.yml: |
    service:
      extensions: [jaeger_storage, jaeger_query]
      pipelines:
        traces:
          receivers: [otlp]
          processors: [batch]
          exporters: [jaeger_storage_exporter]
        metrics:
          receivers: [otlp]
          processors: [batch]
          exporters: [prometheus]

    extensions:
      jaeger_storage:
        backends:
          memory:
            max_traces: 100000
      jaeger_query:
        storage:
          traces: jaeger_storage

    receivers:
      otlp:
        protocols:
          grpc:
            endpoint: 0.0.0.0:4317
          http:
            endpoint: 0.0.0.0:4318

    processors:
      batch:
        timeout: 1s
        send_batch_size: 1024

    exporters:
      jaeger_storage_exporter:
        jaeger_storage:
          backend: memory
      prometheus:
        endpoint: 0.0.0.0:8889

---
apiVersion: v1
kind: Service
metadata:
  name: jaeger-collector
  namespace: lyo-backend
  labels:
    app: jaeger
    component: collector
spec:
  ports:
  - name: grpc
    port: 4317
    protocol: TCP
    targetPort: 4317
  - name: http
    port: 4318
    protocol: TCP
    targetPort: 4318
  selector:
    app: jaeger
    component: collector
  type: ClusterIP

---
apiVersion: v1
kind: Service
metadata:
  name: jaeger-query
  namespace: lyo-backend
  labels:
    app: jaeger
    component: query
spec:
  ports:
  - name: query
    port: 16686
    protocol: TCP
    targetPort: 16686
  selector:
    app: jaeger
    component: query
  type: ClusterIP

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: jaeger-collector
  namespace: lyo-backend
  labels:
    app: jaeger
    component: collector
spec:
  replicas: 1
  selector:
    matchLabels:
      app: jaeger
      component: collector
  template:
    metadata:
      labels:
        app: jaeger
        component: collector
    spec:
      containers:
      - name: jaeger-collector
        image: jaegertracing/jaeger-collector:latest
        ports:
        - containerPort: 4317
          name: grpc
          protocol: TCP
        - containerPort: 4318
          name: http
          protocol: TCP
        env:
        - name: SPAN_STORAGE_TYPE
          value: "memory"
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /
            port: 13133
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /
            port: 13133
          initialDelaySeconds: 5
          periodSeconds: 5

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: jaeger-query
  namespace: lyo-backend
  labels:
    app: jaeger
    component: query
spec:
  replicas: 1
  selector:
    matchLabels:
      app: jaeger
      component: query
  template:
    metadata:
      labels:
        app: jaeger
        component: query
    spec:
      containers:
      - name: jaeger-query
        image: jaegertracing/jaeger-query:latest
        ports:
        - containerPort: 16686
          name: query
          protocol: TCP
        env:
        - name: SPAN_STORAGE_TYPE
          value: "memory"
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /
            port: 16686
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /
            port: 16686
            httpHeaders:
            - name: Accept
              value: application/json
          initialDelaySeconds: 5
          periodSeconds: 5

---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: jaeger-ingress
  namespace: lyo-backend
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
spec:
  rules:
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
"""

# jaeger-otel-collector-config.yaml
otel_collector_config = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: otel-collector-config
  namespace: lyo-backend
data:
  config.yaml: |
    receivers:
      otlp:
        protocols:
          grpc:
            endpoint: 0.0.0.0:4317
          http:
            endpoint: 0.0.0.0:4318

    processors:
      batch:
        timeout: 1s
        send_batch_size: 1024
      memory_limiter:
        limit_mib: 512
        spike_limit_mib: 128
        check_interval: 5s

    exporters:
      jaeger:
        endpoint: jaeger-collector:4317
        tls:
          insecure: true
      prometheus:
        endpoint: 0.0.0.0:8889
      logging:
        loglevel: debug

    service:
      pipelines:
        traces:
          receivers: [otlp]
          processors: [memory_limiter, batch]
          exporters: [jaeger, logging]
        metrics:
          receivers: [otlp]
          processors: [memory_limiter, batch]
          exporters: [prometheus, logging]

---
apiVersion: v1
kind: Service
metadata:
  name: otel-collector
  namespace: lyo-backend
  labels:
    app: opentelemetry
    component: otel-collector
spec:
  ports:
  - name: grpc-otlp
    port: 4317
    protocol: TCP
    targetPort: 4317
  - name: http-otlp
    port: 4318
    protocol: TCP
    targetPort: 4318
  - name: metrics
    port: 8889
    protocol: TCP
    targetPort: 8889
  selector:
    app: opentelemetry
    component: otel-collector
  type: ClusterIP

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: otel-collector
  namespace: lyo-backend
  labels:
    app: opentelemetry
    component: otel-collector
spec:
  replicas: 1
  selector:
    matchLabels:
      app: opentelemetry
      component: otel-collector
  template:
    metadata:
      labels:
        app: opentelemetry
        component: otel-collector
    spec:
      containers:
      - name: otel-collector
        image: otel/opentelemetry-collector:latest
        ports:
        - containerPort: 4317
          name: grpc-otlp
          protocol: TCP
        - containerPort: 4318
          name: http-otlp
          protocol: TCP
        - containerPort: 8889
          name: metrics
          protocol: TCP
        volumeMounts:
        - name: config
          mountPath: /etc/otelcol
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /
            port: 13133
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /
            port: 13133
          initialDelaySeconds: 5
          periodSeconds: 5
      volumes:
      - name: config
        configMap:
          name: otel-collector-config
"""

# Prometheus configuration for tracing metrics
prometheus_tracing_config = """
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  # - "first_rules.yml"
  # - "second_rules.yml"

scrape_configs:
  - job_name: 'jaeger-collector'
    static_configs:
      - targets: ['jaeger-collector:8889']

  - job_name: 'otel-collector'
    static_configs:
      - targets: ['otel-collector:8889']

  - job_name: 'lyo-backend'
    static_configs:
      - targets: ['lyo-backend:8000']
    scrape_interval: 5s
    metrics_path: '/metrics'
"""

# Grafana dashboard configuration for tracing
grafana_tracing_dashboard = """
{
  "dashboard": {
    "id": null,
    "title": "LyoBackend Distributed Tracing",
    "tags": ["lyo-backend", "tracing", "opentelemetry"],
    "timezone": "browser",
    "panels": [
      {
        "id": 1,
        "title": "Request Rate",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(http_requests_total[5m])",
            "legendFormat": "{{method}} {{endpoint}}"
          }
        ]
      },
      {
        "id": 2,
        "title": "Trace Duration",
        "type": "graph",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(trace_duration_bucket[5m]))",
            "legendFormat": "95th percentile"
          }
        ]
      },
      {
        "id": 3,
        "title": "Error Rate by Service",
        "type": "graph",
        "targets": [
          {
            "expr": "rate(trace_count_total{status=\"error\"}[5m]) / rate(trace_count_total[5m]) * 100",
            "legendFormat": "{{service}}"
          }
        ]
      }
    ],
    "time": {
      "from": "now-1h",
      "to": "now"
    },
    "timepicker": {},
    "templating": {
      "list": []
    },
    "annotations": {
      "list": []
    },
    "refresh": "5s",
    "schemaVersion": 27,
    "version": 0,
    "links": []
  }
}
"""

def generate_jaeger_deployment(namespace: str = "lyo-backend") -> str:
    """Generate Jaeger deployment configuration"""
    return jaeger_k8s_config.replace("lyo-backend", namespace)

def generate_otel_collector_deployment(namespace: str = "lyo-backend") -> str:
    """Generate OpenTelemetry collector deployment configuration"""
    return otel_collector_config.replace("lyo-backend", namespace)

def generate_prometheus_config() -> str:
    """Generate Prometheus configuration for tracing"""
    return prometheus_tracing_config

def generate_grafana_dashboard() -> str:
    """Generate Grafana dashboard configuration for tracing"""
    return grafana_tracing_dashboard

# Deployment script for tracing infrastructure
tracing_deployment_script = """
#!/bin/bash
# Deploy Distributed Tracing Infrastructure

set -e

NAMESPACE=${1:-lyo-backend}
PROJECT_ID=${2:-your-project-id}

echo "🚀 Deploying Distributed Tracing Infrastructure..."
echo "Namespace: $NAMESPACE"
echo "Project: $PROJECT_ID"
echo ""

# Create namespace
kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -

# Deploy Jaeger
echo "📊 Deploying Jaeger..."
python3 -c "
from lyo_app.core.jaeger_config import generate_jaeger_deployment
config = generate_jaeger_deployment('$NAMESPACE')
with open('jaeger-deployment.yaml', 'w') as f:
    f.write(config)
"
kubectl apply -f jaeger-deployment.yaml

# Deploy OpenTelemetry Collector
echo "🔧 Deploying OpenTelemetry Collector..."
python3 -c "
from lyo_app.core.jaeger_config import generate_otel_collector_deployment
config = generate_otel_collector_deployment('$NAMESPACE')
with open('otel-collector-deployment.yaml', 'w') as f:
    f.write(config)
"
kubectl apply -f otel-collector-deployment.yaml

# Wait for deployments
echo "⏳ Waiting for deployments..."
kubectl wait --for=condition=available --timeout=300s deployment/jaeger-collector -n $NAMESPACE
kubectl wait --for=condition=available --timeout=300s deployment/jaeger-query -n $NAMESPACE
kubectl wait --for=condition=available --timeout=300s deployment/otel-collector -n $NAMESPACE

# Get service URLs
echo "🌐 Service URLs:"
echo "Jaeger UI: http://$(kubectl get svc jaeger-query -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].ip}'):16686"
echo "OTel Collector: http://$(kubectl get svc otel-collector -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].ip}'):4317"

echo ""
echo "✅ Distributed Tracing Infrastructure Deployed!"
echo ""
echo "📋 Next Steps:"
echo "1. Update your application with OTEL environment variables"
echo "2. Access Jaeger UI for trace visualization"
echo "3. Configure Grafana dashboards"
echo "4. Set up Prometheus for metrics collection"
"""
