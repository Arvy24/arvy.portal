import streamlit as st
import pandas as pd
from db import get_client, page_header
st.set_page_config(page_title="Timesheets", page_icon="📋", layout="wide")
page_header("📋 Timesheet Upload", "Upload weekly Excel timesheets per hotel")

supabase = get_client()

# --- Load reference data ---
@st.cache_data(ttl=60)
def load_clients():
    res = supabase.table("clients").select("id,name,short_name,dept_number").eq("is_active", True).order("name").execute()
    return res.data

@st.cache_data(ttl=60)
def load_weeks():
    res = supabase.table("weeks").select("*").order("week_ending", desc=True).execute()
    return res.data

@st.cache_data(ttl=60)
def load_employees():
    res = supabase.table("employees").select("id,full_name,preferred_name,employee_ref,employment_type").eq("is_active", True).execute()
    return res.data

clients = load_clients()
weeks   = load_weeks()
employees = load_employees()

client_map = {c["name"]: c["id"] for c in clients}

# Build employee lookup by full name and preferred name (case-insensitive)
employee_map = {}
for e in employees:
    employee_map[e["full_name"].strip().lower()] = e
    if e.get("preferred_name"):
        employee_map[e["preferred_name"].strip().lower()] = e

# --- Sidebar: Select week and hotel ---
st.sidebar.header("⚙️ Step 1: Select Week & Hotel")

week_options = [w["week_ending"] for w in weeks]

if not week_options:
    st.warning("No weeks found. Please add a week first.")
    week_options = []

selected_week = st.sidebar.selectbox("Week Ending", week_options) if week_options else None
week_id = next((w["id"] for w in weeks if w["week_ending"] == selected_week), None) if selected_week else None

# Add new week option
with st.sidebar.expander("➕ Add New Week"):
    from datetime import date
    new_week_date  = st.date_input("Week Ending Date", value=date.today())
    new_tax_week   = st.number_input("Tax Week",  min_value=1, max_value=56, value=1)
    new_tax_month  = st.number_input("Tax Month", min_value=1, max_value=12, value=1)
    if st.button("Add Week"):
        try:
            supabase.table("weeks").insert({
                "week_ending": str(new_week_date),
                "tax_week":    new_tax_week,
                "tax_month":   new_tax_month,
                "tax_year":    new_week_date.year
            }).execute()
            st.success(f"✅ Week {new_week_date} added!")
            load_weeks.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")

client_names    = [c["name"] for c in clients]
selected_client = st.sidebar.selectbox("🏨 Hotel / Client", client_names)
client_id = client_map.get(selected_client)
if not client_id:
    st.error("⚠️ No hotels loaded. Click 🔄 Refresh Data in the sidebar.")
    st.stop()

st.sidebar.markdown("---")
st.sidebar.info(f"📅 Week: **{selected_week}**\n\n🏨 Hotel: **{selected_client}**")

# --- Main: Upload Excel ---
st.markdown("---")
st.subheader("📂 Step 2: Upload Timesheet Excel File")
uploaded_file = st.file_uploader("Upload Excel timesheet (.xlsx or .xls)", type=["xlsx", "xls"])

