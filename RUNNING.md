# Running the AI Decision Service

This file provides a concise, step-by-step guide for running the FastAPI AI Decision Service locally.

## Prerequisites

- Python 3.10+ installed
- Git (optional but recommended)
- MongoDB Atlas and Supabase configured for full functionality
- Terminal access in the project root folder

## Step 1: Open the project directory

In your terminal, navigate to the project root:

```bash
cd "/home/hyoukasterben/Desktop/Human in the loop AI"
```

## Step 2: Create and activate a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

If you are on Windows PowerShell, use:

```powershell
venv\Scripts\Activate.ps1
```

If you are on Windows Command Prompt, use:

```cmd
venv\Scripts\activate.bat
```

## Step 3: Install dependencies

```bash
pip install -r requirements.txt
```

## Step 4: Create the environment file

Copy the example environment file to `.env`:

```bash
cp .env.example .env
```

Then open `.env` and replace placeholder values with your real settings:

- `MONGODB_URI`
- `SUPABASE_URL`
- `SUPABASE_KEY`

## Step 5: Start the FastAPI server

Run the app with Uvicorn:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 10000
```

The server should start and listen on port `10000`.

## Step 6: Confirm the service is running

Open your browser or use curl:

```bash
curl http://localhost:10000/api/v1/health
```

Expected response:

```json
{
  "status": "healthy",
  "message": "AI Decision Service is running"
}
```

## Step 7: Call the decision endpoint

Use curl or Postman to send a request:

```bash
curl -X POST http://localhost:10000/api/v1/decision \
  -H "Content-Type: application/json" \
  -d '{"barangay_id": 1}'
```

## Notes

- If you do not configure `MONGODB_URI` or `SUPABASE_URL` / `SUPABASE_KEY`, the service will still start, but decision requests will use safe fallback behavior.
- To view API docs, open:

```bash
http://localhost:10000/docs
```

## Troubleshooting

- If `python3 -m venv venv` fails, install the system package:

```bash
sudo apt update
sudo apt install python3.12-venv
```

- If the server does not start, ensure your `.env` file exists and contains valid values.
- If `curl` returns `Not Found`, use the correct endpoint prefix: `/api/v1/health`.
