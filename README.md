# KisanOne 🌾

> **One Platform. One Process. One Farmer.**
> Smart Agricultural Procurement Orchestration — SIH26032

## 📁 Project Structure

`
KisanOne/
├── frontend/   # TanStack Start (React + TypeScript + Vite) — runs on :8080
└── backend/    # FastAPI (Python) + MongoDB Atlas — runs on :8000
`

## 🚀 Quick Start

### Backend
`ash
cd backend
pip install -r requirements.txt
# Create .env from backend/.env.example
uvicorn main:app --reload --host 0.0.0.0 --port 8000
`

### Frontend
`ash
cd frontend
npm install
npm run dev
`

## ⚙️ Environment Variables
Copy `backend/.env.example` to `backend/.env` and fill in your MongoDB URI.

## 👥 Team SIH-83 CodeOps
