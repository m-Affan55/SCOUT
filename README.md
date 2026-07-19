# Scout: AI Workflow Automation Platform

## What is Scout?
Scout is an intelligent virtual assistant designed to automate tedious online applications. Instead of forcing you to navigate complex websites, read endless requirements, or manually fill out pages of forms, Scout does it for you. 

Simply tell Scout what you want to achieve in plain English (or even Roman Urdu) — for example, *"I want to apply to FAST university"* or *"Renew my driving license"*. 

Scout will then act on your behalf by secretly opening a browser, finding the right forms, extracting data from your documents, and filling everything out.

### The Human-in-the-Loop Advantage
Bots often fail when they hit security checks like CAPTCHAs or OTPs (One Time Passwords) sent to your phone. Scout is different. It is a **human-in-the-loop** system. If Scout reaches an OTP screen, it pauses its work, securely sends an alert to your screen asking for the code, and then takes your input to seamlessly resume the application.

---

## Technical Architecture

Scout is built on a modern, decoupled architecture featuring a reactive frontend and an agentic AI backend.

### Frontend: React + Vite
- **UI:** A production-grade, minimalist dark mode interface designed without heavy frameworks (Vanilla CSS).
- **Real-Time Feed:** Utilizes WebSockets to subscribe to the AI agent's internal state, providing a live timeline of the browser's actions.
- **Interruption UI:** Implements a strict modal trap for when the LangGraph agent pauses execution to request OTP/Human input.

### Backend: FastAPI + Python
- **API Engine:** Serves as the high-performance bridge between the frontend and the AI. Manages the WebSocket broadcasting.
- **Agent Framework (LangGraph):** The core intelligence of Scout. It models the automation as a State Graph with distinct nodes (`Planner`, `Analyzer`, `Automator`). It handles workflow interruptions gracefully by persisting state until human input is received.
- **Browser Automation (Playwright):** Used by the `Automator` node to execute headless or visible browser operations (clicking, typing, reading DOMs).

---

## Local Development Setup

### 1. Backend Setup
1. Navigate to the `backend` directory: `cd backend`
2. Create a virtual environment: `python -m venv venv`
3. Activate the virtual environment:
   - Windows: `.\venv\Scripts\Activate.ps1`
   - Mac/Linux: `source venv/bin/activate`
4. Install dependencies: `pip install -r requirements.txt`
5. Install Playwright browsers: `playwright install chromium`
6. Start the server: `uvicorn app.main:app --host 0.0.0.0 --port 8000`

### 2. Frontend Setup
1. Navigate to the `frontend` directory: `cd frontend`
2. Install Node dependencies: `npm install`
3. Start the Vite development server: `npm run dev`
4. Open `http://localhost:5173` in your browser.