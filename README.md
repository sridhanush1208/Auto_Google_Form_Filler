# ⚡ Auto Google Form Filler

An autonomous, scheduled, dual-engine Google Form automation system with an interactive Web Dashboard and cloud-native execution. Submits your Google Form on specific days and times with your email and custom/dynamic field values—**completely autonomously, even when your computer is shut down or closed**.

[![Tests](https://img.shields.io/badge/tests-15%20passed-brightgreen.svg)]()
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)]()
[![Render](https://img.shields.io/badge/deploy-Render%20Free-46E3B7.svg)]()
[![GitHub Actions](https://img.shields.io/badge/runner-GitHub%20Actions-2088FF.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)]()

---

## 🌐 Deploy to Render (Free Cloud Web App for Mobile & Friends)

You can host this entire web app online for **100% free** on **Render.com** so you and your friends can open it directly from mobile browsers:

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/sridhanush1208/Auto_Google_Form_Filler)

### 30-Second Setup on Render:
1. Log in to [render.com](https://render.com) using your GitHub account.
2. Click **New +** → **Web Service**.
3. Connect your repository: `sridhanush1208/Auto_Google_Form_Filler`.
4. Render will automatically read `render.yaml` and configure everything!
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn src.web.app:app --host 0.0.0.0 --port $PORT`
5. Click **Create Web Service**. 
6. Render gives you a public link (e.g. `https://auto-google-form-filler.onrender.com`) that you and your friends can open on any phone!

---

## 🚀 Local Quick Start (Web Dashboard)

### 1. Clone & Set Up Virtual Environment
```bash
# Clone the repository
git clone https://github.com/sridhanush1208/Auto_Google_Form_Filler.git
cd Auto_Google_Form_Filler

# Create and activate virtual environment
python -m venv .venv

# On Windows (PowerShell):
.\.venv\Scripts\Activate.ps1

# On Linux / macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Launch the Web Dashboard
```bash
python run_ui.py
```
Open your browser at **`http://127.0.0.1:8000`**.

---

## 🖥️ Web Dashboard Walkthrough

### 1. 🔍 Form Inspector
1. Paste your Google Form URL (e.g., `https://docs.google.com/forms/d/e/.../viewform`) or a Pre-filled Link.
2. Click **Inspect Form**.
3. View all detected question titles, question types (Short answer, Multiple choice, Dropdown, Checkbox), and their exact internal `entry.<ID>` keys.
4. Click **Use in Configurator** to load them straight into the configuration editor.

### 2. 📝 Field Configurator
1. Set your submission email address.
2. For each question field, enter the answer you want to submit.
3. Use dynamic date helpers to keep submitted dates current:
   - `{{TODAY}}` -> Formats as `YYYY-MM-DD` (e.g., `2026-09-08`)
   - `{{NOW}}` -> Formats as `HH:MM:SS` (e.g., `16:30:00`)
   - `{{TIMESTAMP}}` -> Formats as `YYYY-MM-DD HH:MM:SS`
   - `{{TODAY_FORMAT:%d/%m/%Y}}` -> Formats as `08/09/2026`
   - `{{DAY_NAME}}` -> Formats as `Tuesday`
4. Click **Save Configuration** to write to `config/form_config.yaml`.

### 3. ⏰ Visual Schedule Planner
1. Select your local timezone (e.g. `Asia/Kolkata` / IST).
2. Set your desired submission time (e.g. `09:30 AM`).
3. Toggle the days of the week you want the form to be filled.
4. Click **Save & Sync Schedule** to update `.github/workflows/scheduled_submission.yml`.

### 4. 🧪 Test & Submit Console
- Click **Simulate (Dry-Run)**: Tests configuration without sending any network requests. Verifies dynamic date interpolation and prints the exact payload.
- Click **Live Submit Now**: Sends an actual submission to Google Forms and displays the HTTP status code and confirmation message.

---

## ☁️ Running Autonomously on GitHub Actions (Laptop Closed)

Because GitHub Actions runs on GitHub's cloud servers, your form will be submitted on schedule even if your laptop is closed, sleeping, or disconnected:

1. Push your repository to GitHub:
   ```bash
   git add .
   git commit -m "Configure auto form filler"
   git push origin main
   ```
2. Navigate to your repository on GitHub:
   `https://github.com/sridhanush1208/Auto_Google_Form_Filler`
3. Click the **Actions** tab.
4. You will see the **Autonomous Google Form Submission** workflow active.
5. You can trigger a manual test anytime by clicking **Run workflow**!

### Adding Email Alert Secrets (Optional)
To receive email alerts when GitHub Actions runs:
1. Go to your GitHub repository -> **Settings** -> **Secrets and variables** -> **Actions**.
2. Add the following repository secrets:
   - `SMTP_HOST`: `smtp.gmail.com`
   - `SMTP_PORT`: `587`
   - `SMTP_USER`: `your_email@gmail.com`
   - `SMTP_PASSWORD`: *Your 16-character Google App Password* ([Generate here](https://myaccount.google.com/apppasswords))
   - `ALERT_RECIPIENT_EMAIL`: `your_notification_email@gmail.com`

---

## 💻 Command Line Interface (CLI) Usage

### Run Form Submission via CLI:
```bash
# Dry run
python src/main.py --dry-run

# Live submission
python src/main.py

# Custom config file or timezone
python src/main.py --config config/form_config.yaml --tz Asia/Kolkata
```

### Inspect a Form from Terminal:
```bash
python -m src.inspector https://docs.google.com/forms/d/e/.../viewform
```

### Convert Local Time to Cron:
```bash
python src/scheduler.py
```

---

## 🧪 Running Tests

Run the full automated test suite:
```bash
pytest tests/ -v
```

---

## 📂 Project Structure

```
Auto_Google_Form_Filler/
├── .github/
│   └── workflows/
│       └── scheduled_submission.yml    # Autonomous cloud cron runner
├── config/
│   ├── form_config.example.yaml        # Example template config
│   └── form_config.yaml                # Your active configuration
├── src/
│   ├── __init__.py
│   ├── inspector.py                    # Form Inspector: discovers entry IDs from URL
│   ├── scheduler.py                    # Timezone converter & workflow generator
│   ├── filler/
│   │   ├── __init__.py
│   │   ├── base.py                     # Abstract Form Filler base class
│   │   ├── http_filler.py              # Direct HTTP POST engine
│   │   └── browser_filler.py           # Playwright headless browser engine
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── date_resolver.py            # Dynamic date template resolver
│   │   └── notifier.py                 # Email alert dispatcher
│   ├── web/
│   │   ├── __init__.py
│   │   ├── app.py                      # FastAPI web backend
│   │   └── templates/
│   │       └── index.html              # Sleek single-page dashboard UI
│   └── main.py                         # Unified CLI runner for GitHub Actions
├── tests/
│   ├── test_date_resolver.py           # 3 unit tests
│   ├── test_filler.py                  # 2 unit tests
│   ├── test_inspector.py               # 3 unit tests
│   ├── test_scheduler.py               # 3 unit tests
│   └── test_web_api.py                 # 3 integration tests
├── run_ui.py                           # Single-command launcher for Web Dashboard
├── requirements.txt                    # Core dependencies
├── requirements-browser.txt            # Optional Playwright dependencies
├── .env.example                        # Template for secrets
├── .gitignore                          # Ignored caches, venvs, and sensitive files
├── pytest.ini                          # Test configuration
└── README.md                           # Documentation
```

---

## 📄 License
MIT License. Feel free to customize and use for your automation needs!
