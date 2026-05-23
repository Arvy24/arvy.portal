ARVY Hospitality Solutions Ltd — Staff & Finance Portal
=======================================================
Phase 2: Employee Management

HOW TO RUN LOCALLY
------------------
1. Install Python 3.11 from python.org
2. Open Terminal / Command Prompt
3. Navigate to this folder
4. Run:
     pip install -r requirements.txt
     streamlit run app.py
5. Portal opens in your browser at http://localhost:8501

HOW TO DEPLOY ONLINE (free)
----------------------------
1. Create free account at github.com
2. Create new repository called "arvy-portal"
3. Upload all files in this folder to that repository
4. Go to share.streamlit.io
5. Connect your GitHub account
6. Select your repository and click Deploy
7. Add your secrets in Streamlit Cloud:
     SUPABASE_URL = "https://xokkmxcavewttcwgdtfh.supabase.co"
     SUPABASE_KEY = "your_key_here"
8. You get a private URL to share with your team

FILES IN THIS FOLDER
--------------------
app.py                      — Main portal entry point
db.py                       — Supabase connection
requirements.txt            — Python packages needed
.streamlit/secrets.toml     — Your Supabase credentials (keep private)
pages/01_dashboard.py       — Home dashboard
pages/02_employees.py       — Employee management (bulk upload, add, remove)
pages/03_clients.py         — Hotel/client management
pages/04–11                 — Coming in future phases
ARVY_Employee_Template.csv  — Template for bulk employee upload

PHASES REMAINING
----------------
Phase 3 — Timesheet upload
Phase 4 — Hour disposal
Phase 5 — Payroll/Self-Emp/UTR payment upload
Phase 6 — Client invoices & income
Phase 7 — Employee search
Phase 8 — Reports & dashboard
