# EC2 Deployment Guide — VAHAN Dashboard

## What you need
- Access to AWS Console (your team's AWS account)
- ~15 minutes

---

## Step 1 — Launch an EC2 Instance

1. Go to **AWS Console** → EC2 → **Launch Instance**
2. Configure:
   - **Name:** `vahan-dashboard`
   - **AMI:** Amazon Linux 2023 (free tier eligible)
   - **Instance type:** `t3.small` (2 vCPU, 2GB RAM — enough for dashboard + scraper)
   - **Key pair:** Create new → name it `vahan-key` → Download the `.pem` file → **save it safely**
   - **Network:** Keep default VPC
   - **Security Group:** Create new with these rules:

   | Type | Port | Source | Purpose |
   |------|------|--------|---------|
   | SSH | 22 | Your IP | Admin access |
   | Custom TCP | 8501 | 0.0.0.0/0 | Dashboard access |
   | Custom TCP | 8501 | ::/0 | Dashboard IPv6 |

3. Click **Launch Instance**
4. Wait ~2 minutes for it to start
5. Note the **Public IPv4 address** (e.g. `54.x.x.x`)

---

## Step 2 — Connect to EC2

On your Windows machine, open PowerShell:

```powershell
# Move to where you saved the key
cd Downloads

# Fix key permissions (required)
icacls vahan-key.pem /inheritance:r /grant:r "$($env:USERNAME):(R)"

# SSH into EC2
ssh -i vahan-key.pem ec2-user@YOUR_EC2_PUBLIC_IP
```

You should see a Linux terminal prompt.

---

## Step 3 — Upload your project files

Open a **second PowerShell window** (keep SSH open in first) and run:

```powershell
# Upload entire vahan_dashboard folder to EC2
scp -i Downloads\vahan-key.pem -r "C:\Users\ibharan\OneDrive - amazon.com\Desktop\Business Analyst\KIRO\vahan_dashboard" ec2-user@YOUR_EC2_PUBLIC_IP:~/vahan_dashboard
```

---

## Step 4 — Run the setup script

Back in your SSH terminal:

```bash
cd ~/vahan_dashboard
bash deploy/setup_ec2.sh
```

This will:
- Install Python, Chrome, all dependencies
- Start the dashboard as a background service on port 8501
- Start the daily scheduler (runs at 8 AM IST)
- Auto-restart if the server reboots

At the end it prints your dashboard URL.

---

## Step 5 — Access the dashboard

Your dashboard will be live at:
```
http://YOUR_EC2_PUBLIC_IP:8501
```

Share this link with your team. No VPN needed — works from any browser anywhere.

---

## Step 6 — Make the IP permanent (optional but recommended)

By default EC2 public IP changes on reboot. To fix it:

1. AWS Console → EC2 → **Elastic IPs** → Allocate Elastic IP
2. Associate it with your `vahan-dashboard` instance
3. Your URL becomes permanent: `http://ELASTIC_IP:8501`

---

## Useful commands (run via SSH)

```bash
# Check if dashboard is running
sudo systemctl status vahan-dashboard

# View live dashboard logs
sudo journalctl -u vahan-dashboard -f

# Restart dashboard
sudo systemctl restart vahan-dashboard

# Check scheduler logs
sudo journalctl -u vahan-scheduler -f

# Run pipeline manually
cd ~/vahan_dashboard && python3 run_pipeline.py --now

# Update dashboard (after making changes locally, re-upload and restart)
sudo systemctl restart vahan-dashboard
```

---

## Cost estimate

| Resource | Cost |
|----------|------|
| t3.small EC2 | ~$15/month |
| Storage (20GB) | ~$2/month |
| Data transfer | ~$1/month |
| **Total** | **~$18/month** |

Use your team's AWS account — this qualifies as internal tooling.

---

## Architecture on EC2

```
EC2 Instance (t3.small)
├── vahan-dashboard.service  → Streamlit on port 8501 (always on)
├── vahan-scheduler.service  → Scrapes VAHAN daily at 8 AM IST
└── vahan_dashboard/
    ├── dashboard.py
    ├── data/
    │   ├── vahan_processed.csv      (updated daily)
    │   └── amazon_online_sales.csv  (updated daily)
    └── logs/
```
