#!/bin/bash

# 🔐 SSL Certificate Management for LyoBackendJune Production
# This script sets up SSL certificates using Let's Encrypt with Certbot

set -e

# Configuration
DOMAIN=${1:-"your-domain.com"}
EMAIL=${2:-"admin@your-domain.com"}
STAGING=${3:-false}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔐 SSL Certificate Setup for LyoBackendJune${NC}"
echo -e "${BLUE}Domain: ${DOMAIN}${NC}"
echo -e "${BLUE}Email: ${EMAIL}${NC}"
echo -e "${BLUE}Staging: ${STAGING}${NC}"
echo ""

# Validate inputs
if [[ "$DOMAIN" == "your-domain.com" ]]; then
    echo -e "${RED}❌ Please provide a valid domain name${NC}"
    echo "Usage: $0 <domain> <email> [staging]"
    echo "Example: $0 api.lyobackend.com admin@lyobackend.com false"
    exit 1
fi

if [[ "$EMAIL" == "admin@your-domain.com" ]]; then
    echo -e "${RED}❌ Please provide a valid email address${NC}"
    echo "Usage: $0 <domain> <email> [staging]"
    echo "Example: $0 api.lyobackend.com admin@lyobackend.com false"
    exit 1
fi

# Create necessary directories
echo -e "${YELLOW}📁 Creating SSL directories...${NC}"
mkdir -p ./docker/ssl/certs
mkdir -p ./docker/ssl/www
mkdir -p ./docker/ssl/conf.d

# Create initial nginx configuration for ACME challenge
echo -e "${YELLOW}⚙️ Creating initial nginx config...${NC}"
cat > ./docker/ssl/conf.d/default.conf << 'EOF'
server {
    listen 80;
    listen [::]:80;
    
    server_name _;
    server_tokens off;
    
    # ACME challenge location
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
        try_files $uri =404;
    }
    
    # Redirect all other traffic to HTTPS
    location / {
        return 301 https://$host$request_uri;
    }
}
EOF

# Create docker-compose for SSL setup
echo -e "${YELLOW}🐳 Creating SSL setup docker-compose...${NC}"
cat > ./docker-compose.ssl.yml << EOF
version: '3.8'

services:
  nginx-ssl:
    image: nginx:alpine
    container_name: lyo-nginx-ssl
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./docker/ssl/conf.d:/etc/nginx/conf.d
      - ./docker/ssl/www:/var/www/certbot
      - ./docker/ssl/certs:/etc/letsencrypt
    networks:
      - lyo-network
    restart: unless-stopped

  certbot:
    image: certbot/certbot:latest
    container_name: lyo-certbot
    volumes:
      - ./docker/ssl/www:/var/www/certbot
      - ./docker/ssl/certs:/etc/letsencrypt
    networks:
      - lyo-network
    command: |
      sh -c "
        if [ '$STAGING' = 'true' ]; then
          STAGING_FLAG='--staging'
        else
          STAGING_FLAG=''
        fi
        certbot certonly \\
          --webroot \\
          --webroot-path=/var/www/certbot \\
          --email $EMAIL \\
          --agree-tos \\
          --no-eff-email \\
          \$\$STAGING_FLAG \\
          -d $DOMAIN
      "

networks:
  lyo-network:
    driver: bridge

EOF

# Start nginx for ACME challenge
echo -e "${YELLOW}🚀 Starting nginx for ACME challenge...${NC}"
docker-compose -f docker-compose.ssl.yml up -d nginx-ssl

# Wait for nginx to be ready
echo -e "${YELLOW}⏳ Waiting for nginx to be ready...${NC}"
sleep 10

# Test if domain is accessible
echo -e "${YELLOW}🌐 Testing domain accessibility...${NC}"
if curl -s -o /dev/null -w "%{http_code}" "http://${DOMAIN}/.well-known/acme-challenge/test" | grep -q "404"; then
    echo -e "${GREEN}✅ Domain is accessible${NC}"
else
    echo -e "${RED}❌ Domain is not accessible. Please check DNS configuration.${NC}"
    echo -e "${YELLOW}💡 Make sure your domain points to this server's IP address.${NC}"
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${RED}❌ Stopping SSL setup${NC}"
        docker-compose -f docker-compose.ssl.yml down
        exit 1
    fi
fi

# Request SSL certificate
echo -e "${YELLOW}🔐 Requesting SSL certificate...${NC}"
if docker-compose -f docker-compose.ssl.yml run --rm certbot; then
    echo -e "${GREEN}✅ SSL certificate obtained successfully${NC}"
else
    echo -e "${RED}❌ Failed to obtain SSL certificate${NC}"
    echo -e "${YELLOW}💡 Try using staging mode first: $0 $DOMAIN $EMAIL true${NC}"
    docker-compose -f docker-compose.ssl.yml down
    exit 1
fi

# Create production nginx configuration with SSL
echo -e "${YELLOW}⚙️ Creating production nginx config with SSL...${NC}"
cat > ./docker/ssl/conf.d/default.conf << EOF
# Rate limiting zones
limit_req_zone \$binary_remote_addr zone=api:10m rate=100r/m;
limit_req_zone \$binary_remote_addr zone=auth:10m rate=20r/m;
limit_req_zone \$binary_remote_addr zone=upload:10m rate=10r/m;

# Upstream backend servers
upstream lyo_backend {
    least_conn;
    server lyo-api-1:8000 max_fails=3 fail_timeout=30s;
    server lyo-api-2:8000 max_fails=3 fail_timeout=30s;
    keepalive 32;
}

