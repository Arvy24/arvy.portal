import streamlit as st
import pandas as pd
from datetime import date, timedelta
from db import get_client, page_header

st.set_page_config(page_title="Timesheet Upload", page_icon="⏱️", layout="wide")
page_header("⏱️ Timesheet Upload", "Upload weekly timesheets per hotel — employees created automatically")

supabase = get_client()

@st.cache_data(ttl=60)
def load_clients():
    return supabase.table("clients").select("id,name").eq("is_active", True).order("name").execute().data or []

if st.sidebar.button("🔄 Refresh"):
    load_clients.clear(); st.rerun()

clients = load_clients()
if not clients:
    st.error("⚠️ No hotels found. Add hotels in the Clients page first.")
    st.stop()

# ── Sidebar ───────────────────────────────────────────────────
st.sidebar.header("⚙️ Week & Hotel")
week_date = st.sidebar.date_input(
    "📅 Week Date (Monday)",
    value=date.today() - timedelta(days=date.today().weekday()),
)
client_names    = [c["name"] for c in clients]
selected_client = st.sidebar.selectbox("🏨 Hotel", client_names)
st.sidebar.markdown("---")
st.sidebar.info(f"📅 Week: **{week_date}**\n\n🏨 Hotel: **{selected_client}**")

st.markdown("---")
st.subheader("📂 Upload Timesheet Excel")
st.caption("Excel must have at least two columns: **Employee Name** and **Hours**")

uploaded = st.file_uploader("Upload Excel timesheet", type=["xlsx", "xls", "csv"])

df = None
if uploaded:
    try:
        if uploaded.name.endswith(".csv"):
            df = pd.read_csv(uploaded)
        else:
            xl = pd.ExcelFile(uploaded)
            sheet = st.selectbox("Select Sheet", xl.sheet_names) if len(xl.sheet_names) > 1 else xl.sheet_names[0]
            header_row = st.number_input("Header row (0 = first row)", 0, 20, 0)
            df = pd.read_excel(uploaded, sheet_name=sheet, header=int(header_row))

        df = df.dropna(how="all").reset_index(drop=True)
        st.success(f"✅ File loaded — {len(df)} rows")
        st.dataframe(df.head(20), use_container_width=True)
    except Exception as e:
        st.error(f"File error: {e}")

if df is not None:
    st.markdown("---")
    st.subheader("🗂️ Map Columns")
    cols = ["— not used —"] + list(df.columns.astype(str))

    c1, c2, c3 = st.columns(3)
    with c1:
        name_col  = st.selectbox("👤 Employee Name column", cols)
    with c2:
        hours_col = st.selectbox("⏱️ Hours Worked column", cols)
    with c3:
        notes_col = st.selectbox("📝 Notes column (optional)", cols)

    if name_col != "— not used —" and hours_col != "— not used —":
        st.markdown("---")
        st.subheader("🔍 Preview Rows")

        def safe_float(v):
            try:
                return float(str(v).replace(",", "").strip())
            except:
                return 0.0

        skip_words = {"nan", "", "name", "employee", "total", "grand total", "employee name"}
        rows = []
        for _, row in df.iterrows():
            name = str(row[name_col]).strip() if pd.notna(row[name_col]) else ""
            if name.lower() in skip_words:
                continue
            hours = safe_float(row[hours_col]) if pd.notna(row.get(hours_col)) else 0.0
            if not name:
                continue
            notes = str(row[notes_col]).strip() if notes_col != "— not used —" and pd.notna(row.get(notes_col)) else ""
            rows.append({
                "Employee Name": name,
                "Hours": hours,
                "Client": selected_client,
                "Week Date": str(week_date),
                "Notes": notes,
            })

        if rows:
            preview_df = pd.DataFrame(rows)
            edited_df  = st.data_editor(preview_df, use_container_width=True, hide_index=True, num_rows="dynamic")

            c1, c2, c3 = st.columns(3)
            c1.metric("Employees", len(edited_df))
            c2.metric("Total Hours", f"{edited_df['Hours'].sum():.1f}")
            c3.metric("Hotel", selected_client)

            if st.button("💾 Save Timesheets", type="primary", use_container_width=True):
                saved = 0; errors = []
                for _, r in edited_df.iterrows():
                    name = str(r["Employee Name"]).strip()
                    if not name:
                        continue
                    try:
                        supabase.table("weekly_records").upsert({
                            "week_date":    str(week_date),
                            "employee_name": name,
                            "client_name":  selected_client,
                            "hours_worked": float(r["Hours"] or 0),
                            "notes":        str(r.get("Notes", "") or ""),
                        }, on_conflict="week_date,employee_name,client_name").execute()
                        saved += 1
                    except Exception as e:
                        errors.append(f"{name}: {e}")

                if errors:
                    st.error(f"⚠️ Saved {saved}, {len(errors)} error(s):\n" + "\n".join(errors))
                else:
                    st.success(f"✅ {saved} employees saved for **{selected_client}** — Week **{week_date}**")
                    st.balloons()
        else:
            st.warning("No valid rows found. Check column mapping.")

st.markdown("---")

# ── View this week's records ──────────────────────────────────
st.subheader(f"📋 Records for {selected_client} — Week {week_date}")
try:
    recs = supabase.table("weekly_records").select("*")\
        .eq("week_date", str(week_date))\
        .eq("client_name", selected_client)\
        .order("employee_name").execute().data or []
    if recs:
        df_recs = pd.DataFrame(recs)[["employee_name","hours_worked","payroll_amount","self_emp_amount","utr_amount","notes"]]
        df_recs.columns = ["Employee","Hours","Payroll £","Self-Emp £","UTR £","Notes"]
        st.dataframe(df_recs, use_container_width=True, hide_index=True)
        c1,c2 = st.columns(2)
        c1.metric("Employees", len(df_recs))
        c2.metric("Total Hours", f"{df_recs['Hours'].sum():.1f}")
    else:
        st.info("No records yet for this week/hotel. Upload a timesheet above.")
except Exception as e:
    st.warning(f"Could not load records: {e}")

st.markdown("---")
st.caption("⏱️ Timesheets  •  ARVY Portal v1.0")
