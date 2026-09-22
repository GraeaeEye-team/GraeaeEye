"""
Launcher for Smart Credit System Parser Web Wizard.
Run:
    python run_server.py
Then open http://127.0.0.1:8000 in your browser.
"""

import sys
import uvicorn

if __name__ == "__main__":
    if sys.stdout.encoding != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    print("=" * 70)
    print("[SMART CREDIT SYSTEM] Web Wizard Ingestion Engine")
    print("=" * 70)
    print("URL: http://127.0.0.1:8000")
    print("API Docs: http://127.0.0.1:8000/docs")
    print("=" * 70)
    uvicorn.run("smart_credit_parser.web.app:app", host="127.0.0.1", port=8000, reload=False)
