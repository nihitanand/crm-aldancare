#!/usr/bin/env python3
"""
CRM 26 – Monthly Firebase Backup
Runs on 1st of every month via GitHub Actions cron.
Reads crm26/v1/proposals from Firebase, saves to Hostinger /public_html/crm/backups/,
sends confirmation email to hr@aldancare.com
"""

import json
import os
import ftplib
import smtplib
import urllib.request
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ── Config from GitHub Secrets ──
FIREBASE_URL = os.environ["FIREBASE_URL"]  # https://fintech-nd-default-rtdb.asia-southeast1.firebasedatabase.app
FTP_HOST     = os.environ["FTP_HOST"]      # 77.37.37.73
FTP_USER     = os.environ["FTP_USER"]      # u362545885.aldancare.com
FTP_PASS     = os.environ["FTP_PASS"]
SMTP_USER    = os.environ["SMTP_USER"]     # hr@aldancare.com
SMTP_PASS    = os.environ["SMTP_PASS"]

NOTIFY_EMAIL = "hr@aldancare.com"
BACKUP_PATH  = "/public_html/crm/backups"

# ── IST timezone ──
IST = timezone(timedelta(hours=5, minutes=30))
now_ist = datetime.now(IST)

# ── Only run on 1st of month (cron fires on 28-31, check actual date) ──
if now_ist.day != 1:
    print(f"Today is {now_ist.strftime('%d %b %Y')} — not 1st of month. Skipping.")
    exit(0)

print(f"Starting CRM backup for {now_ist.strftime('%B %Y')}...")

# ── Step 1: Read Firebase data ──
def firebase_get(path):
    url = f"{FIREBASE_URL}/{path}.json"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

print("Reading Firebase data...")
proposals = firebase_get("crm26/v1/proposals") or {}

# Convert Firebase object to list
def to_list(v):
    if not v: return []
    if isinstance(v, list): return [x for x in v if x]
    if isinstance(v, dict): return [x for x in v.values() if x]
    return []

proposal_list = to_list(proposals)

# ── Step 2: Build backup payload ──
backup = {
    "meta": {
        "app": "CRM 26 – Aldan Healthcare Bihar",
        "backup_date": now_ist.strftime("%Y-%m-%d"),
        "backup_time": now_ist.strftime("%H:%M IST"),
        "period": now_ist.strftime("%B %Y"),
        "firebase_path": "crm26/v1/proposals",
        "total_proposals": len(proposal_list),
    },
    "proposals": proposal_list,
}

# ── Step 3: Stats for email ──
statuses = {"Proposed": 0, "Approved": 0, "Confirmed": 0}
total_confirmed_amt = 0
for p in proposal_list:
    s = p.get("status", "")
    if s in statuses:
        statuses[s] += 1
    if s == "Confirmed":
        entries = p.get("issuedEntries") or p.get("entries") or []
        total_confirmed_amt += sum(float(e.get("issued", e.get("proposed", 0))) for e in entries)

# ── Step 4: Serialize ──
filename = f"CRM_Backup_{now_ist.strftime('%Y-%m-%d')}.json"
content  = json.dumps(backup, indent=2, ensure_ascii=False).encode("utf-8")
size_kb  = len(content) // 1024

print(f"Backup size: {size_kb} KB | Proposals: {len(proposal_list)}")

# ── Step 5: Upload to Hostinger via FTP ──
print(f"Uploading to FTP: {BACKUP_PATH}/{filename}")
import io
ftp = ftplib.FTP()
ftp.connect(FTP_HOST, 21, timeout=30)
ftp.login(FTP_USER, FTP_PASS)
ftp.set_pasv(True)

# Create backup dir if needed
try:
    ftp.mkd(BACKUP_PATH)
    print(f"Created directory: {BACKUP_PATH}")
except ftplib.error_perm:
    pass  # Already exists

ftp.cwd(BACKUP_PATH)
ftp.storbinary(f"STOR {filename}", io.BytesIO(content))
ftp.quit()
print("FTP upload successful.")

# ── Step 6: Send email notification ──
print(f"Sending email to {NOTIFY_EMAIL}...")

subject = f"✅ CRM 26 Monthly Backup — {now_ist.strftime('%B %Y')}"