if uploaded_file:
    # Read all sheets
    xl = pd.ExcelFile(uploaded_file)
    sheet_names = xl.sheet_names

    selected_sheet = st.selectbox("Select Sheet (tab)", sheet_names)

    st.markdown("---")
    st.subheader("⚙️ Step 3: Configure Layout")

    col1, col2 = st.columns(2)
    with col1:
        header_row = st.number_input(
            "Header row number (0 = first row)",
            min_value=0, max_value=20, value=0,
            help="Which row contains column names?"
        )
    with col2:
        skip_last = st.number_input(
            "Rows to skip at the bottom (totals etc.)",
            min_value=0, max_value=10, value=1
        )

    # Re-read with correct header
    df = pd.read_excel(uploaded_file, sheet_name=selected_sheet, header=int(header_row))
    df = df.dropna(how="all")
    if skip_last > 0:
        df = df.iloc[:-skip_last]
    df = df.reset_index(drop=True)

    st.write("**Preview of your file:**")
    st.dataframe(df.head(25), use_container_width=True)

    # Column mapping
    st.markdown("---")
    st.subheader("🗂️ Step 4: Map Columns")
    cols = ["— not used —"] + list(df.columns.astype(str))

    col1, col2, col3 = st.columns(3)
    with col1:
        name_col  = st.selectbox("👤 Employee Name column", cols)
    with col2:
        hours_col = st.selectbox("⏱️ Total Hours column", cols)
    with col3:
        rate_col  = st.selectbox("💷 Client Rate (£/hr) column — optional", cols, index=0)

    if name_col != "— not used —" and hours_col != "— not used —":
        st.markdown("---")
        st.subheader("🔍 Step 5: Employee Matching Preview")

        preview_rows = []
        for _, row in df.iterrows():
            name_val  = str(row[name_col]).strip() if pd.notna(row[name_col]) else ""
            hours_val = row[hours_col] if pd.notna(row[hours_col]) else 0
            rate_val  = row[rate_col]  if rate_col != "— not used —" and pd.notna(row.get(rate_col)) else None

            # Skip blank / header-like names
            if not name_val or name_val.lower() in ["nan", "", "name", "employee", "total"]:
                continue
            try:
                hours_val = float(hours_val)
            except Exception:
                continue  # skip rows with non-numeric hours

            # Try to match employee
            emp          = employee_map.get(name_val.lower())
            match_status = "✅ Found" if emp else "❌ Not Found"
            emp_ref      = emp["employee_ref"]    if emp else "—"
            emp_type     = emp["employment_type"] if emp else "—"

            preview_rows.append({
                "Name (from file)": name_val,
                "Hours":            hours_val,
                "Rate (£/hr)":      rate_val,
                "Match":            match_status,
                "Employee Ref":     emp_ref,
                "Type":             emp_type,
                "_emp":             emp
            })

        if preview_rows:
            display_df = pd.DataFrame([{k: v for k, v in r.items() if k != "_emp"} for r in preview_rows])
            st.dataframe(display_df, use_container_width=True)

            matched   = sum(1 for r in preview_rows if "✅" in r["Match"])
            unmatched = sum(1 for r in preview_rows if "❌" in r["Match"])

            c1, c2, c3 = st.columns(3)
            c1.metric("Total Rows",    len(preview_rows))
            c2.metric("✅ Matched",    matched)
            c3.metric("❌ Not Found",  unmatched)

            if unmatched > 0:
                st.warning(
                    f"⚠️ {unmatched} employee(s) not found in the database and will be skipped. "
                    "Please add them in the **Employees** page first, then re-upload."
                )

            # Save button
            st.markdown("---")
            total_hours = sum(float(r["Hours"]) for r in preview_rows if r["Hours"])
            st.info(
                f"📊 Ready to save **{matched}** records  |  "
                f"Total hours: **{total_hours:.1f}**  |  "
                f"Week: **{selected_week}**  |  "
                f"Hotel: **{selected_client}**"
            )

            if matched > 0 and week_id:
                if st.button("💾 Save Timesheets to Database", type="primary"):
                    saved  = 0
                    errors = []

                    for r in preview_rows:
                        if "❌" in r["Match"]:
                            continue
                        emp = r["_emp"]
                        if not emp:
                            continue

                        try:
                            hours = float(r["Hours"]) if r["Hours"] else 0
                            rate  = float(r["Rate (£/hr)"]) if r["Rate (£/hr)"] not in [None, ""] else None

                            supabase.table("timesheets").upsert({
                                "employee_id":   emp["id"],
                                "client_id":     client_id,
                                "week_id":       week_id,
                                "hours_received": hours,
                                "hourly_rate":   rate,
                                "source_file":   uploaded_file.name
                            }, on_conflict="employee_id,client_id,week_id").execute()
                            saved += 1

                        except Exception as e:
                            errors.append(f"{r['Name (from file)']}: {str(e)}")

                    # Log the upload
                    supabase.table("upload_log").insert({
                        "upload_type":       "timesheet",
                        "filename":          uploaded_file.name,
                        "week_id":           week_id,
                        "records_processed": saved,
                        "records_failed":    len(errors),
                        "status":            "success" if not errors else "partial",
                        "error_log":         {"errors": errors} if errors else None
                    }).execute()

                    if errors:
                        st.error(
                            f"⚠️ Saved {saved} records with {len(errors)} error(s):\n" +
                            "\n".join(errors)
                        )
                    else:
                        st.success(
                            f"✅ Successfully saved {saved} timesheet records for "
                            f"**{selected_client}** — Week ending **{selected_week}**!"
                        )
                    st.balloons()
        else:
            st.warning("No valid rows found. Check your column mapping and header row setting.")
    else:
        st.info("👆 Please select the Employee Name and Total Hours columns above.")
else:
    st.info("👆 Upload an Excel timesheet file to get started.")

# --- View existing timesheets ---
st.markdown("---")
st.subheader("📊 Existing Timesheets This Week")

if week_id and selected_client:
    try:
        existing = supabase.table("timesheets").select(
            "hours_received, hourly_rate, source_file, employees(full_name, employee_ref, employment_type)"
        ).eq("client_id", client_id).eq("week_id", week_id).execute()

        if existing.data:
            rows = []
            for r in existing.data:
                emp = r.get("employees", {}) or {}
                rows.append({
                    "Employee":      emp.get("full_name", "—"),
                    "Ref":           emp.get("employee_ref", "—"),
                    "Type":          emp.get("employment_type", "—"),
                    "Hours":         r["hours_received"],
                    "Rate (£/hr)":   r["hourly_rate"],
                    "Source File":   r["source_file"]
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
            total = sum(r["Hours"] for r in rows)
            st.success(f"**{len(rows)} employees | {total:.1f} total hours** for {selected_client} — Week {selected_week}")
        else:
            st.info("No timesheets uploaded yet for this hotel and week.")
    except Exception as e:
        st.error(f"Error loading existing timesheets: {e}")
