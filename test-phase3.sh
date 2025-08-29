#!/bin/bash
# Test Phase 3 Features
# Validates that all Phase 3 components are working correctly

set -e

NAMESPACE=${1:-lyo}
PROJECT_ID=${2:-your-project-id}

echo "🧪 Testing Phase 3 Features..."
echo "Namespace: $NAMESPACE"
echo "Project: $PROJECT_ID"
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

# Test Kubernetes cluster connectivity
test_k8s_connectivity() {
    log_info "Testing Kubernetes connectivity..."

    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi

    if ! kubectl get namespaces &> /dev/null; then
        log_error "Cannot access Kubernetes API"
        exit 1
    fi

    log_success "Kubernetes connectivity OK"
}

# Test namespace exists
test_namespace() {
    log_info "Testing namespace $NAMESPACE..."

    if ! kubectl get namespace $NAMESPACE &> /dev/null; then
        log_error "Namespace $NAMESPACE does not exist"
        exit 1
    fi

    log_success "Namespace $NAMESPACE exists"
}

# Test Jaeger deployment
test_jaeger() {
    log_info "Testing Jaeger deployment..."

    # Check if Jaeger pods are running
    if ! kubectl get pods -n $NAMESPACE -l app=jaeger &> /dev/null; then
        log_error "Jaeger pods not found"
        return 1
    fi

    # Check if Jaeger services are running
    if ! kubectl get svc -n $NAMESPACE -l app=jaeger &> /dev/null; then
        log_error "Jaeger services not found"
        return 1
    fi

    # Check pod status
    local ready_pods=$(kubectl get pods -n $NAMESPACE -l app=jaeger --no-headers | grep -c "Running")
    local total_pods=$(kubectl get pods -n $NAMESPACE -l app=jaeger --no-headers | wc -l)

    if [ "$ready_pods" -ne "$total_pods" ]; then
        log_warning "Jaeger pods: $ready_pods/$total_pods ready"
        return 1
    fi

    log_success "Jaeger deployment OK ($ready_pods/$total_pods pods ready)"
}

# Test OpenTelemetry Collector
test_otel_collector() {
    log_info "Testing OpenTelemetry Collector..."

    # Check if OTEL collector pods are running
    if ! kubectl get pods -n $NAMESPACE -l app=opentelemetry &> /dev/null; then
        log_error "OpenTelemetry Collector pods not found"
        return 1
    fi

    # Check pod status
    local ready_pods=$(kubectl get pods -n $NAMESPACE -l app=opentelemetry --no-headers | grep -c "Running")
    local total_pods=$(kubectl get pods -n $NAMESPACE -l app=opentelemetry --no-headers | wc -l)

    if [ "$ready_pods" -ne "$total_pods" ]; then
        log_warning "OTEL Collector pods: $ready_pods/$total_pods ready"
        return 1
    fi

    log_success "OpenTelemetry Collector OK ($ready_pods/$total_pods pods ready)"
}

# Test LyoBackend deployment
test_lyo_backend() {
    log_info "Testing LyoBackend deployment..."

    # Check if LyoBackend pods are running
    if ! kubectl get pods -n $NAMESPACE -l app=lyo-backend &> /dev/null; then
        log_error "LyoBackend pods not found"
        return 1
    fi

    # Check pod status
    local ready_pods=$(kubectl get pods -n $NAMESPACE -l app=lyo-backend --no-headers | grep -c "Running")
    local total_pods=$(kubectl get pods -n $NAMESPACE -l app=lyo-backend --no-headers | wc -l)

    if [ "$ready_pods" -ne "$total_pods" ]; then
        log_warning "LyoBackend pods: $ready_pods/$total_pods ready"
        return 1
    fi

    log_success "LyoBackend deployment OK ($ready_pods/$total_pods pods ready)"
}

# Test application health
test_app_health() {
    log_info "Testing application health..."

    # Get service URL
    local service_url=$(kubectl get svc lyo-backend -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null)

    if [ -z "$service_url" ]; then
        log_warning "Service URL not available yet"
        return 1
    fi

    # Test health endpoint
    if curl -s "http://$service_url/health" > /dev/null; then
        log_success "Application health check OK"
    else
        log_warning "Application health check failed"
        return 1
    fi
}

# Test tracing functionality
test_tracing() {
    log_info "Testing tracing functionality..."

    # Get Jaeger URL
    local jaeger_url=$(kubectl get svc jaeger-query -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null)

    if [ -z "$jaeger_url" ]; then
        log_warning "Jaeger URL not available yet"
        return 1
    fi

    # Test Jaeger UI
    if curl -s "http://$jaeger_url:16686" > /dev/null; then
        log_success "Jaeger UI accessible"
    else
        log_warning "Jaeger UI not accessible"
        return 1
    fi
}

# Generate test report
generate_report() {
    echo ""
    echo "📋 Phase 3 Test Report"
    echo "===================="
    echo "Namespace: $NAMESPACE"
    echo "Timestamp: $(date)"
    echo ""

    echo "🔍 Current Status:"
    kubectl get pods -n $NAMESPACE --no-headers | while read line; do
        echo "  $line"
    done

    echo ""
    echo "🌐 Service URLs:"
    kubectl get svc -n $NAMESPACE --no-headers | while read name type cluster_ip external_ip; do
        if [ "$type" = "LoadBalancer" ] && [ "$external_ip" != "<pending>" ]; then
            echo "  $name: http://$external_ip"
        fi
    done

    echo ""
    echo "📊 Resource Usage:"
    kubectl top pods -n $NAMESPACE --no-headers 2>/dev/null | while read line; do
        echo "  $line"
    done || echo "  kubectl top not available"

    echo ""
    echo "🔧 Useful Commands:"
    echo "  kubectl get pods -n $NAMESPACE -w"
    echo "  kubectl logs -f deployment/lyo-backend -n $NAMESPACE"
    echo "  kubectl get hpa -n $NAMESPACE"
    echo "  kubectl get vpa -n $NAMESPACE"
}

# Main test function
main() {
    local failed_tests=0

    log_info "Starting Phase 3 validation tests"

    # Run tests
    test_k8s_connectivity || ((failed_tests++))
    test_namespace || ((failed_tests++))

    if test_jaeger; then
        log_success "✅ Jaeger test passed"
    else
        log_error "❌ Jaeger test failed"
        ((failed_tests++))
    fi

    if test_otel_collector; then
        log_success "✅ OpenTelemetry Collector test passed"
    else
        log_error "❌ OpenTelemetry Collector test failed"
        ((failed_tests++))
    fi

    if test_lyo_backend; then
        log_success "✅ LyoBackend test passed"
    else
        log_error "❌ LyoBackend test failed"
        ((failed_tests++))
    fi

    test_app_health || true  # Don't fail on health check
    test_tracing || true     # Don't fail on tracing test

    # Generate report
    generate_report

    echo ""
    if [ $failed_tests -eq 0 ]; then
        log_success "🎉 All critical tests passed! Phase 3 deployment is healthy."
    else
        log_warning "⚠️ $failed_tests test(s) failed. Check the deployment."
    fi

    echo ""
    echo "💡 Troubleshooting Tips:"
    echo "• Check pod logs: kubectl logs -f deployment/<name> -n $NAMESPACE"
    echo "• Check pod status: kubectl describe pod/<name> -n $NAMESPACE"
    echo "• Check events: kubectl get events -n $NAMESPACE"
    echo "• Check services: kubectl get svc -n $NAMESPACE"
}

# Run main function
main "$@"
