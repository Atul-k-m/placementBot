# 📬 ReminderBot: Multi-Tenant Email Monitor SaaS

A professional, secure, and production-ready SaaS application that monitors your Gmail inbox for specific senders or keywords and sends daily WhatsApp digests via Twilio.

## 🛠️ Features
- **Stateless Architecture**: Web service for UI/API + Standalone Worker for scheduling.
- **Production Scrapers**: Monitoring Devpost and Unstop for career opportunities.
- **AES-256 GCM Security**: All user tokens and phone numbers are encrypted at rest.
- **Aesthetic Dashboard**: Custom Vanilla JS/CSS UI with a guided onboarding wizard.
- **Zero Cold-Starts**: Automatic self-pinging to keep free-tier instances awake.

---

## 💻 Section 1: Local Development Setup

1. **Clone & Install**:
   ```bash
   git clone <your-repo-url>
   cd reminderBot
   python -m venv venv
   source venv/bin/activate  # venv\Scripts\activate on Windows
   pip install -r requirements.txt
   ```

2. **Environment Variables**:
   - Copy `.env.example` to `.env`.
   - Generate keys using `python -c "import secrets; print(secrets.token_hex(32))"` and fill them in `.env`.

3. **Google API Setup**:
   - Place your `credentials.json` from Google Cloud Console in the root.
   - Run `python generate_token.py` and follow the browser prompts.
   - Copy the resulting JSON for use in the dashboard.

4. **Run App**:
   ```bash
   # Terminal 1: Web Server
   python -m uvicorn main:app --reload
   
   # Terminal 2: Background Worker (Required for jobs to run)
   python worker.py
   ```

---

## 🚀 Section 2: Render.com Deployment (Zero Cost)

### Step 1: Push to GitHub
Ensure your code (including `render.yaml` and `Procfile`) is pushed to a private GitHub repository.

### Step 2: Deploy Blueprint
1. Go to **[Render Dashboard](https://dashboard.render.com/)**.
2. Click **New** → **Blueprint**.
3. Connect your GitHub repo.
4. Render will read `render.yaml` and automatically create:
   - **web**: `reminderbot-web`
   - **worker**: `reminderbot-worker`
   - **database**: `reminderbot-db` (Free PostgreSQL)

### Step 3: Link Web & Worker
1. Wait for the **web** service to deploy. Copy its live URL (e.g., `https://reminderbot-web.onrender.com`).
2. Go to the **worker** service settings:
   - Add `WEB_URL` = your copied web URL.
   - **CRITICAL**: Copy the `AES_MASTER_KEY` and `JWT_SECRET_KEY` values from the Web service's Env tab and paste them exactly into the Worker's Env tab. They must be identical for encryption/decryption to work.
   - Add your `GEMINI_API_KEY` (if using AI hero).

### Step 4: Prevent Sleep (Cold-Start Fix)
1. Go to **[UptimeRobot](https://uptimerobot.com/)** and create a free account.
2. Add a **New Monitor**:
   - Type: `HTTP(s)`
   - URL: `https://your-app-name.onrender.com/health`
   - Interval: `14 minutes`
3. This keeps the web instance "warm" for free.

---

## 📌 Section 3: Important Operational Notes

- **Database Persistence**: The **Free PostgreSQL** tier expires after 90 days on Render. Export your data or upgrade to the $7 Starter tier before then to keep your configuration.
- **Twilio Sandbox**: Every user must manually send the "join [keyword]" message to the Twilio number once. This must be repeated every **72 hours** to keep the sandbox session active.
- **Statelessness**: Do not store any files in the local filesystem on Render. All data must be in the PostgreSQL database.
- **Encryption**: If you ever change the `AES_MASTER_KEY`, all existing user credentials in the database will become unreadable and users will need to re-authorise.

---

## ✅ Final License
MIT License. Created with ❤️ for students and job seekers.
