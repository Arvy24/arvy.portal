# ── Dashboard home page ──────────────────────────────────────
import streamlit as st
from db import get_client

st.title("🏨 ARVY Hospitality — Portal Dashboard")
st.markdown("---")

db = get_client()

col1, col2, col3, col4 = st.columns(4)

try:
    emp_count    = len(db.table("employees").select("id").eq("is_active", True).execute().data)
    client_count = len(db.table("clients").select("id").eq("is_active", True).execute().data)
    week_count   = len(db.table("weeks").select("id").execute().data)
    upload_count = len(db.table("upload_log").select("id").execute().data)
except Exception as e:
    emp_count = client_count = week_count = upload_count = 0

col1.metric("Active Employees", emp_count)
col2.metric("Hotel Clients",    client_count)
col3.metric("Weeks on Record",  week_count)
col4.metric("Total Uploads",    upload_count)

st.markdown("---")
st.markdown("### Quick Links")
st.info("👥 Start by uploading your **Employee List** — go to **Employees** in the sidebar.")
st.info("🏨 Your **15 Hotels** are already loaded and ready.")
st.info("📋 After employees are loaded, move to **Timesheets** to upload weekly hours.")
