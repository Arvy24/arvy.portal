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
# Recent records viewer + Edit / Delete
# ═══════════════════════════════════════════════════════════════
st.subheader("📋 Timesheet Records — View, Edit & Delete")

@st.cache_data(ttl=15)
def load_all_records():
    return supabase.table("weekly_records").select(
        "id,week_date,employee_name,client_name,hours_worked,payroll_amount,utr_amount,self_emp_amount"
    ).order("week_date", desc=True).limit(500).execute().data or []

all_recs = load_all_records()

if not all_recs:
    st.info("No records yet. Upload a timesheet above.")
else:
    df_all = pd.DataFrame(all_recs)
    df_all["week_date"]    = pd.to_datetime(df_all["week_date"])
    df_all["hours_worked"] = pd.to_numeric(df_all["hours_worked"], errors="coerce").fillna(0)

    # ── Filters ───────────────────────────────────────────────
    col1, col2 = st.columns(2)
    with col1:
        hotels_list = ["All"] + sorted(df_all["client_name"].dropna().unique().tolist())
        hotel_f = st.selectbox("Filter by Hotel", hotels_list, key="rec_hotel")
    with col2:
        week_opts = ["All"] + sorted(
            df_all["week_date"].dt.strftime("%d %b %Y").unique().tolist(), reverse=True
        )
        week_f = st.selectbox("Filter by Week", week_opts, key="rec_week")

    df_view = df_all.copy()
    if hotel_f != "All":
        df_view = df_view[df_view["client_name"] == hotel_f]
    if week_f != "All":
        df_view = df_view[df_view["week_date"].dt.strftime("%d %b %Y") == week_f]

    # Display table
    df_show = df_view[["week_date","employee_name","client_name","hours_worked",
                        "payroll_amount","utr_amount","self_emp_amount"]].copy()
    df_show["week_date"] = df_show["week_date"].dt.strftime("%d %b %Y")
    df_show.columns = ["Week","Employee","Hotel","Hours","Payroll £","UTR £","Self-Emp £"]
    st.dataframe(df_show, use_container_width=True, hide_index=True)

    c1, c2 = st.columns(2)
    c1.metric("Employees shown", len(df_view))
    c2.metric("Total Hours",     f"{df_view['hours_worked'].sum():.1f}")

    st.markdown("---")

    # ── Edit / Delete panel ───────────────────────────────────
    st.subheader("✏️ Edit or Delete a Record")
    st.caption("Select the employee record you want to correct or remove.")

    if df_view.empty:
        st.info("No records match the current filter.")
    else:
        # Build label list for selectbox
        def row_label(r):
            return (
                f"{r['week_date'].strftime('%d %b %Y')}  |  "
                f"{r['employee_name']}  |  "
                f"{r['client_name']}  |  "
                f"{r['hours_worked']:.1f} hrs"
            )

        labels     = [row_label(r) for _, r in df_view.iterrows()]
        ids        = df_view["id"].tolist()
        sel_idx    = st.selectbox("Select record", range(len(labels)),
                                  format_func=lambda i: labels[i],
                                  key="edit_select")

        sel_rec    = df_view.iloc[sel_idx]
        sel_id     = ids[sel_idx]

        st.markdown("##### Selected record")
        ec1, ec2, ec3, ec4 = st.columns([3, 2, 2, 2])
        with ec1:
            new_name  = st.text_input("👤 Employee Name", value=sel_rec["employee_name"], key="edit_name")
        with ec2:
            hotel_opts   = client_list if client_list else [sel_rec["client_name"]]
            hotel_cur    = sel_rec["client_name"] if sel_rec["client_name"] in hotel_opts else hotel_opts[0]
            new_hotel    = st.selectbox("🏨 Hotel", hotel_opts,
                                        index=hotel_opts.index(hotel_cur),
                                        key="edit_hotel")
        with ec3:
            new_hours = st.number_input("⏱️ Hours", value=float(sel_rec["hours_worked"]),
                                         min_value=0.0, step=0.5, format="%.1f", key="edit_hours")
        with ec4:
            new_week  = st.date_input("📅 Week Start",
                                       value=sel_rec["week_date"].date(),
                                       key="edit_week")

        bc1, bc2, bc3 = st.columns([2, 2, 1])

        with bc1:
            if st.button("💾 Save Changes", type="primary", use_container_width=True, key="btn_save"):
                try:
                    supabase.table("weekly_records").update({
                        "employee_name": new_name.strip(),
                        "client_name":   new_hotel,
                        "hours_worked":  new_hours,
                        "week_date":     str(new_week),
                    }).eq("id", sel_id).execute()
                    st.success(f"✅ Record updated — **{new_name}** | {new_hotel} | {new_hours} hrs")
                    load_all_records.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Could not save: {e}")

        with bc2:
            # Two-step delete: show confirm toggle first
            confirm_del = st.checkbox("⚠️ Confirm delete", key="confirm_del")
            if confirm_del:
                if st.button("🗑️ Delete This Record", type="secondary",
                             use_container_width=True, key="btn_del"):
                    try:
                        supabase.table("weekly_records").delete().eq("id", sel_id).execute()
                        st.success(f"✅ Deleted — **{sel_rec['employee_name']}** | {sel_rec['client_name']} | week {sel_rec['week_date'].strftime('%d %b %Y')}")
                        load_all_records.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Could not delete: {e}")

st.markdown("---")
st.caption("⏱️ Timesheet Upload  •  ARVY Portal v1.0")
