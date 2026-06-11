import streamlit as st
import pandas as pd
import openpyxl
import re
from datetime import datetime, date, timedelta
from db import get_client, page_header

st.set_page_config(page_title="Timesheet Upload", page_icon="⏱️", layout="wide")
page_header("⏱️ Timesheet Upload", "Select hotel & week dates first, then upload the rota Excel")

supabase = get_client()

@st.cache_data(ttl=60)
def load_clients():
    return supabase.table("clients").select("id,name").eq("is_active", True).order("name").execute().data or []

if st.sidebar.button("🔄 Refresh"):
    load_clients.clear(); st.rerun()

clients     = load_clients()
client_list = [c["name"] for c in clients] if clients else []

# ═══════════════════════════════════════════════════════════════
# STEP 1 — Hotel & Week (always visible at top)
# ═══════════════════════════════════════════════════════════════
st.subheader("1️⃣  Select Hotel & Week Dates")
st.caption("Set these before uploading. The file's extracted dates/hotel are used as hints only.")

default_monday = date.today() - timedelta(days=date.today().weekday())
default_sunday = default_monday + timedelta(days=6)

hcol, s_col, e_col = st.columns([2, 1, 1])
with hcol:
    if client_list:
        selected_client = st.selectbox("🏨 Hotel / Client", client_list)
    else:
        selected_client = st.text_input("🏨 Hotel / Client name")

with s_col:
    week_start = st.date_input("📅 Week Start (Monday)", value=default_monday)

with e_col:
    week_end = st.date_input("📅 Week End (Sunday)", value=default_sunday)

# Warn if dates look wrong
if week_end < week_start:
    st.error("⚠️ Week End must be after Week Start.")
elif (week_end - week_start).days > 13:
    st.warning("⚠️ Date range is more than 2 weeks — double-check dates.")

st.info(
    f"📌 Saving as: **{selected_client}** | "
    f"**{week_start.strftime('%d %b %Y')}** → **{week_end.strftime('%d %b %Y')}**  "
    f"  *(week key = {week_start})*"
)

st.markdown("---")

# ═══════════════════════════════════════════════════════════════
# STEP 2 — Upload & parse
# ═══════════════════════════════════════════════════════════════
st.subheader("2️⃣  Upload Timesheet Excel")
st.caption("ARVY rota format — employee names and total hours are extracted automatically.")

uploaded = st.file_uploader("Upload timesheet (.xlsx / .xls)", type=["xlsx", "xls"])

def parse_arvy_timesheet(file_bytes):
    wb   = openpyxl.load_workbook(file_bytes, data_only=True)
    ws   = wb.active
    rows = list(ws.iter_rows(values_only=True))

    detected_client = None
    detected_start  = None
    detected_end    = None

    # Title row — extract client name and dates as hints
    title = str(rows[0][0] or "") if rows else ""
    dm = re.search(r'(\d{2}[./]\d{2}[./]\d{4})', title)
    if dm:
        raw = title[:dm.start()].strip().rstrip(" [")
        detected_client = re.sub(r'\s+', ' ', raw).strip()
    dates_found = re.findall(r'(\d{2}[./]\d{2}[./]\d{4})', title)
    if len(dates_found) >= 2:
        try:
            detected_start = datetime.strptime(dates_found[0], "%d/%m/%Y").date()
            detected_end   = datetime.strptime(dates_found[1], "%d/%m/%Y").date()
        except: pass

    # Fallback — row 3 actual dates
    if (not detected_start or not detected_end) and len(rows) > 2:
        actual_dates = [v for v in rows[2] if isinstance(v, datetime)]
        if len(actual_dates) >= 2:
            detected_start = actual_dates[0].date()
            detected_end   = actual_dates[-1].date()

    SKIP = {
        "employees","agency","arvy","total","l/p","shift","rate",
        "grand total","rota","housekeeping","notes","nan",""
    }
    employees = []
    for row in rows[3:]:
        name_val  = row[0]
        hours_val = row[8] if len(row) > 8 else None
        if not isinstance(name_val, str): continue
        name = name_val.strip()
        if not name or name.lower() in SKIP: continue
        if any(kw in name.lower() for kw in ["agency","arvy","team member","housekeeping","supervisor"]): continue
        if not isinstance(hours_val, (int, float)): continue
        if float(hours_val) <= 0: continue
        employees.append({"name": name, "hours": float(hours_val)})

    return {"detected_client": detected_client, "detected_start": detected_start,
            "detected_end": detected_end, "employees": employees}

