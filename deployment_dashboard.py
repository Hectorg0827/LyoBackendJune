#!/usr/bin/env python3
"""
LyoBackend Deployment Dashboard
Complete overview of deployment status, services, and health

This dashboard provides a comprehensive view of:
- All deployed services and their health
- Recent deployment activity  
- Configuration status
- Quick troubleshooting information

Usage:
    python3 deployment_dashboard.py
    python3 deployment_dashboard.py --refresh-rate 30
"""

import subprocess
import json
import sys
import time
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

# Import from our fresh deployment checker
try:
    from check_deployment_status_fresh import (
        Colors, print_header, print_status, run_command, 
        get_gcloud_project, discover_cloud_run_services,
        get_service_details, test_endpoint
    )
except ImportError:
    # Define minimal versions if import fails
    class Colors:
        GREEN = '\033[92m'
        RED = '\033[91m'
        YELLOW = '\033[93m'
        BLUE = '\033[94m'
        CYAN = '\033[96m'
        WHITE = '\033[97m'
        BOLD = '\033[1m'
        END = '\033[0m'
    
    def print_header(text: str, color: str = Colors.CYAN):
        print(f"\n{color}{Colors.BOLD}{'='*60}{Colors.END}")
        print(f"{color}{Colors.BOLD}{text.center(60)}{Colors.END}")
        print(f"{color}{Colors.BOLD}{'='*60}{Colors.END}")
    
    def print_status(text: str, status: str, details: str = ""):
        icons = {'success': '✅', 'fail': '❌', 'warning': '⚠️ ', 'info': 'ℹ️ '}
        icon = icons.get(status, '•')
        print(f"{icon} {text}")
        if details:
            print(f"   {details}")

def get_project_info() -> Dict[str, str]:
    """Get current Google Cloud project information"""
    info = {}
    
    # Get project ID
    success, project_id, _ = run_command(['gcloud', 'config', 'get-value', 'project'])
    if success and project_id and project_id != "(unset)":
        info['project_id'] = project_id
    else:
        info['project_id'] = "Not configured"
    
    # Get default region
    success, region, _ = run_command(['gcloud', 'config', 'get-value', 'run/region'])
    if success and region and region != "(unset)":
        info['default_region'] = region
    else:
        info['default_region'] = "us-central1"
    
    # Get account
    success, account, _ = run_command(['gcloud', 'config', 'get-value', 'account'])
    if success and account and account != "(unset)":
        info['account'] = account
    else:
        info['account'] = "Not authenticated"
    
    return info

def get_recent_deployments(project: str, hours: int = 24) -> List[Dict[str, Any]]:
    """Get recent deployment activity from Cloud Build or Audit logs"""
    deployments = []
    
    # Try to get Cloud Build history
    try:
        cmd = [
            'gcloud', 'builds', 'list',
            '--project', project,
            '--limit', '10',
            '--format', 'json'
        ]
        
        success, stdout, _ = run_command(cmd)
        if success and stdout:
            builds = json.loads(stdout)
            
            for build in builds:
                create_time = build.get('createTime', '')
                if create_time:
                    deployments.append({
                        'timestamp': create_time,
                        'status': build.get('status', 'UNKNOWN'),
                        'source': 'Cloud Build',
                        'details': f"Build {build.get('id', 'unknown')[:8]}"
                    })
    except Exception:
        pass
    
    # If no builds found, try to get service revision history
    if not deployments:
        cmd = [
            'gcloud', 'run', 'revisions', 'list',
            '--project', project,
            '--limit', '5',
            '--format', 'json'
        ]
        
        success, stdout, _ = run_command(cmd)
        if success and stdout:
            try:
                revisions = json.loads(stdout)
                for revision in revisions:
                    metadata = revision.get('metadata', {})
                    create_time = metadata.get('creationTimestamp', '')
                    if create_time:
                        deployments.append({
                            'timestamp': create_time,
                            'status': 'DEPLOYED',
                            'source': 'Cloud Run',
                            'details': f"Revision {metadata.get('name', 'unknown')}"
                        })
            except Exception:
                pass
    
    return deployments[:5]  # Return most recent 5

def get_configuration_status() -> Dict[str, str]:
    """Check configuration and environment status"""
    status = {}
    
    # Check if common environment files exist
    env_files = ['.env.production', '.env.staging', '.env.development']
    for env_file in env_files:
        try:
            with open(env_file, 'r') as f:
                content = f.read()
                if 'CHANGE-THIS-IN-PRODUCTION' in content:
                    status[env_file] = 'Needs configuration'
                else:
                    status[env_file] = 'Configured'
        except FileNotFoundError:
            status[env_file] = 'Missing'
    
    # Check if Docker files exist
    docker_files = ['Dockerfile', 'Dockerfile.cloud', 'docker-compose.yml']
    for docker_file in docker_files:
        try:
            with open(docker_file, 'r') as f:
                status[docker_file] = 'Available'
        except FileNotFoundError:
            status[docker_file] = 'Missing'
    
    return status

