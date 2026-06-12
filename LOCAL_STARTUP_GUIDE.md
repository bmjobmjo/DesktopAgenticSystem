# OASIS Local Startup Guide

Welcome to the OASIS Desktop Agentic System! This guide will help you get the system running locally for development, testing, or daily use.

## Prerequisites

Before starting, ensure you have the following installed on your machine:
- **Python 3.10+** (for the backend API services)
- **Node.js 18+** (for the Web UI and WhatsApp daemon)
- **npm** (comes with Node.js)

## 1. Start the Backend API Service

The backend API handles core agent logic, data management, and integrations.

1. Open a terminal and navigate to the project root directory:
   ```bash
   cd D:\Works\GenericAgent\DesktopAgenticSystem
   ```
2. Activate your virtual environment (if you are using one):
   ```bash
   # On Windows
   .venv\Scripts\activate
   ```
3. Install dependencies (if you haven't already):
   ```bash
   pip install -r requirements.txt
   ```
4. Start the API server:
   ```bash
   python api_start.py
   ```
   *The API will start running (typically on port `8787`). Leave this terminal open.*

## 2. Start the Web UI

The Web UI provides a graphical dashboard to interact with your agents, manage integrations (like WhatsApp), and monitor system status.

1. Open a **new** terminal and navigate to the UI directory:
   ```bash
   cd D:\Works\GenericAgent\DesktopAgenticSystem\apps\ui_web
   ```
2. Install dependencies (first time only):
   ```bash
   npm install
   ```
3. Start the development server:
   ```bash
   npm run dev
   ```
   *The UI will usually start on `http://localhost:5173`. Open this URL in your web browser.*

## 3. Configure the WhatsApp Bridge (Optional)

If you plan to use the WhatsApp integration, it requires a headless daemon process and a linked WhatsApp account. 

### A. Initial Device Linking (Registration)
If you are setting this up for the first time, you must link your WhatsApp account.
1. In the Web UI, navigate to the **Settings** > **WhatsApp** tab.
2. Enter your phone number (with country code, e.g., `919876543210`).
3. Click **Register**. The system will generate a pairing code.
4. Open WhatsApp on your phone, go to **Linked Devices** -> **Link with phone number**, and enter the code.
5. Alternatively, you can do this from the terminal:
   ```bash
   cd apps\whatsapp_bridge\headless
   node register.js --phone <YOUR_NUMBER> --dir <PATH_TO_EXCHANGE_FOLDER>
   ```

### B. Starting the Daemon
Once registered, the daemon must run in the background to handle incoming and outgoing messages.
1. Open the **Settings** > **WhatsApp** tab in the Web UI.
2. Click **Start Daemon**. 
3. The UI will indicate that the daemon is running and actively polling.

---

## Troubleshooting

- **Web UI not connecting (Port 5173 in use):**
  If `npm run dev` fails or acts unresponsively because port `5173` is occupied by a zombie process, you can kill it (on Windows) using:
  ```cmd
  netstat -ano | findstr :5173
  taskkill /F /PID <PROCESS_ID_FROM_ABOVE>
  ```
- **Daemon says "Not Connected":**
  This means the authentication session is missing or invalid. Ensure you have successfully completed the WhatsApp linking/registration step before starting the daemon.
- **Python Missing Modules:**
  Ensure you have activated your virtual environment and run `pip install -r requirements.txt`.
