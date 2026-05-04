@echo off
cd /d "C:\Users\ibharan\OneDrive - amazon.com\Desktop\Business Analyst\KIRO\vahan_dashboard"
python scheduler.py --now >> logs\task_scheduler.log 2>&1