def display_dashboard(project_info: Dict[str, str], refresh_rate: int = 0):
    """Display the complete deployment dashboard"""
    
    while True:
        # Clear screen (optional)
        if refresh_rate > 0:
            print('\033[H\033[J', end='')
        
        # Header
        print_header("🎛️ LYOBACKEND DEPLOYMENT DASHBOARD", Colors.CYAN)
        print(f"{Colors.WHITE}Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.END}")
        
        if refresh_rate > 0:
            print(f"{Colors.YELLOW}Auto-refresh every {refresh_rate}s (Ctrl+C to stop){Colors.END}")
        
        # Project Information
        print_header("📋 PROJECT INFORMATION", Colors.BLUE)
        print_status(f"Project ID: {project_info['project_id']}", 
                    "success" if project_info['project_id'] != "Not configured" else "fail")
        print_status(f"Default Region: {project_info['default_region']}", "info")
        print_status(f"Account: {project_info['account']}", 
                    "success" if project_info['account'] != "Not authenticated" else "fail")
        
        # Service Status
        if project_info['project_id'] != "Not configured":
            print_header("🚀 SERVICE STATUS", Colors.GREEN)
            
            services = discover_cloud_run_services(project_info['project_id'], project_info['default_region'])
            
            if services:
                for service in services:
                    service_name = service.get('metadata', {}).get('name', 'Unknown')
                    service_url = service.get('status', {}).get('url', '')
                    
                    if service_url:
                        # Quick health check
                        success, status_code, _, latency = test_endpoint(service_url, '/health', timeout=5)
                        if success:
                            print_status(f"{service_name}: HEALTHY", "success", 
                                       f"{service_url} ({latency:.0f}ms)")
                        else:
                            print_status(f"{service_name}: UNHEALTHY", "fail", 
                                       f"{service_url} (HTTP {status_code})")
                    else:
                        print_status(f"{service_name}: NO URL", "warning", "Service may be deploying")
            else:
                print_status("No services found", "warning", "No Cloud Run services deployed")
            
            # Recent Deployments
            print_header("📈 RECENT ACTIVITY", Colors.PURPLE)
            deployments = get_recent_deployments(project_info['project_id'])
            
            if deployments:
                for deployment in deployments:
                    timestamp = deployment['timestamp'][:19].replace('T', ' ')
                    status = deployment['status']
                    details = deployment['details']
                    
                    status_icon = "success" if status in ['SUCCESS', 'DEPLOYED'] else "warning"
                    print_status(f"{timestamp}: {status}", status_icon, details)
            else:
                print_status("No recent deployment activity found", "info")
        
        # Configuration Status
        print_header("⚙️ CONFIGURATION STATUS", Colors.YELLOW)
        config_status = get_configuration_status()
        
        for file_name, status in config_status.items():
            if status == "Configured" or status == "Available":
                print_status(f"{file_name}: {status}", "success")
            elif status == "Needs configuration":
                print_status(f"{file_name}: {status}", "warning", "Update production secrets")
            else:
                print_status(f"{file_name}: {status}", "info")
        
        # Quick Actions
        print_header("🛠️ QUICK ACTIONS", Colors.CYAN)
        print(f"   {Colors.GREEN}•{Colors.END} Fresh status check: {Colors.WHITE}./fresh_deployment_check.sh{Colors.END}")
        print(f"   {Colors.GREEN}•{Colors.END} Quick status: {Colors.WHITE}./quick_status.sh{Colors.END}")
        print(f"   {Colors.GREEN}•{Colors.END} Deploy: {Colors.WHITE}./one-click-deploy.sh{Colors.END}")
        print(f"   {Colors.GREEN}•{Colors.END} Monitor: {Colors.WHITE}./monitor_deployment.py lyo-backend us-central1{Colors.END}")
        print(f"   {Colors.GREEN}•{Colors.END} Logs: {Colors.WHITE}gcloud run logs read --service=lyo-backend{Colors.END}")
        
        # Break if not in refresh mode
        if refresh_rate == 0:
            break
        
        try:
            time.sleep(refresh_rate)
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}Dashboard stopped by user{Colors.END}")
            break

def main():
    parser = argparse.ArgumentParser(description='LyoBackend Deployment Dashboard')
    parser.add_argument('--refresh-rate', type=int, default=0, 
                       help='Auto-refresh rate in seconds (0 for no refresh)')
    args = parser.parse_args()
    
    # Get project information
    project_info = get_project_info()
    
    # Display dashboard
    display_dashboard(project_info, args.refresh_rate)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Dashboard interrupted by user{Colors.END}")
        sys.exit(0)
    except Exception as e:
        print(f"\n{Colors.RED}Error: {e}{Colors.END}")
        sys.exit(1)