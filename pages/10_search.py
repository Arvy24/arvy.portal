import streamlit as st
import pandas as pd
from datetime import date, timedelta
from db import get_client, page_header

st.set_page_config(page_title="Employee Search", page_icon="🔍", layout="wide")
page_header("🔍 Employee Search", "Search any employee — full history of hours and payments")

supabase = get_client()

if st.sidebar.button("🔄 Refresh"):
    st.cache_data.clear(); st.rerun()

@st.cache_data(ttl=60)
def load_employee_names():
    recs = supabase.table("weekly_records").select("employee_name").execute().data or []
    return sorted(set(r["employee_name"].strip() for r in recs if r.get("employee_name")))

@st.cache_data(ttl=60)
def load_client_names():
    recs = supabase.table("weekly_records").select("client_name").execute().data or []
    return sorted(set(r["client_name"].strip() for r in recs if r.get("client_name")))

all_names   = load_employee_names()
all_clients = load_client_names()

st.subheader("🔎 Search Employee")
search = st.text_input("Type employee name", placeholder="e.g. John Smith")

matched_names = [n for n in all_names if search.lower() in n.lower()] if search else all_names

if not matched_names:
    st.info("No employees found. Upload timesheets first to build the employee database.")
    st.stop()

selected_name = st.selectbox(f"Select employee ({len(matched_names)} found)", matched_names)

st.markdown("---")

st.subheader("🔽 Filters")
col1, col2, col3 = st.columns(3)

with col1:
    filter_type = st.selectbox("Quick Filter", [
        "All Time", "This Week", "Last Week", "This Month", "Last Month", "This Year", "Custom Range"
    ])
with col2:
    client_filter = st.selectbox("🏨 Hotel", ["All Hotels"] + all_clients)
with col3:
    date_from, date_to = None, None
    if filter_type == "Custom Range":
        date_from = st.date_input("From", value=date.today() - timedelta(days=30))
        date_to   = st.date_input("To",   value=date.today())

today = date.today()
if filter_type == "This Week":
    date_from = today - timedelta(days=today.weekday())
    date_to   = today
elif filter_type == "Last Week":
    date_from = today - timedelta(days=today.weekday() + 7)
    date_to   = today - timedelta(days=today.weekday() + 1)
elif filter_type == "This Month":
    date_from = today.replace(day=1)
    date_to   = today
elif filter_type == "Last Month":
    first_this = today.replace(day=1)
    date_to    = first_this - timedelta(days=1)
    date_from  = date_to.replace(day=1)
elif filter_type == "This Year":
    date_from = today.replace(month=1, day=1)
    date_to   = today

@st.cache_data(ttl=30)
def load_employee_history(name, df, dt, client):
    q = supabase.table("weekly_records").select("*").eq("employee_name", name)
    if df:
        q = q.gte("week_date", str(df))
    if dt:
        q = q.lte("week_date", str(dt))
    if client:
        q = q.eq("client_name", client)
    return q.order("week_date", desc=True).execute().data or []

history = load_employee_history(
    selected_name,
    date_from,
    date_to,
    client_filter if client_filter != "All Hotels" else None
)

st.markdown("---")

if not history:
    st.info(f"No records found for **{selected_name}** with the selected filters.")
    st.stop()

df_hist = pd.DataFrame(history)
df_hist["hours_worked"]    = pd.to_numeric(df_hist["hours_worked"],    errors="coerce").fillna(0)
df_hist["payroll_amount"]  = pd.to_numeric(df_hist["payroll_amount"],  errors="coerce").fillna(0)
df_hist["self_emp_amount"] = pd.to_numeric(df_hist["self_emp_amount"], errors="coerce").fillna(0)
df_hist["utr_amount"]      = pd.to_numeric(df_hist["utr_amount"],      errors="coerce").fillna(0)
df_hist["total_paid"]      = df_hist["payroll_amount"] + df_hist["self_emp_amount"] + df_hist["utr_amount"]

total_hours   = df_hist["hours_worked"].sum()
total_payroll = df_hist["payroll_amount"].sum()
total_self    = df_hist["self_emp_amount"].sum()
total_utr     = df_hist["utr_amount"].sum()
total_paid    = df_hist["total_paid"].sum()

st.subheader(f"👤 {selected_name} — {len(df_hist)} record(s)")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Hours",  f"{total_hours:.1f}")
c2.metric("Payroll",      f"£{total_payroll:,.2f}")
c3.metric("Self-Emp",     f"£{total_self:,.2f}")
c4.metric("UTR",          f"£{total_utr:,.2f}")
c5.metric("Total Paid",   f"£{total_paid:,.2f}")

st.markdown("---")

df_show = df_hist[["week_date","client_name","hours_worked","payroll_amount","self_emp_amount","utr_amount","total_paid","notes"]].copy()
df_show["week_date"] = pd.to_datetime(df_show["week_date"]).dt.strftime("%d %b %Y")
df_show.columns = ["Week Date","Hotel","Hours","Payroll £","Self-Emp £","UTR £","Total Paid £","Notes"]

totals_row = pd.DataFrame([{
    "Week Date": "── TOTAL ──", "Hotel": "", "Hours": round(total_hours, 2),
    "Payroll £": round(total_payroll, 2), "Self-Emp £": round(total_self, 2),
    "UTR £": round(total_utr, 2), "Total Paid £": round(total_paid, 2), "Notes": ""
}])

df_display = pd.concat([df_show, totals_row], ignore_index=True)
st.dataframe(df_display, use_container_width=True, hide_index=True)

csv = df_show.to_csv(index=False).encode()
st.download_button(
    f"⬇ Download {selected_name} History as CSV",
    csv,
    f"ARVY_{selected_name.replace(' ','_')}_history.csv",
    "text/csv"
)

st.markdown("---")
st.caption("🔍 Employee Search  •  ARVY Portal v1.0")