if uploaded:
    try:
        parsed = parse_arvy_timesheet(uploaded)

        # Show what the file detected (info only — user's selections above are used for saving)
        hints = []
        if parsed["detected_client"]: hints.append(f"Hotel detected: *{parsed['detected_client']}*")
        if parsed["detected_start"]:  hints.append(f"Dates detected: *{parsed['detected_start'].strftime('%d %b')} → {parsed['detected_end'].strftime('%d %b %Y')}*")
        if hints:
            st.caption("📄 From file — " + " | ".join(hints) + " (using your selections above)")

        st.markdown("---")

        if not parsed["employees"]:
            st.error("❌ No employees found. Check the format matches the ARVY rota layout.")
        else:
            st.subheader(f"3️⃣  Review & Save — {len(parsed['employees'])} Employees Extracted")

            df_preview = pd.DataFrame(parsed["employees"])
            df_preview.columns = ["Employee Name", "Total Hours"]
            df_preview.insert(0, "Hotel", selected_client)
            df_preview["Week Start"] = str(week_start)
            df_preview["Week End"]   = str(week_end)

            edited = st.data_editor(
                df_preview[["Employee Name","Total Hours","Hotel","Week Start","Week End"]],
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic",
                column_config={
                    "Total Hours": st.column_config.NumberColumn(format="%.1f"),
                }
            )

            c1, c2, c3 = st.columns(3)
            c1.metric("Employees", len(edited))
            c2.metric("Total Hours", f"{edited['Total Hours'].sum():.1f}")
            c3.metric("Week", f"{week_start.strftime('%d %b')} → {week_end.strftime('%d %b %Y')}")

            st.markdown("---")
            if st.button("💾 Save Timesheets to Database", type="primary", use_container_width=True):
                saved = 0; errors = []
                for _, row in edited.iterrows():
                    name = str(row["Employee Name"]).strip()
                    if not name or name.lower() == "nan": continue
                    try:
                        supabase.table("weekly_records").upsert({
                            "week_date":     str(week_start),
                            "employee_name": name,
                            "client_name":   str(row["Hotel"]),
                            "hours_worked":  float(row["Total Hours"] or 0),
                        }, on_conflict="week_date,employee_name,client_name").execute()
                        saved += 1
                    except Exception as e:
                        errors.append(f"{name}: {e}")

                if errors:
                    st.error(f"⚠️ Saved {saved}, {len(errors)} error(s):\n" + "\n".join(errors))
                else:
                    st.success(f"✅ {saved} employees saved — **{selected_client}** | **{week_start} → {week_end}**")
                    st.balloons()

    except Exception as e:
        st.error(f"❌ Could not parse file: {e}")
        st.info("Make sure it's an ARVY rota Excel with the standard format.")

st.markdown("---")

# ═══════════════════════════════════════════════════════════════
# Recent records viewer
# ═══════════════════════════════════════════════════════════════
st.subheader("📋 Recent Timesheet Records")
try:
    recs = supabase.table("weekly_records").select(
        "week_date,employee_name,client_name,hours_worked"
    ).order("week_date", desc=True).limit(200).execute().data or []

    if recs:
        df_recs = pd.DataFrame(recs)
        df_recs.columns = ["Week Date","Employee","Hotel","Hours"]
        df_recs["Week Date"] = pd.to_datetime(df_recs["Week Date"]).dt.strftime("%d %b %Y")

        col1, col2 = st.columns(2)
        with col1:
            hotels = ["All"] + sorted(df_recs["Hotel"].unique().tolist())
            hotel_f = st.selectbox("Filter by Hotel", hotels)
        with col2:
            weeks  = ["All"] + sorted(df_recs["Week Date"].unique().tolist(), reverse=True)
            week_f = st.selectbox("Filter by Week", weeks)

        if hotel_f != "All": df_recs = df_recs[df_recs["Hotel"] == hotel_f]
        if week_f  != "All": df_recs = df_recs[df_recs["Week Date"] == week_f]

        st.dataframe(df_recs, use_container_width=True, hide_index=True)
        c1, c2 = st.columns(2)
        c1.metric("Employees", len(df_recs))
        c2.metric("Total Hours", f"{df_recs['Hours'].sum():.1f}")
    else:
        st.info("No records yet. Upload a timesheet above.")
except Exception as e:
    st.warning(f"Could not load records: {e}")

st.markdown("---")
st.caption("⏱️ Timesheet Upload  •  ARVY Portal v1.0")
