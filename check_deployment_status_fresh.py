#!/usr/bin/env python3
"""
Fresh Deployment Status Checker for LyoBackend
Auto-discovers and comprehensively tests all deployed services

This tool provides a clean, fresh perspective on deployment status by:
- Auto-discovering Cloud Run services  
- Testing health and functionality of all endpoints
- Providing detailed status reports with actionable recommendations
- Working without manual configuration

Usage:
    python check_deployment_status_fresh.py
    python check_deployment_status_fresh.py --detailed
    python check_deployment_status_fresh.py --project my-project --region us-central1
"""

import subprocess
import json
import sys
import time
import requests
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import argparse
import re

# Colors for output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_header(text: str, color: str = Colors.CYAN):
    """Print a formatted header"""
    print(f"\n{color}{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{color}{Colors.BOLD}{text.center(60)}{Colors.END}")
    print(f"{color}{Colors.BOLD}{'='*60}{Colors.END}")

def print_status(text: str, status: str, details: str = ""):
    """Print a status line with icon"""
    icons = {
        'success': f'{Colors.GREEN}✅',
        'fail': f'{Colors.RED}❌',
        'warning': f'{Colors.YELLOW}⚠️ ',
        'info': f'{Colors.BLUE}ℹ️ ',
        'running': f'{Colors.YELLOW}🔄',
        'unknown': f'{Colors.PURPLE}❓'
    }
    icon = icons.get(status, '•')
    print(f"{icon} {text}{Colors.END}")
    if details:
        print(f"   {Colors.WHITE}{details}{Colors.END}")

def run_command(cmd: List[str], capture_output: bool = True) -> Tuple[bool, str, str]:
    """Run a command and return success, stdout, stderr"""
    try:
        result = subprocess.run(
            cmd, 
            capture_output=capture_output, 
            text=True, 
            timeout=30
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)

def get_gcloud_project() -> Optional[str]:
    """Get the current gcloud project"""
    success, stdout, _ = run_command(['gcloud', 'config', 'get-value', 'project'])
    return stdout if success and stdout != "(unset)" else None

def discover_cloud_run_services(project: str, region: str = "us-central1") -> List[Dict[str, Any]]:
    """Discover all Cloud Run services in the project/region"""
    print_status("Discovering Cloud Run services...", "running")
    
    cmd = [
        'gcloud', 'run', 'services', 'list',
        '--project', project,
        '--region', region,
        '--format', 'json'
    ]
    
    success, stdout, stderr = run_command(cmd)
    
    if not success:
        print_status("Failed to discover services", "fail", stderr)
        return []
    
    try:
        services = json.loads(stdout) if stdout else []
        print_status(f"Found {len(services)} Cloud Run services", "success")
        return services
    except json.JSONDecodeError:
        print_status("Failed to parse service list", "fail", "Invalid JSON response")
        return []

def get_service_details(service_name: str, project: str, region: str) -> Optional[Dict[str, Any]]:
    """Get detailed information about a specific service"""
    cmd = [
        'gcloud', 'run', 'services', 'describe', service_name,
        '--project', project,
        '--region', region,
        '--format', 'json'
    ]
    
    success, stdout, _ = run_command(cmd)
    
    if success and stdout:
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            pass
    return None

def test_endpoint(url: str, endpoint: str = "", method: str = "GET", 
                 data: Dict = None, headers: Dict = None, timeout: int = 10) -> Tuple[bool, int, str, float]:
    """Test an endpoint and return success, status_code, response, latency"""
    full_url = f"{url.rstrip('/')}{endpoint}"
    start_time = time.time()
    
    try:
        if method.upper() == "GET":
            response = requests.get(full_url, headers=headers, timeout=timeout)
        elif method.upper() == "POST":
            response = requests.post(full_url, json=data, headers=headers, timeout=timeout)
        else:
            response = requests.request(method, full_url, json=data, headers=headers, timeout=timeout)
        
        latency = (time.time() - start_time) * 1000
        success = 200 <= response.status_code < 400
        
        try:
            if response.headers.get('content-type', '').startswith('application/json'):
                response_text = response.json()
            else:
                response_text = response.text[:500]
        except:
            response_text = response.text[:500]
        
        return success, response.status_code, response_text, latency
        
    except requests.exceptions.Timeout:
        latency = (time.time() - start_time) * 1000
        return False, 0, "Request timeout", latency
    except Exception as e:
        latency = (time.time() - start_time) * 1000
        return False, 0, str(e), latency

