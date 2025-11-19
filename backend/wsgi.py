"""WSGI entry-point for running the Flask app."""
import os
from dotenv import load_dotenv

# Load environment variables BEFORE creating the app
# This is critical for Railway/gunicorn deployments
load_dotenv()

# Log Supabase configuration status (without exposing credentials)
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
if supabase_url and supabase_key:
    print(f"✓ Supabase configuration detected (URL: {supabase_url[:30]}...)")
else:
    missing = []
    if not supabase_url:
        missing.append("SUPABASE_URL")
    if not supabase_key:
        missing.append("SUPABASE_KEY")
    print(f"⚠ Warning: Missing Supabase environment variables: {', '.join(missing)}")

from backend.app import create_app

app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
