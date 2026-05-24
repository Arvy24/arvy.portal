import streamlit as st
from db import get_client, page_header

st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")
page_header("📊 Portal Dashboard", "Live overview — ARVY Hospitality Solutions Ltd")

db = get_client()

try:
    emp_count    = len(db.table("employees").select("id").eq("is_active", True).execute().data)
    client_count = len(db.table("clients").select("id").eq("is_active", True).execute().data)
    week_count   = len(db.table("weeks").select("id").execute().data)
    upload_count = len(db.table("upload_log").select("id").execute().data)
except Exception:
    emp_count = client_count = week_count = upload_count = 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("👥 Active Employees", emp_count)
col2.metric("🏨 Hotel Clients",    client_count)
col3.metric("📅 Weeks on Record",  week_count)
col4.metric("📤 Total Uploads",    upload_count)

st.markdown("---")
st.markdown("### 🚀 Getting Started")

c1, c2 = st.columns(2)
with c1:
    st.info("👥 **Employees** — Upload your staff list via CSV or add individually.")
    st.info("📋 **Timesheets** — Upload weekly Excel timesheets per hotel.")
    st.info("💷 **Payments** — Upload payroll PDF, self-emp & UTR Excel files.")
with c2:
    st.info("⏱️ **Hour Disposal** — Split hours between payroll / self-emp / UTR.")
    st.info("🧾 **Invoices** — Upload client invoices to track income.")
    st.info("📊 **Reports** — View weekly & monthly P&L per hotel.")

st.markdown("---")
st.caption("ARVY Hospitality Solutions Ltd  •  Portal v1.0  •  admin@arvy24.co.uk")