def test_service_health(service_url: str, service_name: str) -> Dict[str, Any]:
    """Comprehensive health check for a service"""
    print_status(f"Testing {service_name} health", "running")
    
    results = {
        'service_name': service_name,
        'service_url': service_url,
        'tests': [],
        'overall_health': 'unknown',
        'total_tests': 0,
        'passed_tests': 0
    }
    
    # Define test endpoints
    test_endpoints = [
        ('/', 'Root endpoint', 'GET'),
        ('/health', 'Health check', 'GET'),
        ('/api/v1', 'API v1 info', 'GET'),
        ('/docs', 'API documentation', 'GET'),
        ('/openapi.json', 'OpenAPI spec', 'GET'),
        ('/api/v1/features', 'Features endpoint', 'GET'),
        ('/api/v1/smoke-test', 'Smoke test', 'GET'),
    ]
    
    for endpoint, description, method in test_endpoints:
        success, status_code, response, latency = test_endpoint(service_url, endpoint, method)
        
        test_result = {
            'endpoint': endpoint,
            'description': description,
            'success': success,
            'status_code': status_code,
            'latency_ms': latency,
            'response_preview': str(response)[:200] if response else ""
        }
        
        results['tests'].append(test_result)
        results['total_tests'] += 1
        
        if success:
            results['passed_tests'] += 1
            print_status(f"{description}: {latency:.0f}ms", "success", f"HTTP {status_code}")
        else:
            print_status(f"{description}: {latency:.0f}ms", "fail", f"HTTP {status_code}")
    
    # Calculate overall health
    success_rate = (results['passed_tests'] / results['total_tests']) * 100 if results['total_tests'] > 0 else 0
    
    if success_rate >= 90:
        results['overall_health'] = 'excellent'
    elif success_rate >= 75:
        results['overall_health'] = 'good'
    elif success_rate >= 50:
        results['overall_health'] = 'fair'
    else:
        results['overall_health'] = 'poor'
    
    results['success_rate'] = success_rate
    
    return results

def test_advanced_functionality(service_url: str, service_name: str) -> Dict[str, Any]:
    """Test advanced functionality like AI endpoints"""
    print_status(f"Testing {service_name} advanced features", "running")
    
    results = {
        'ai_tests': [],
        'auth_tests': [],
        'performance_tests': []
    }
    
    # Test AI endpoints
    ai_endpoints = [
        ('/api/v1/test-ai', 'AI model test', 'GET'),
        ('/api/v1/ai/chat', 'AI chat endpoint', 'POST', {'message': 'Hello', 'session_id': 'test'}),
    ]
    
    for endpoint_data in ai_endpoints:
        if len(endpoint_data) == 3:
            endpoint, description, method = endpoint_data
            data = None
        else:
            endpoint, description, method, data = endpoint_data
        
        success, status_code, response, latency = test_endpoint(
            service_url, endpoint, method, data=data, timeout=15
        )
        
        results['ai_tests'].append({
            'endpoint': endpoint,
            'description': description,
            'success': success,
            'status_code': status_code,
            'latency_ms': latency
        })
        
        if success:
            print_status(f"{description}: {latency:.0f}ms", "success", f"HTTP {status_code}")
        else:
            print_status(f"{description}: {latency:.0f}ms", "warning", f"HTTP {status_code} (may need auth)")
    
    # Performance test
    print_status("Running performance test (5 concurrent requests)", "running")
    latencies = []
    
    for i in range(5):
        success, _, _, latency = test_endpoint(service_url, '/health')
        if success:
            latencies.append(latency)
        time.sleep(0.1)
    
    if latencies:
        avg_latency = sum(latencies) / len(latencies)
        min_latency = min(latencies)
        max_latency = max(latencies)
        
        results['performance_tests'] = {
            'avg_latency_ms': avg_latency,
            'min_latency_ms': min_latency,
            'max_latency_ms': max_latency,
            'successful_requests': len(latencies),
            'total_requests': 5
        }
        
        perf_status = "success" if avg_latency < 1000 else "warning"
        print_status(f"Performance: {len(latencies)}/5 successful", perf_status, 
                    f"Avg: {avg_latency:.0f}ms, Min: {min_latency:.0f}ms, Max: {max_latency:.0f}ms")
    else:
        print_status("Performance test failed", "fail", "No successful requests")
    
    return results

def generate_recommendations(service_results: List[Dict[str, Any]]) -> List[str]:
    """Generate actionable recommendations based on test results"""
    recommendations = []
    
    for result in service_results:
        service_name = result.get('service_name', 'Unknown')
        health = result.get('overall_health', 'unknown')
        success_rate = result.get('success_rate', 0)
        
        if health == 'poor':
            recommendations.append(f"🚨 {service_name}: Critical issues detected (success rate: {success_rate:.1f}%). Check logs immediately.")
        elif health == 'fair':
            recommendations.append(f"⚠️ {service_name}: Some endpoints failing (success rate: {success_rate:.1f}%). Review failed endpoints.")
        elif health == 'good':
            recommendations.append(f"✅ {service_name}: Mostly healthy (success rate: {success_rate:.1f}%). Minor issues to investigate.")
        elif health == 'excellent':
            recommendations.append(f"🎉 {service_name}: Excellent health (success rate: {success_rate:.1f}%). All systems operational.")
    
    # Add general recommendations
    if len([r for r in service_results if r.get('overall_health') in ['poor', 'fair']]) > 0:
        recommendations.append("📋 Next steps: Check service logs with: gcloud run logs read --service=SERVICE_NAME")
        recommendations.append("🔧 Troubleshoot: Verify environment variables and secrets are properly configured")
    
    return recommendations

