import streamlit as st
from db import page_header

st.set_page_config(page_title="Hour Disposal", page_icon="⏱️", layout="wide")
page_header("⏱️ Hour Disposal — Removed", "This page has been replaced")

st.info("ℹ️ Hour disposal is no longer needed. Employees and hours are now created automatically when you upload timesheets.")
st.markdown("Use **⏱️ Timesheet Upload** to upload hours per hotel each week.")
st.markdown("Use **💷 Payroll Upload**, **🧾 Self-Emp Upload** or **📑 UTR Upload** to add payments.")
st.markdown("Use **🔍 Employee Search** to see full history.")
