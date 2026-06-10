import streamlit as st
import pandas as pd
import pdfplumber
import io
import re
from datetime import date, timedelta
from db import get_client, page_header

st.set_page_config(page_title="Payroll Upload", page_icon="💷", layout="wide")
page_header("💷 Payroll Upload", "Upload payroll PDF or Excel — matched to timesheet employees by name")

supabase = get_client()

@st.cache_data(ttl=60)
def load_clients():
    return supabase.table("clients").select("id,name").eq("is_active", True).order("name").execute().data or []

if st.sidebar.button("🔄 Refresh"):
    load_clients.clear(); st.rerun()

clients = load_clients()

# ── Sidebar ───────────────────────────────────────────────────
st.sidebar.header("⚙️ Select Week")
week_date = st.sidebar.date_input(
    "📅 Week Date (start of week)",
    value=date.today() - timedelta(days=date.today().weekday()),
)
client_names    = [c["name"] for c in clients] if clients else []
selected_client = st.sidebar.selectbox("🏨 Hotel (optional)", ["All Hotels"] + client_names)
st.sidebar.markdown("---")

# ── Load timesheet employees for this week ────────────────────
@st.cache_data(ttl=30)
def load_week_records(wd):
    return supabase.table("weekly_records").select(
        "id,employee_name,client_name,hours_worked,payroll_amount,week_date"
    ).eq("week_date", str(wd)).execute().data or []

@st.cache_data(ttl=60)
def load_all_employee_names():
    """Load all unique employee names ever uploaded — used as match options."""
    recs = supabase.table("weekly_records").select("employee_name").execute().data or []
    return sorted(set(r["employee_name"].strip() for r in recs if r.get("employee_name")))

week_recs = load_week_records(week_date)
if selected_client != "All Hotels":
    week_recs = [r for r in week_recs if r["client_name"] == selected_client]

# All known names (used for matching dropdown — not filtered by week)
all_known_names = load_all_employee_names()
timesheet_names = [r["employee_name"] for r in week_recs]  # week-specific (for auto-match hint)

if week_recs:
    st.info(f"📋 **{len(week_recs)}** timesheet employees found for week **{week_date}**")
elif all_known_names:
    st.warning(f"⚠️ No timesheets for week **{week_date}** — but {len(all_known_names)} known employees available to match. Make sure the week date matches your timesheet.")
else:
    st.warning("⚠️ No employees in database yet. Upload timesheets first.")

# ── PDF parser ────────────────────────────────────────────────
def parse_payroll_pdf(file_bytes):
    """Extract employee ref, name, gross pay, net pay from ARVY payroll PDF."""
    employees = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.split('\n'):
                tokens = line.strip().split()
                if not tokens or not tokens[0].isdigit():
                    continue
                # Skip total/summary lines
                if any(kw in line.lower() for kw in ['total:', 'department:', 'process date total']):
                    continue
                emp_ref = tokens[0]
                name_parts = []
                num_start = 1
                for i, t in enumerate(tokens[1:], 1):
                    try:
                        float(t.replace(',', ''))
                        num_start = i
                        break
                    except ValueError:
                        name_parts.append(t)
                if not name_parts:
                    continue
                numbers = []
                for t in tokens[num_start:]:
                    try:
                        numbers.append(float(t.replace(',', '')))
                    except ValueError:
                        pass
                if len(numbers) < 3:
                    continue
                employees.append({
                    'emp_ref':   emp_ref,
                    'pdf_name':  ' '.join(name_parts),
                    'gross_pay': numbers[1],
                    'net_pay':   numbers[-1],
                })
    return employees

# ── Name matching helper ──────────────────────────────────────
def best_match(pdf_name, timesheet_list):
    """Try to find the best matching timesheet name for a PDF payroll name."""
    if not timesheet_list:
        return None
    pdf_lower   = pdf_name.lower()
    pdf_surname = pdf_lower.split()[-1] if pdf_lower.split() else ""

    # 1. Exact match
    for n in timesheet_list:
        if n.lower() == pdf_lower:
            return n

    # 2. Surname match (last word)
    surname_matches = [n for n in timesheet_list if pdf_surname and pdf_surname in n.lower()]
    if len(surname_matches) == 1:
        return surname_matches[0]

    # 3. Any word overlap
    pdf_words = set(pdf_lower.split())
    for n in timesheet_list:
        ts_words = set(n.lower().split())
        if pdf_words & ts_words:
            return n

    return None

# ── Upload ────────────────────────────────────────────────────
st.markdown("---")
st.subheader("📂 Upload Payroll File")

file_type = st.radio("File format", ["PDF", "Excel (.xlsx / .csv)"], horizontal=True)

uploaded = st.file_uploader(
    "Upload payroll file",
    type=["pdf"] if file_type == "PDF" else ["xlsx", "xls", "csv"]
)

parsed_rows = []   # list of dicts: pdf_name, matched_name, net_pay, gross_pay

