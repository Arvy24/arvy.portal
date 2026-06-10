import streamlit as st
import pandas as pd
import openpyxl
import re
from datetime import datetime, date
from db import get_client, page_header

st.set_page_config(page_title="Timesheet Upload", page_icon="⏱️", layout="wide")
page_header("⏱️ Timesheet Upload", "Upload weekly rota — employees and hours extracted automatically")

supabase = get_client()

@st.cache_data(ttl=60)
def load_clients():
    return supabase.table("clients").select("id,name").eq("is_active", True).order("name").execute().data or []

if st.sidebar.button("🔄 Refresh"):
    load_clients.clear(); st.rerun()

clients = load_clients()

# ── Parse timesheet in ARVY rota format ──────────────────────
def parse_arvy_timesheet(file_bytes):
    """
    Parses ARVY rota Excel format:
      Row 1 : Title — e.g. "Tavistock Housekeeping  30/03/2026 to 05/04/2026] ROTA"
      Row 2 : Column headers (Employees, Monday … Sunday, Total, RATE, TOTAL)
      Row 3 : Actual dates (None, date, date, date, date, date, date, date, ...)
      Row 4+ : Employee rows — col[0]=name, col[8]=total hours (numeric)
               L/P rows      — col[0]=None or "L/P", contain daily numeric hours
    """
    wb = openpyxl.load_workbook(file_bytes, data_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))

    result = {
        "client_name": None,
        "week_start": None,
        "week_end": None,
        "employees": [],   # list of {name, total_hours}
    }

    # ── Extract title row (row 0) ─────────────────────────────
    title = str(rows[0][0] or "") if rows else ""

    # Try to extract client name (everything before the date pattern)
    date_match = re.search(r'(\d{2}[./]\d{2}[./]\d{4})', title)
    if date_match:
        client_raw = title[:date_match.start()].strip().rstrip(" [")
        result["client_name"] = re.sub(r'\s+', ' ', client_raw).strip()

    # Try to extract date range from title: DD/MM/YYYY to DD/MM/YYYY
    date_range = re.findall(r'(\d{2}[./]\d{2}[./]\d{4})', title)
    if len(date_range) >= 2:
        try:
            result["week_start"] = datetime.strptime(date_range[0], "%d/%m/%Y").date()
            result["week_end"]   = datetime.strptime(date_range[1], "%d/%m/%Y").date()
        except:
            pass

    # ── Fallback: extract dates from row 3 (index 2) ─────────
    if (not result["week_start"] or not result["week_end"]) and len(rows) > 2:
        date_row = rows[2]
        actual_dates = [v for v in date_row if isinstance(v, datetime)]
        if len(actual_dates) >= 2:
            result["week_start"] = actual_dates[0].date()
            result["week_end"]   = actual_dates[-1].date()

    # ── Extract employees (rows 4 onwards) ────────────────────
    SKIP_KEYWORDS = {
        "employees", "agency", "arvy", "total", "l/p", "shift", "rate",
        "grand total", "rota", "housekeeping", "notes", "nan", ""
    }

    for row in rows[3:]:
        name_val  = row[0]
        hours_val = row[8] if len(row) > 8 else None

        # Must have a string name and a numeric total hours
        if not isinstance(name_val, str):
            continue
        name = name_val.strip()
        if not name or name.lower() in SKIP_KEYWORDS:
            continue
        # Skip section headers (very long lines or contain keywords)
        if any(kw in name.lower() for kw in ["agency", "arvy", "team member", "housekeeping", "supervisor"]):
            continue
        if not isinstance(hours_val, (int, float)):
            continue
        if float(hours_val) <= 0:
            continue

        result["employees"].append({
            "name":  name,
            "hours": float(hours_val),
        })

    return result

# ── UI ────────────────────────────────────────────────────────
st.subheader("📂 Upload Timesheet Excel")
st.caption("Upload your ARVY rota Excel — client name, dates and employee hours are extracted automatically.")

uploaded = st.file_uploader("Upload timesheet (.xlsx)", type=["xlsx", "xls"])

if uploaded:
    try:
        parsed = parse_arvy_timesheet(uploaded)

        st.markdown("---")
        st.subheader("✅ Extracted Information")

        # ── Show / allow editing of extracted header info ────
        c1, c2, c3 = st.columns(3)
        with c1:
            # Offer client dropdown — pre-select if matched
            client_list = [c["name"] for c in clients] if clients else []
            detected    = parsed["client_name"] or ""
            # Try to find closest match
            matched_idx = 0
            for i, cn in enumerate(client_list):
                if detected.lower()[:8] in cn.lower() or cn.lower()[:8] in detected.lower():
                    matched_idx = i
                    break
            selected_client = st.selectbox(
                "🏨 Hotel (auto-detected — confirm or change)",
                client_list,
                index=matched_idx
            ) if client_list else st.text_input("🏨 Hotel Name", value=detected)

        with c2:
            week_start = st.date_input(
                "📅 Week Start",
                value=parsed["week_start"] or date.today()
            )
        with c3:
            week_end = st.date_input(
                "📅 Week End",
                value=parsed["week_end"] or date.today()
            )

        st.markdown("---")

        if not parsed["employees"]:
            st.error("❌ No employees found in this file. Check the format matches the ARVY rota layout.")
        else:
            st.subheader(f"👥 {len(parsed['employees'])} Employees Extracted")

            df_preview = pd.DataFrame(parsed["employees"])
            df_preview.columns = ["Employee Name", "Total Hours"]
            df_preview["Hotel"]      = selected_client
            df_preview["Week Start"] = str(week_start)
            df_preview["Week End"]   = str(week_end)

            # Editable — allow corrections before saving
            edited = st.data_editor(
                df_preview[["Employee Name","Total Hours","Hotel","Week Start","Week End"]],
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic"
            )

            c1, c2, c3 = st.columns(3)
            c1.metric("Employees", len(edited))
            c2.metric("Total Hours", f"{edited['Total Hours'].sum():.1f}")
            c3.metric("Week", f"{week_start} → {week_end}")

            st.markdown("---")
            if st.button("💾 Save Timesheets to Database", type="primary", use_container_width=True):
                saved = 0; errors = []
                for _, row in edited.iterrows():
                    name = str(row["Employee Name"]).strip()
                    if not name or name.lower() == "nan":
                        continue
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

# ── View recent records ───────────────────────────────────────
st.subheader("📋 Recent Timesheet Records")
try:
    recs = supabase.table("weekly_records").select(
        "week_date,employee_name,client_name,hours_worked"
    ).order("week_date", desc=True).limit(100).execute().data or []

    if recs:
        df_recs = pd.DataFrame(recs)
        df_recs.columns = ["Week Date","Employee","Hotel","Hours"]

        # Filter controls
        hotels = ["All"] + sorted(df_recs["Hotel"].unique().tolist())
        col1, col2 = st.columns(2)
        with col1:
            hotel_f = st.selectbox("Filter by Hotel", hotels)
        with col2:
            weeks   = ["All"] + sorted(df_recs["Week Date"].unique().tolist(), reverse=True)
            week_f  = st.selectbox("Filter by Week", weeks)

        if hotel_f != "All":
            df_recs = df_recs[df_recs["Hotel"] == hotel_f]
        if week_f != "All":
            df_recs = df_recs[df_recs["Week Date"] == week_f]

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
