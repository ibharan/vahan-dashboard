#!/bin/bash
# EC2 Setup Script for VAHAN Dashboard
# Run this once after SSH-ing into your EC2 instance
# Usage: bash setup_ec2.sh

set -e
echo "=== VAHAN Dashboard EC2 Setup ==="

# 1. Update system
sudo yum update -y 2>/dev/null || sudo apt-get update -y

# 2. Install Python 3.11
if ! command -v python3 &> /dev/null; then
    sudo yum install -y python3 python3-pip 2>/dev/null || \
    sudo apt-get install -y python3 python3-pip
fi

# 3. Install Chrome for Selenium scraper
echo "Installing Chrome..."
if command -v yum &> /dev/null; then
    # Amazon Linux / RHEL
    sudo yum install -y wget
    wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_x86_64.rpm
    sudo yum install -y ./google-chrome-stable_current_x86_64.rpm
    rm google-chrome-stable_current_x86_64.rpm
else
    # Ubuntu / Debian
    wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
    echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" | \
        sudo tee /etc/apt/sources.list.d/google-chrome.list
    sudo apt-get update -y
    sudo apt-get install -y google-chrome-stable
fi

# 4. Install Python dependencies
echo "Installing Python packages..."
pip3 install --upgrade pip
pip3 install selenium pandas numpy streamlit plotly apscheduler pyyaml openpyxl requests

# 5. Create systemd service for dashboard
echo "Creating systemd service..."
WORK_DIR=$(pwd)
sudo tee /etc/systemd/system/vahan-dashboard.service > /dev/null <<EOF
[Unit]
Description=VAHAN 2-Wheeler Sales Dashboard
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=$WORK_DIR
ExecStart=/usr/bin/python3 -m streamlit run dashboard.py --server.address 0.0.0.0 --server.port 8501 --server.headless true
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 6. Create systemd service for scheduler
sudo tee /etc/systemd/system/vahan-scheduler.service > /dev/null <<EOF
[Unit]
Description=VAHAN Daily Scraper Scheduler
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=$WORK_DIR
ExecStart=/usr/bin/python3 scheduler.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF

# 7. Enable and start services
sudo systemctl daemon-reload
sudo systemctl enable vahan-dashboard
sudo systemctl enable vahan-scheduler
sudo systemctl start vahan-dashboard
sudo systemctl start vahan-scheduler

echo ""
echo "=== Setup Complete ==="
echo "Dashboard running at: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):8501"
echo ""
echo "Useful commands:"
echo "  sudo systemctl status vahan-dashboard   # check dashboard status"
echo "  sudo systemctl status vahan-scheduler   # check scheduler status"
echo "  sudo systemctl restart vahan-dashboard  # restart dashboard"
echo "  sudo journalctl -u vahan-dashboard -f   # view live logs"
