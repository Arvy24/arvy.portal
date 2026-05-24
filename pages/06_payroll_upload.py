import streamlit as st
import pandas as pd
import pdfplumber
import io
from db import get_client, page_header

st.set_page_config(page_title="Payroll Upload", page_icon="💷", layout="wide")
page_header("💷 Payroll Upload", "Upload weekly payroll PDF and map to employee records")

supabase = get_client()

@st.cache_data(ttl=60)
def load_clients():
    return supabase.table("clients").select("id,name").eq("is_active", True).order("name").execute().data or []

@st.cache_data(ttl=60)
def load_weeks():
    return supabase.table("weeks").select("*").order("week_ending", desc=True).execute().data or []

@st.cache_data(ttl=60)
def load_employees():
    return supabase.table("employees").select("id,full_name,preferred_name,employee_ref,employment_type").eq("is_active", True).execute().data or []

if st.sidebar.button("🔄 Refresh Data"):
    load_clients.clear(); load_weeks.clear(); load_employees.clear()
    st.rerun()

clients   = load_clients()
weeks     = load_weeks()
employees = load_employees()

if not clients or not weeks:
    st.error("⚠️ No hotels or weeks loaded. Please check Supabase permissions.")
    st.stop()

# Employee lookup
employee_map = {}
for e in employees:
    employee_map[e["full_name"].strip().lower()] = e
    if e.get("preferred_name"):
        employee_map[e["preferred_name"].strip().lower()] = e
    if e.get("employee_ref"):
        employee_map[str(e["employee_ref"]).strip().lower()] = e

# Sidebar
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
st.subheader("📂 Step 1: Upload Payroll PDF or Excel")
file_type = st.radio("File format", ["PDF", "Excel (.xlsx)"], horizontal=True)

uploaded = st.file_uploader(
    "Upload payroll file",
    type=["pdf"] if file_type == "PDF" else ["xlsx", "xls"]
)

df = None

if uploaded and file_type == "PDF":
    try:
        with pdfplumber.open(io.BytesIO(uploaded.read())) as pdf:
            all_tables = []
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    if table and len(table) > 1:
                        all_tables.extend(table)

        if all_tables:
            df = pd.DataFrame(all_tables[1:], columns=all_tables[0])
            df = df.dropna(how="all").reset_index(drop=True)
            st.success(f"✅ PDF parsed — {len(df)} rows extracted")
            st.dataframe(df.head(20), use_container_width=True)
        else:
            # Try text extraction
            st.warning("No tables found. Trying text extraction...")
            with pdfplumber.open(io.BytesIO(uploaded.getvalue())) as pdf:
                text = "\n".join(p.extract_text() or "" for p in pdf.pages)
            st.text_area("Raw PDF Text", text, height=300)
            st.info("💡 If the PDF has no tables, paste the data into Excel and upload as Excel instead.")
    except Exception as e:
        st.error(f"PDF error: {e}")

elif uploaded and file_type == "Excel (.xlsx)":
    xl = pd.ExcelFile(uploaded)
    sheet = st.selectbox("Select Sheet", xl.sheet_names)
    col1, col2 = st.columns(2)
    with col1:
        header_row = st.number_input("Header row (0 = first row)", 0, 20, 0)
    with col2:
        skip_last = st.number_input("Skip rows at bottom", 0, 10, 1)

    df = pd.read_excel(uploaded, sheet_name=sheet, header=int(header_row))
    df = df.dropna(how="all")
    if skip_last > 0:
        df = df.iloc[:-skip_last]
    df = df.reset_index(drop=True)
    st.dataframe(df.head(20), use_container_width=True)