def main():
    parser = argparse.ArgumentParser(description='Fresh deployment status checker for LyoBackend')
    parser.add_argument('--project', help='GCP Project ID (auto-detected if not provided)')
    parser.add_argument('--region', default='us-central1', help='GCP Region (default: us-central1)')
    parser.add_argument('--detailed', action='store_true', help='Show detailed test results')
    parser.add_argument('--service', help='Check specific service only')
    args = parser.parse_args()
    
    # Start fresh status check
    print_header("🚀 LYOBACKEND FRESH DEPLOYMENT STATUS CHECK")
    print(f"{Colors.CYAN}Starting comprehensive deployment analysis...{Colors.END}")
    print(f"{Colors.WHITE}Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.END}\n")
    
    # Get project
    project = args.project or get_gcloud_project()
    
    if not project:
        print_status("No GCP project configured", "fail", "Run: gcloud config set project YOUR_PROJECT_ID")
        sys.exit(1)
    
    print_status(f"Using project: {project}", "info")
    print_status(f"Using region: {args.region}", "info")
    
    # Discover services
    services = discover_cloud_run_services(project, args.region)
    
    if not services:
        print_status("No Cloud Run services found", "warning", "Consider deploying your backend first")
        sys.exit(0)
    
    # Test each service
    all_results = []
    
    for service in services:
        service_name = service.get('metadata', {}).get('name', 'Unknown')
        
        if args.service and service_name != args.service:
            continue
        
        service_url = service.get('status', {}).get('url')
        
        if not service_url:
            print_status(f"Service {service_name}: No URL found", "fail")
            continue
        
        print_header(f"🧪 TESTING: {service_name.upper()}", Colors.PURPLE)
        print_status(f"Service URL: {service_url}", "info")
        
        # Get detailed service info
        service_details = get_service_details(service_name, project, args.region)
        
        # Basic health tests
        health_results = test_service_health(service_url, service_name)
        
        # Advanced functionality tests
        if args.detailed:
            advanced_results = test_advanced_functionality(service_url, service_name)
            health_results.update(advanced_results)
        
        all_results.append(health_results)
    
    # Summary Report
    print_header("📊 DEPLOYMENT STATUS SUMMARY", Colors.GREEN)
    
    for result in all_results:
        service_name = result['service_name']
        health = result['overall_health']
        success_rate = result.get('success_rate', 0)
        
        health_colors = {
            'excellent': Colors.GREEN,
            'good': Colors.CYAN,
            'fair': Colors.YELLOW,
            'poor': Colors.RED,
            'unknown': Colors.PURPLE
        }
        
        color = health_colors.get(health, Colors.WHITE)
        print(f"{color}🏷️  {service_name}: {health.upper()} ({success_rate:.1f}% success rate){Colors.END}")
        print(f"   📍 {result['service_url']}")
        print(f"   🧪 Tests: {result['passed_tests']}/{result['total_tests']} passed\n")
    
    # Recommendations
    print_header("💡 RECOMMENDATIONS", Colors.YELLOW)
    recommendations = generate_recommendations(all_results)
    
    for rec in recommendations:
        print(f"   {rec}")
    
    # Overall status
    total_services = len(all_results)
    healthy_services = len([r for r in all_results if r.get('overall_health') in ['excellent', 'good']])
    
    print_header("🎯 OVERALL DEPLOYMENT STATUS", Colors.BOLD)
    
    if healthy_services == total_services and total_services > 0:
        print(f"{Colors.GREEN}{Colors.BOLD}🎉 ALL SYSTEMS OPERATIONAL{Colors.END}")
        print(f"   {healthy_services}/{total_services} services are healthy")
    elif healthy_services > 0:
        print(f"{Colors.YELLOW}{Colors.BOLD}⚠️  PARTIAL DEPLOYMENT ISSUES{Colors.END}")
        print(f"   {healthy_services}/{total_services} services are healthy")
    else:
        print(f"{Colors.RED}{Colors.BOLD}🚨 DEPLOYMENT PROBLEMS DETECTED{Colors.END}")
        print(f"   {healthy_services}/{total_services} services are healthy")
    
    print(f"\n{Colors.CYAN}Fresh deployment status check completed!{Colors.END}")
    
    # Exit with appropriate code
    sys.exit(0 if healthy_services == total_services else 1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Status check interrupted by user{Colors.END}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.RED}Unexpected error: {e}{Colors.END}")
        sys.exit(1)