# HTTP to HTTPS redirect
server {
    listen 80;
    listen [::]:80;
    
    server_name $DOMAIN;
    server_tokens off;
    
    # ACME challenge location
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
        try_files \$uri =404;
    }
    
    # Redirect all other traffic to HTTPS
    location / {
        return 301 https://\$host\$request_uri;
    }
}

# HTTPS server
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    
    server_name $DOMAIN;
    server_tokens off;
    
    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    
    # Modern SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    
    # SSL session settings
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_session_tickets off;
    
    # OCSP stapling
    ssl_stapling on;
    ssl_stapling_verify on;
    ssl_trusted_certificate /etc/letsencrypt/live/$DOMAIN/chain.pem;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self' wss: https:;" always;
    
    # General settings
    client_max_body_size 100M;
    proxy_connect_timeout 60s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;
    
    # Enable gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types
        text/plain
        text/css
        text/xml
        text/javascript
        application/json
        application/javascript
        application/xml+rss
        application/atom+xml
        image/svg+xml;
    
    # API routes with rate limiting
    location /api/ {
        limit_req zone=api burst=50 nodelay;
        
        proxy_pass http://lyo_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Port \$server_port;
        
        proxy_cache_bypass \$http_upgrade;
        proxy_buffering off;
    }
    
    # Authentication routes with stricter rate limiting
    location ~ ^/api/(auth|login|register|password) {
        limit_req zone=auth burst=10 nodelay;
        
        proxy_pass http://lyo_backend;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    # File upload routes with strict rate limiting
    location ~ ^/api/(upload|files) {
        limit_req zone=upload burst=5 nodelay;
        
        proxy_pass http://lyo_backend;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        client_max_body_size 100M;
    }
    
    # WebSocket support
    location /ws/ {
        proxy_pass http://lyo_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
    }
    
    # Health check endpoint
    location /health {
        access_log off;
        return 200 "healthy\\n";
        add_header Content-Type text/plain;
    }
    
    # Metrics endpoint (restrict access)
    location /metrics {
        allow 10.0.0.0/8;
        allow 172.16.0.0/12;
        allow 192.168.0.0/16;
        allow 127.0.0.1;
        deny all;
        
        proxy_pass http://lyo_backend;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    # Block common attack patterns
    location ~ /\\.ht {
        deny all;
    }
    
    location ~ /\\.(env|git|svn) {
        deny all;
    }
}
EOF

# Reload nginx with SSL configuration
echo -e "${YELLOW}🔄 Reloading nginx with SSL configuration...${NC}"
docker-compose -f docker-compose.ssl.yml exec nginx-ssl nginx -s reload

# Create SSL renewal script
echo -e "${YELLOW}🔄 Creating SSL renewal script...${NC}"
cat > ./docker/ssl/renew-ssl.sh << 'EOF'
#!/bin/bash

# SSL Certificate Renewal Script
# Run this script monthly via cron to auto-renew certificates

set -e

echo "🔄 Renewing SSL certificates..."

# Renew certificates
docker-compose -f docker-compose.ssl.yml run --rm certbot renew

# Reload nginx to pick up new certificates
docker-compose -f docker-compose.ssl.yml exec nginx-ssl nginx -s reload

echo "✅ SSL certificate renewal completed"
EOF

chmod +x ./docker/ssl/renew-ssl.sh

# Create cron job setup script
cat > ./docker/ssl/setup-cron.sh << 'EOF'
#!/bin/bash

# Setup cron job for SSL renewal
# Run this once to set up automatic SSL renewal

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CRON_CMD="0 2 1 * * $SCRIPT_DIR/renew-ssl.sh >> $SCRIPT_DIR/renewal.log 2>&1"

echo "📅 Setting up cron job for SSL renewal..."

# Add to crontab if not already present
(crontab -l 2>/dev/null | grep -v "$SCRIPT_DIR/renew-ssl.sh"; echo "$CRON_CMD") | crontab -

echo "✅ Cron job created: $CRON_CMD"
echo "📋 Current crontab:"
crontab -l
EOF

chmod +x ./docker/ssl/setup-cron.sh

# Test SSL configuration
echo -e "${YELLOW}🧪 Testing SSL configuration...${NC}"
sleep 5

if curl -s -I "https://${DOMAIN}/health" | grep -q "200 OK"; then
    echo -e "${GREEN}✅ SSL configuration is working correctly${NC}"
    echo -e "${GREEN}🔐 HTTPS is now enabled for ${DOMAIN}${NC}"
else
    echo -e "${YELLOW}⚠️ SSL test inconclusive. Manual verification recommended.${NC}"
fi

# Clean up SSL setup containers
echo -e "${YELLOW}🧹 Cleaning up SSL setup containers...${NC}"
docker-compose -f docker-compose.ssl.yml down

echo ""
echo -e "${GREEN}🎉 SSL Setup Complete!${NC}"
echo ""
echo -e "${BLUE}📋 Next Steps:${NC}"
echo -e "1. Update your main docker-compose.production.yml to use the SSL nginx config"
echo -e "2. Run: ${YELLOW}./docker/ssl/setup-cron.sh${NC} to enable automatic renewal"
echo -e "3. Test your SSL grade at: ${BLUE}https://www.ssllabs.com/ssltest/analyze.html?d=${DOMAIN}${NC}"
echo -e "4. Update DNS CAA records for additional security"
echo ""
echo -e "${GREEN}✅ Your LyoBackendJune is now secured with SSL/TLS!${NC}"
