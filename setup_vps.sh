#!/bin/bash
# Deploy script — Hetzner CX22 Ubuntu 24.04
# Ejecutar como root: bash setup_vps.sh yourdomain.com

set -e
DOMAIN=${1:?"Usage: bash setup_vps.sh yourdomain.com"}

echo "=== Carbon Farming Tracker — VPS Setup ==="
echo "Domain: $DOMAIN"

# System deps
apt-get update -qq
apt-get install -y -qq \
    python3.12 python3-pip python3-venv \
    nginx certbot python3-certbot-nginx \
    git libgdal-dev gdal-bin libgeos-dev libproj-dev \
    postgresql postgresql-contrib supervisor

# App user
useradd -m -s /bin/bash carbon 2>/dev/null || true
su - carbon << 'USEREOF'
git clone https://github.com/yourusername/carbon-tracker.git ~/app
cd ~/app
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
echo "⚠  Edit ~/app/.env with your credentials before starting"
USEREOF

# Supervisor config — keeps app alive on reboot
cat > /etc/supervisor/conf.d/carbon-streamlit.conf << SUPEOF
[program:carbon-streamlit]
command=/home/carbon/app/venv/bin/streamlit run /home/carbon/app/streamlit_app/app.py --server.port 8501 --server.headless true
directory=/home/carbon/app
user=carbon
autostart=true
autorestart=true
stderr_logfile=/var/log/carbon-streamlit.err.log
stdout_logfile=/var/log/carbon-streamlit.out.log
environment=HOME="/home/carbon",USER="carbon"
SUPEOF

cat > /etc/supervisor/conf.d/carbon-api.conf << SUPEOF
[program:carbon-api]
command=/home/carbon/app/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
directory=/home/carbon/app
user=carbon
autostart=true
autorestart=true
stderr_logfile=/var/log/carbon-api.err.log
stdout_logfile=/var/log/carbon-api.out.log
SUPEOF

# Nginx
sed "s/yourdomain.com/$DOMAIN/g" /home/carbon/app/deploy/nginx.conf \
    > /etc/nginx/sites-available/carbon-tracker
ln -sf /etc/nginx/sites-available/carbon-tracker /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

# SSL
certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m admin@$DOMAIN

# Start
supervisorctl reread && supervisorctl update
supervisorctl start carbon-streamlit carbon-api

echo ""
echo "✅ Deploy complete → https://$DOMAIN"