if uploaded:
    # ── PDF ──────────────────────────────────────────────────
    if file_type == "PDF":
        try:
            employees = parse_payroll_pdf(uploaded.read())
            if not employees:
                st.error("❌ No employee data found in this PDF. Check it's an ARVY payroll summary PDF.")
            else:
                st.success(f"✅ Found **{len(employees)}** employees in PDF")
                for emp in employees:
                    matched = best_match(emp['pdf_name'], timesheet_names)
                    parsed_rows.append({
                        'PDF Name':       emp['pdf_name'],
                        'Emp Ref':        emp['emp_ref'],
                        'Gross Pay £':    emp['gross_pay'],
                        'Net Pay £':      emp['net_pay'],
                        'Matched To':     matched or '— no match —',
                    })
        except Exception as e:
            st.error(f"❌ PDF error: {e}")

    # ── Excel ─────────────────────────────────────────────────
    else:
        try:
            if uploaded.name.endswith('.csv'):
                df = pd.read_csv(uploaded)
            else:
                xl = pd.ExcelFile(uploaded)
                sheet = st.selectbox("Sheet", xl.sheet_names) if len(xl.sheet_names) > 1 else xl.sheet_names[0]
                header_row = st.number_input("Header row (0 = first row)", 0, 20, 0)
                df = pd.read_excel(uploaded, sheet_name=sheet, header=int(header_row))
            df = df.dropna(how='all').reset_index(drop=True)
            st.dataframe(df.head(20), use_container_width=True)

            cols = ['— not used —'] + list(df.columns.astype(str))
            c1, c2 = st.columns(2)
            with c1:
                name_col = st.selectbox("👤 Employee Name column", cols)
            with c2:
                amt_col  = st.selectbox("💷 Net Pay / Amount column", cols)

            if name_col != '— not used —' and amt_col != '— not used —':
                skip = {'nan','','name','employee','total','grand total','employee name'}
                for _, row in df.iterrows():
                    n = str(row[name_col]).strip() if pd.notna(row[name_col]) else ''
                    if n.lower() in skip or not n:
                        continue
                    try:
                        amt = float(str(row[amt_col]).replace('£','').replace(',','').strip())
                    except:
                        continue
                    if amt == 0:
                        continue
                    matched = best_match(n, timesheet_names)
                    parsed_rows.append({
                        'PDF Name':    n,
                        'Emp Ref':     '—',
                        'Gross Pay £': amt,
                        'Net Pay £':   amt,
                        'Matched To':  matched or '— no match —',
                    })
        except Exception as e:
            st.error(f"❌ Excel error: {e}")

# ── Preview & manual matching ─────────────────────────────────
if parsed_rows:
    st.markdown("---")
    st.subheader("🔍 Preview & Confirm Matching")
    st.caption("The app tries to auto-match payroll names to your timesheet names. Correct any that say '— no match —' using the dropdown.")

    match_options = ['— skip —'] + all_known_names

    confirmed = []
    for i, row in enumerate(parsed_rows):
        c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
        with c1:
            st.markdown(f"**{row['PDF Name']}** (Ref: {row['Emp Ref']})")
        with c2:
            current_idx = 0
            if row['Matched To'] in match_options:
                current_idx = match_options.index(row['Matched To'])
            sel = st.selectbox(
                f"Match to timesheet employee",
                match_options,
                index=current_idx,
                key=f"match_{i}",
                label_visibility="collapsed"
            )
        with c3:
            st.markdown(f"Gross: **£{row['Gross Pay £']:,.2f}**")
        with c4:
            st.markdown(f"Net: **£{row['Net Pay £']:,.2f}**")
        confirmed.append({'timesheet_name': sel, 'net_pay': row['Net Pay £'], 'pdf_name': row['PDF Name']})

    st.markdown("---")
    valid     = [r for r in confirmed if r['timesheet_name'] != '— skip —']
    skipped   = [r for r in confirmed if r['timesheet_name'] == '— skip —']
    total_net = sum(r['net_pay'] for r in valid)

    c1, c2, c3 = st.columns(3)
    c1.metric("Employees to Save", len(valid))
    c2.metric("Skipped", len(skipped))
    c3.metric("Total Net Pay", f"£{total_net:,.2f}")

    if valid and st.button("💾 Save Payroll Payments", type="primary", use_container_width=True):
        saved = 0; errors = []

        for r in valid:
            ts_name = r['timesheet_name']
            try:
                # Look up the exact record by name + week_date (works regardless of sidebar week filter)
                existing = supabase.table("weekly_records").select("id,client_name").eq(
                    "employee_name", ts_name
                ).eq("week_date", str(week_date)).limit(1).execute().data
                if existing:
                    supabase.table("weekly_records").update({
                        "payroll_amount": r['net_pay']
                    }).eq("id", existing[0]["id"]).execute()
                else:
                    client = selected_client if selected_client != "All Hotels" else "Unknown"
                    supabase.table("weekly_records").upsert({
                        "week_date":      str(week_date),
                        "employee_name":  ts_name,
                        "client_name":    client,
                        "hours_worked":   0,
                        "payroll_amount": r['net_pay'],
                    }, on_conflict="week_date,employee_name,client_name").execute()
                saved += 1
            except Exception as e:
                errors.append(f"{ts_name}: {e}")

        load_week_records.clear()
        if errors:
            st.error(f"⚠️ Saved {saved}, errors:\n" + "\n".join(errors))
        else:
            st.success(f"✅ Payroll saved for {saved} employees — Week **{week_date}**")
            st.balloons()

# ── Current week summary ──────────────────────────────────────
st.markdown("---")
st.subheader(f"📋 Payroll Records — Week {week_date}")
try:
    q = supabase.table("weekly_records").select(
        "employee_name,client_name,hours_worked,payroll_amount"
    ).eq("week_date", str(week_date)).gt("payroll_amount", 0).order("employee_name").execute().data or []
    if q:
        df_q = pd.DataFrame(q)
        df_q.columns = ["Employee","Hotel","Hours","Payroll £"]
        st.dataframe(df_q, use_container_width=True, hide_index=True)
        st.metric("Total Net Pay", f"£{df_q['Payroll £'].sum():,.2f}")
    else:
        st.info("No payroll records yet for this week.")
except Exception as e:
    st.warning(f"Could not load: {e}")

st.markdown("---")
st.caption("💷 Payroll Upload  •  ARVY Portal v1.0")
