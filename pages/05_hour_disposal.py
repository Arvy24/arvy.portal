import streamlit as st
import pandas as pd
from db import get_client, page_header

st.set_page_config(page_title="Hour Disposal", page_icon="⏱️", layout="wide")
page_header("⏱️ Hour Disposal", "Split employee hours into Payroll / Self-Emp / UTR")

supabase = get_client()

# --- Load reference data ---
@st.cache_data(ttl=60)
def load_clients():
    res = supabase.table("clients").select("id,name").eq("is_active", True).order("name").execute()
    return res.data or []

@st.cache_data(ttl=60)
def load_weeks():
    res = supabase.table("weeks").select("*").order("week_ending", desc=True).execute()
    return res.data or []

if st.sidebar.button("🔄 Refresh Data"):
    load_clients.clear()
    load_weeks.clear()
    st.rerun()

clients = load_clients()
weeks   = load_weeks()

if not clients:
    st.error("⚠️ No hotels loaded. Check Supabase permissions and click 🔄 Refresh Data.")
    st.stop()

if not weeks:
    st.error("⚠️ No weeks found. Please add a week in the Timesheets page first.")
    st.stop()

# --- Sidebar ---
st.sidebar.header("⚙️ Select Week & Hotel")
week_options    = [w["week_ending"] for w in weeks]
selected_week   = st.sidebar.selectbox("Week Ending", week_options)
week_id         = next(w["id"] for w in weeks if w["week_ending"] == selected_week)

client_names    = [c["name"] for c in clients]
selected_client = st.sidebar.selectbox("🏨 Hotel / Client", client_names)
client_id       = next(c["id"] for c in clients if c["name"] == selected_client)

st.sidebar.markdown("---")
st.sidebar.info(f"📅 Week: **{selected_week}**\n\n🏨 Hotel: **{selected_client}**")

st.markdown("---")

# --- Load timesheets for selected week & hotel ---
try:
    ts_res = supabase.table("timesheets").select(
        "id, hours_received, hourly_rate, employees(id, full_name, employee_ref, employment_type)"
    ).eq("client_id", client_id).eq("week_id", week_id).execute()
    timesheets = ts_res.data or []
except Exception as e:
    st.error(f"Error loading timesheets: {e}")
    st.stop()

if not timesheets:
    st.warning(f"⚠️ No timesheets found for **{selected_client}** — Week **{selected_week}**.\n\nPlease upload timesheets first in the 📋 Timesheets page.")
    st.stop()

# --- Load existing disposals ---
try:
    disp_res = supabase.table("hour_disposals").select("*").eq("client_id", client_id).eq("week_id", week_id).execute()
    existing = {d["employee_id"]: d for d in (disp_res.data or [])}
except Exception:
    existing = {}

# --- Build editable table ---
st.subheader(f"📋 Hour Disposal — {selected_client} | Week ending {selected_week}")
st.caption("Enter how many hours each employee worked on Payroll, Self-Employed, and UTR basis. Total must equal Hours Received.")

rows = []
for ts in timesheets:
    emp          = ts.get("employees", {}) or {}
    emp_id       = emp.get("id", "")
    hrs_received = float(ts.get("hours_received", 0))
    disp         = existing.get(emp_id, {})

    rows.append({
        "Employee":        emp.get("full_name", "—"),
        "Ref":             emp.get("employee_ref", "—"),
        "Type":            emp.get("employment_type", "—"),
        "Hrs Received":    hrs_received,
        "Payroll Hrs":     float(disp.get("payroll_hours",  0)),
        "Self-Emp Hrs":    float(disp.get("self_emp_hours", 0)),
        "UTR Hrs":         float(disp.get("utr_hours",      0)),
        "_emp_id":         emp_id,
        "_ts_id":          ts.get("id", ""),
    })

display_df = pd.DataFrame(rows)

# Editable columns
edit_df = display_df[["Employee", "Ref", "Type", "Hrs Received", "Payroll Hrs", "Self-Emp Hrs", "UTR Hrs"]].copy()

