#!/bin/bash
# Health check script for LyoBackendJune

set -e

# Check if the application is responding
if curl -f -s http://localhost:8000/health > /dev/null; then
    echo "Application health check: PASSED"
else
    echo "Application health check: FAILED"
    exit 1
fi

# Check database connectivity (optional, can be done via app health endpoint)
# if pg_isready -h postgres -p 5432 -U postgres > /dev/null; then
#     echo "Database health check: PASSED"
# else
#     echo "Database health check: FAILED"
#     exit 1
# fi

# Check Redis connectivity (optional)
# if redis-cli -h redis -p 6379 ping > /dev/null; then
#     echo "Redis health check: PASSED"
# else
#     echo "Redis health check: FAILED"
#     exit 1
# fi

echo "All health checks passed"
exit 0
