# RUNNING.md
### Link Generation – How to Run Backend & Frontend

## 1. Project Layout

```
Link-Generator/
  backend/        # FastAPI backend
  frontend/       # React + Vite UI
```

## 2. One-Time Setup

### 2.1. Frontend Setup (React + Vite)

```bash
cd /Users/guyeven/Projects/RainfallMap/Link-Generator/frontend
npm install
```

### 2.2. Backend Setup (Python + FastAPI)

```bash
cd /Users/guyeven/Projects/RainfallMap/Link-Generator/backend
python -m venv .venv
source venv/bin/activate
pip install -r requirements.txt
```

## 3. Starting the System (Everyday Workflow)

### 3.1. Start the Backend

```bash
cd backend
source venv/bin/activate
uvicorn app:app --reload --port 8100

uvicorn app:app --reload --port
```

### 3.2. Start the Frontend

```bash
cd frontend
npm run dev -- --port 5174
```

## 4. Stopping the Servers

Press Ctrl + C.

## 5. Quick Cheat Sheet

```bash
# Backend
cd backend
source .venv/bin/activate
uvicorn main:app --reload

# Frontend
cd frontend
npm run dev
```

## 6. Fixing Port Conflicts

### 6.1. Check What Is Using the Port

macOS / Linux:
```bash
lsof -i :8000
lsof -i :5173
```

Windows:
```powershell
netstat -ano | findstr :8000
netstat -ano | findstr :5173
```

### 6.2. Kill the Process

macOS / Linux:
```bash
kill -9 <PID>
```

Windows:
```powershell
taskkill /PID <PID> /F
```

### 6.3. Run on a Different Port

Backend:
```bash
uvicorn main:app --reload --port 8001
```

Frontend:
```bash
npm run dev -- --port 5174
```