edited = st.data_editor(
    edit_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Employee":     st.column_config.TextColumn("Employee",     disabled=True),
        "Ref":          st.column_config.TextColumn("Ref",          disabled=True, width="small"),
        "Type":         st.column_config.TextColumn("Type",         disabled=True, width="small"),
        "Hrs Received": st.column_config.NumberColumn("Hrs Received", disabled=True, format="%.2f", width="small"),
        "Payroll Hrs":  st.column_config.NumberColumn("Payroll Hrs",  format="%.2f", min_value=0.0, step=0.5),
        "Self-Emp Hrs": st.column_config.NumberColumn("Self-Emp Hrs", format="%.2f", min_value=0.0, step=0.5),
        "UTR Hrs":      st.column_config.NumberColumn("UTR Hrs",      format="%.2f", min_value=0.0, step=0.5),
    },
    num_rows="fixed",
    key="disposal_editor"
)

# --- Validation ---
st.markdown("---")
st.subheader("✅ Validation")

validation_rows = []
all_ok = True
for i, row in edited.iterrows():
    total_disposed = row["Payroll Hrs"] + row["Self-Emp Hrs"] + row["UTR Hrs"]
    hrs_received   = row["Hrs Received"]
    gap            = round(hrs_received - total_disposed, 2)
    status         = "✅ OK" if abs(gap) < 0.01 else f"❌ Gap: {gap:+.2f} hrs"
    if abs(gap) >= 0.01:
        all_ok = False
    validation_rows.append({
        "Employee":      row["Employee"],
        "Hrs Received":  hrs_received,
        "Total Disposed": round(total_disposed, 2),
        "Gap":           gap,
        "Status":        status,
    })

val_df = pd.DataFrame(validation_rows)
st.dataframe(val_df, use_container_width=True, hide_index=True)

# Summary metrics
total_received = sum(r["Hrs Received"]   for r in validation_rows)
total_disposed = sum(r["Total Disposed"] for r in validation_rows)
total_payroll  = float(edited["Payroll Hrs"].sum())
total_selfemp  = float(edited["Self-Emp Hrs"].sum())
total_utr      = float(edited["UTR Hrs"].sum())

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Received",  f"{total_received:.1f} hrs")
c2.metric("Payroll",         f"{total_payroll:.1f} hrs")
c3.metric("Self-Emp",        f"{total_selfemp:.1f} hrs")
c4.metric("UTR",             f"{total_utr:.1f} hrs")
c5.metric("Gap",             f"{total_received - total_disposed:.1f} hrs",
          delta_color="inverse")

if not all_ok:
    st.warning("⚠️ Some employees have a mismatch. Please check the hours add up correctly before saving.")

# --- Save ---
st.markdown("---")
if st.button("💾 Save Hour Disposals", type="primary", disabled=not all_ok):
    saved  = 0
    errors = []

    for i, row in edited.iterrows():
        emp_id = display_df.loc[i, "_emp_id"]
        ts_id  = display_df.loc[i, "_ts_id"]
        try:
            supabase.table("hour_disposals").upsert({
                "timesheet_id":  ts_id,
                "employee_id":   emp_id,
                "client_id":     client_id,
                "week_id":       week_id,
                "hours_received": float(row["Hrs Received"]),
                "payroll_hours":  float(row["Payroll Hrs"]),
                "self_emp_hours": float(row["Self-Emp Hrs"]),
                "utr_hours":      float(row["UTR Hrs"]),
            }, on_conflict="employee_id,client_id,week_id").execute()
            saved += 1
        except Exception as e:
            errors.append(f"{row['Employee']}: {str(e)}")

    # Log
    supabase.table("upload_log").insert({
        "upload_type":       "hour_disposal",
        "week_id":           week_id,
        "records_processed": saved,
        "records_failed":    len(errors),
        "status":            "success" if not errors else "partial",
        "error_log":         {"errors": errors} if errors else None,
        "notes":             f"{selected_client} — Week {selected_week}"
    }).execute()

    if errors:
        st.error(f"⚠️ Saved {saved} with {len(errors)} error(s):\n" + "\n".join(errors))
    else:
        st.success(f"✅ Hour disposals saved for {saved} employees — {selected_client} | Week {selected_week}!")
    st.balloons()

st.caption("💡 Tip: You can edit and re-save at any time. Existing records will be updated.")