if df is not None:
    st.markdown("---")
    st.subheader("🗂️ Step 2: Map Columns")
    cols = ["— not used —"] + list(df.columns.astype(str))

    c1, c2, c3 = st.columns(3)
    with c1:
        name_col      = st.selectbox("👤 Employee Name / Ref", cols)
        gross_col     = st.selectbox("💷 Gross Pay", cols)
        net_col       = st.selectbox("🏦 Net Pay", cols)
    with c2:
        paye_col      = st.selectbox("📊 PAYE Tax", cols)
        emp_nic_col   = st.selectbox("📊 Employee NIC", cols)
        er_nic_col    = st.selectbox("📊 Employer NIC", cols)
    with c3:
        emp_pen_col   = st.selectbox("📊 Employee Pension", cols)
        er_pen_col    = st.selectbox("📊 Employer Pension", cols)
        bank_col      = st.selectbox("🏦 Bank / Sort Code (optional)", cols)

    if name_col != "— not used —" and gross_col != "— not used —":
        st.markdown("---")
        st.subheader("🔍 Step 3: Preview & Match")

        def safe_float(val):
            try:
                return float(str(val).replace("£","").replace(",","").strip())
            except:
                return 0.0

        preview = []
        for _, row in df.iterrows():
            name_val = str(row[name_col]).strip() if pd.notna(row[name_col]) else ""
            if not name_val or name_val.lower() in ["nan","","name","employee","total","grand total"]:
                continue
            try:
                gross = safe_float(row[gross_col])
                if gross == 0:
                    continue
            except:
                continue

            emp    = employee_map.get(name_val.lower())
            status = "✅ Found" if emp else "❌ Not Found"

            preview.append({
                "Name":          name_val,
                "Gross Pay":     safe_float(row[gross_col]),
                "PAYE":          safe_float(row[paye_col])    if paye_col    != "— not used —" else 0,
                "Emp NIC":       safe_float(row[emp_nic_col]) if emp_nic_col != "— not used —" else 0,
                "Er NIC":        safe_float(row[er_nic_col])  if er_nic_col  != "— not used —" else 0,
                "Emp Pension":   safe_float(row[emp_pen_col]) if emp_pen_col != "— not used —" else 0,
                "Er Pension":    safe_float(row[er_pen_col])  if er_pen_col  != "— not used —" else 0,
                "Net Pay":       safe_float(row[net_col])     if net_col     != "— not used —" else 0,
                "Match":         status,
                "_emp":          emp,
            })

        if preview:
            display = pd.DataFrame([{k:v for k,v in r.items() if k!="_emp"} for r in preview])
            st.dataframe(display, use_container_width=True)

            matched   = sum(1 for r in preview if "✅" in r["Match"])
            unmatched = sum(1 for r in preview if "❌" in r["Match"])
            c1,c2,c3 = st.columns(3)
            c1.metric("Total Rows", len(preview))
            c2.metric("✅ Matched", matched)
            c3.metric("❌ Not Found", unmatched)

            if unmatched:
                st.warning(f"⚠️ {unmatched} employee(s) not found — will be skipped.")

            total_gross = sum(r["Gross Pay"] for r in preview)
            total_net   = sum(r["Net Pay"]   for r in preview)
            st.info(f"📊 Total Gross: **£{total_gross:,.2f}** | Total Net: **£{total_net:,.2f}** | Matched: **{matched}** employees")

            if matched > 0:
                if st.button("💾 Save Payroll to Database", type="primary"):
                    saved=0; errors=[]
                    for r in preview:
                        if "❌" in r["Match"]: continue
                        emp = r["_emp"]
                        try:
                            supabase.table("payroll_payments").upsert({
                                "employee_id":      emp["id"],
                                "client_id":        client_id,
                                "week_id":          week_id,
                                "gross_pay":        r["Gross Pay"],
                                "paye_tax":         r["PAYE"],
                                "employee_nic":     r["Emp NIC"],
                                "employer_nic":     r["Er NIC"],
                                "employee_pension": r["Emp Pension"],
                                "employer_pension": r["Er Pension"],
                                "net_pay":          r["Net Pay"],
                                "source_file":      uploaded.name,
                            }, on_conflict="employee_id,client_id,week_id").execute()
                            saved += 1
                        except Exception as e:
                            errors.append(f"{r['Name']}: {e}")

                    supabase.table("upload_log").insert({
                        "upload_type":"payroll","filename":uploaded.name,
                        "week_id":week_id,"records_processed":saved,
                        "records_failed":len(errors),
                        "status":"success" if not errors else "partial",
                        "error_log":{"errors":errors} if errors else None
                    }).execute()

                    if errors:
                        st.error(f"⚠️ Saved {saved} with {len(errors)} error(s):\n"+"\n".join(errors))
                    else:
                        st.success(f"✅ Saved payroll for {saved} employees — {selected_client} | Week {selected_week}!")
                    st.balloons()
        else:
            st.warning("No valid rows found. Check column mapping.")
