# Disk Audit & Clean

A Windows desktop application that scans drives/folders for large files, identifies safe-to-delete temp/cache items, and optionally runs an AI-powered audit using Google Gemini.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![License](https://img.shields.io/badge/License-MIT-green)

## Features

- **Fast recursive scan** — finds the largest files and folders (>= 1 MB) up to 4 levels deep
- **Safe-delete detection** — automatically identifies temp/cache folders (Windows Temp, browser caches, `node_modules`, `__pycache__`, etc.) and marks them green
- **System protection** — critical OS paths (`Windows`, `Program Files`, `Boot`, etc.) are filtered out and never shown
- **AI Smart Audit** — sends file metadata to Google Gemini for risk assessment and delete/keep/backup recommendations
- **Pagination** — browse all results with configurable page size (10 / 20 / 50 / 100)
- **Risk filter** — filter results by AI risk level (Low / Medium / High)
- **Clean vs Delete** — temp folders are cleaned (contents removed, folder kept) instead of fully deleted
- **Dark themed UI** — built with CustomTkinter

## Setup

### 1. Clone and create virtual environment

```bash
git clone https://github.com/talevi83/DiskAuditAndClean.git
cd DiskAudit-And-Clean
python -m venv venv
```

### 2. Activate and install dependencies

```bash
# Windows
venv\Scripts\activate

pip install -r requirements.txt
```

### 3. Configure Gemini API key (optional, for AI audit)

Copy the example env file and add your key:

```bash
copy .env.example .env
```

Edit `.env` and set your API key:

```
GEMINI_API_KEY=your_api_key_here
```

Get a free API key at [https://aistudio.google.com/api-keys](https://aistudio.google.com/api-keys).

### 4. Run

Double-click `run.bat`, or manually:

```bash
venv\Scripts\activate
python main.py
```

## Usage

1. **Browse** to select a drive or folder
2. **Scan** to find all large items (>= 1 MB)
3. Items marked **[SAFE TO DELETE]** in green are known temp/cache folders
4. Click **Smart Audit (AI)** to get Gemini risk assessments for the current page
5. Use **Risk** filter to show only items of a specific risk level
6. **Clean** removes contents of temp folders (keeps the folder); **Delete** removes entirely

## Project Structure

```
main.py          — UI (CustomTkinter), threading, ResultRow rendering
scanner.py       — DiskScanner: recursive scan, system protection, safe-delete detection
ai_auditor.py    — AIAuditor: Gemini API integration, retry logic, JSON parsing
requirements.txt — Python dependencies
run.bat          — Quick launcher (activates venv + runs app)
.env.example     — Template for API key configuration
```

## Requirements

- Python 3.10+
- Windows (uses Windows-specific system paths for protection/detection)
- Google Gemini API key (optional, for AI audit feature)

## License

MIT
