#!/usr/bin/env python3
"""
health_check_unified.py

Health check script for the LyoBackend unified architecture.
This script verifies that all components of the unified architecture
are working properly.
"""
import os
import sys
import argparse
import requests
import json
from typing import Dict, Any, Optional

def check_server(url: str) -> Dict[str, Any]:
    """Check if the server is running and responding properly."""
    try:
        response = requests.get(f"{url}/health", timeout=5)
        if response.status_code == 200:
            return {
                "status": "ok",
                "message": "Server is running and healthy",
                "details": response.json()
            }
        else:
            return {
                "status": "error",
                "message": f"Server responded with status code {response.status_code}",
                "details": response.text
            }
    except requests.exceptions.ConnectionError:
        return {
            "status": "error",
            "message": "Failed to connect to server. Is it running?",
            "details": None
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Unexpected error: {str(e)}",
            "details": None
        }

def check_database_connection(url: str) -> Dict[str, Any]:
    """Check if the database connection is working."""
    try:
        response = requests.get(f"{url}/health/db", timeout=5)
        if response.status_code == 200:
            return {
                "status": "ok",
                "message": "Database connection is healthy",
                "details": response.json()
            }
        else:
            return {
                "status": "error",
                "message": f"Database check failed with status code {response.status_code}",
                "details": response.text
            }
    except requests.exceptions.ConnectionError:
        return {
            "status": "error",
            "message": "Failed to connect to server. Is it running?",
            "details": None
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Unexpected error: {str(e)}",
            "details": None
        }

def check_config(url: str) -> Dict[str, Any]:
    """Check if the configuration is valid."""
    try:
        response = requests.get(f"{url}/health/config", timeout=5)
        if response.status_code == 200:
            return {
                "status": "ok",
                "message": "Configuration is valid",
                "details": response.json()
            }
        else:
            return {
                "status": "error",
                "message": f"Configuration check failed with status code {response.status_code}",
                "details": response.text
            }
    except requests.exceptions.ConnectionError:
        return {
            "status": "error",
            "message": "Failed to connect to server. Is it running?",
            "details": None
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Unexpected error: {str(e)}",
            "details": None
        }

def format_results(results: Dict[str, Dict[str, Any]]) -> str:
    """Format health check results for display."""
    output = "\n" + "=" * 60 + "\n"
    output += "UNIFIED ARCHITECTURE HEALTH CHECK RESULTS\n"
    output += "=" * 60 + "\n\n"
    
    # Count check results
    total = len(results)
    ok = sum(1 for r in results.values() if r["status"] == "ok")
    errors = sum(1 for r in results.values() if r["status"] == "error")
    
    # Display summary
    output += f"Total Checks: {total}\n"
    output += f"Successful: {ok}\n"
    output += f"Failed: {errors}\n\n"
    
    # Display individual check results
    for check_name, result in results.items():
        status = result["status"].upper()
        if status == "OK":
            status_str = f"\033[92m{status}\033[0m"  # Green
        else:
            status_str = f"\033[91m{status}\033[0m"  # Red
            
        output += f"{check_name.upper()}: {status_str}\n"
        output += f"  {result['message']}\n"
        
        # Display details if available and not None
        if result.get("details"):
            if isinstance(result["details"], dict):
                for key, value in result["details"].items():
                    output += f"  - {key}: {value}\n"
            else:
                output += f"  - {result['details']}\n"
        
        output += "\n"
    
    return output

def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Health check for unified architecture")
    parser.add_argument(
        "--url", 
        "-u", 
        default="http://localhost:8000",
        help="Base URL of the server"
    )
    parser.add_argument(
        "--json", 
        "-j", 
        action="store_true",
        help="Output results as JSON"
    )
    
    args = parser.parse_args()
    
    # Run checks
    results = {
        "server": check_server(args.url),
        "database": check_database_connection(args.url),
        "config": check_config(args.url)
    }
    
    # Display results
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(format_results(results))
    
    # Exit with appropriate code
    errors = sum(1 for r in results.values() if r["status"] == "error")
    sys.exit(1 if errors > 0 else 0)

if __name__ == "__main__":
    main()