html_body = f"""
<html><body style="font-family:Arial,sans-serif;color:#1f2937;max-width:600px;margin:0 auto;">
  <div style="background:#1e3a5f;padding:24px;border-radius:12px 12px 0 0;">
    <h2 style="color:white;margin:0;">💊 CRM 26 – Monthly Backup</h2>
    <p style="color:rgba(255,255,255,0.6);margin:6px 0 0;">Aldan Healthcare · Bihar Region</p>
  </div>
  <div style="background:#f8fafc;padding:24px;border:1px solid #e2e8f0;border-top:none;border-radius:0 0 12px 12px;">

    <p style="color:#059669;font-weight:bold;font-size:16px;">✅ Backup completed successfully</p>

    <table style="width:100%;border-collapse:collapse;margin:16px 0;">
      <tr style="background:#e0f2fe;">
        <td style="padding:10px 14px;font-weight:bold;color:#0369a1;">Backup Date</td>
        <td style="padding:10px 14px;">{now_ist.strftime('%d %B %Y, %H:%M IST')}</td>
      </tr>
      <tr>
        <td style="padding:10px 14px;font-weight:bold;color:#374151;">File Name</td>
        <td style="padding:10px 14px;font-family:monospace;font-size:13px;">{filename}</td>
      </tr>
      <tr style="background:#f1f5f9;">
        <td style="padding:10px 14px;font-weight:bold;color:#374151;">File Size</td>
        <td style="padding:10px 14px;">{size_kb} KB</td>
      </tr>
      <tr>
        <td style="padding:10px 14px;font-weight:bold;color:#374151;">Folder Path</td>
        <td style="padding:10px 14px;font-family:monospace;font-size:12px;">/public_html/crm/backups/</td>
      </tr>
      <tr style="background:#f1f5f9;">
        <td style="padding:10px 14px;font-weight:bold;color:#374151;">Total Proposals</td>
        <td style="padding:10px 14px;">{len(proposal_list)}</td>
      </tr>
    </table>

    <h3 style="color:#374151;margin-top:20px;">📊 Proposal Status Snapshot</h3>
    <table style="width:100%;border-collapse:collapse;margin:12px 0;">
      <tr>
        <td style="padding:8px 14px;background:#fef3c7;color:#92400e;font-weight:bold;border-radius:6px;">⏳ Proposed</td>
        <td style="padding:8px 14px;font-weight:bold;">{statuses['Proposed']}</td>
      </tr>
      <tr>
        <td style="padding:8px 14px;background:#dbeafe;color:#1e40af;font-weight:bold;border-radius:6px;">✅ Approved</td>
        <td style="padding:8px 14px;font-weight:bold;">{statuses['Approved']}</td>
      </tr>
      <tr>
        <td style="padding:8px 14px;background:#d1fae5;color:#065f46;font-weight:bold;border-radius:6px;">🎯 Confirmed</td>
        <td style="padding:8px 14px;font-weight:bold;">{statuses['Confirmed']} &nbsp;·&nbsp; ₹{total_confirmed_amt:,.0f} issued</td>
      </tr>
    </table>

    <div style="margin-top:20px;padding:14px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;">
      <p style="margin:0;font-size:13px;color:#166534;">
        📁 <strong>To access the backup:</strong> Hostinger hPanel → File Manager →
        <code style="background:#dcfce7;padding:2px 6px;border-radius:4px;">/public_html/crm/backups/</code>
        → Download <code style="background:#dcfce7;padding:2px 6px;border-radius:4px;">{filename}</code>
      </p>
    </div>

    <p style="margin-top:24px;font-size:12px;color:#9ca3af;">
      This is an automated monthly backup of CRM 26 data.<br>
      App: <a href="https://crm.aldancare.com" style="color:#3b82f6;">crm.aldancare.com</a>
    </p>
  </div>
</body></html>
"""

msg = MIMEMultipart("alternative")
msg["Subject"] = subject
msg["From"]    = SMTP_USER
msg["To"]      = NOTIFY_EMAIL
msg.attach(MIMEText(html_body, "html"))

with smtplib.SMTP_SSL("smtp.hostinger.com", 465, timeout=30) as server:
    server.login(SMTP_USER, SMTP_PASS)
    server.sendmail(SMTP_USER, NOTIFY_EMAIL, msg.as_string())

print(f"Email sent to {NOTIFY_EMAIL}")
print(f"✅ Backup complete: {filename} ({size_kb} KB)")
