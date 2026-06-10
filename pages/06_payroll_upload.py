import streamlit as st
import pandas as pd
import pdfplumber
import io
import re
from datetime import date, timedelta, datetime
from db import get_client, page_header

st.set_page_config(page_title="Payroll Upload", page_icon="💷", layout="wide")
page_header("💷 Payroll Upload", "Upload payroll PDF or Excel — matched to timesheet employees by name")

supabase = get_client()

@st.cache_data(ttl=60)
def load_clients():
    return supabase.table("clients").select("id,name").eq("is_active", True).order("name").execute().data or []

@st.cache_data(ttl=30)
def load_available_weeks():
    """Load all distinct week_dates that have timesheet records — shown as dropdown."""
    recs = supabase.table("weekly_records").select("week_date").execute().data or []
    return sorted(set(r["week_date"] for r in recs if r.get("week_date")), reverse=True)

if st.sidebar.button("🔄 Refresh"):
    load_clients.clear()
    load_available_weeks.clear()
    st.rerun()

clients       = load_clients()
client_names  = [c["name"] for c in clients] if clients else []

# ── Sidebar ───────────────────────────────────────────────────
st.sidebar.header("⚙️ Select Week")

available_weeks = load_available_weeks()
if available_weeks:
    def fmt_week(d):
        try: return datetime.strptime(d, "%Y-%m-%d").strftime("w/c %d %b %Y")
        except: return d
    week_str = st.sidebar.selectbox(
        "📅 Week (from uploaded timesheets)",
        available_weeks,
        format_func=fmt_week
    )
    week_date = date.fromisoformat(week_str)
    st.sidebar.caption(f"Week starting **{week_date.strftime('%d %b %Y')}**")
else:
    st.sidebar.warning("No timesheet weeks found. Upload a timesheet first.")
    week_date = date.today() - timedelta(days=date.today().weekday())

selected_client = st.sidebar.selectbox("🏨 Hotel (optional)", ["All Hotels"] + client_names)
st.sidebar.markdown("---")

# ── Load records for selected week ────────────────────────────
@st.cache_data(ttl=30)
def load_week_records(wd):
    return supabase.table("weekly_records").select(
        "id,employee_name,client_name,hours_worked,payroll_amount,week_date"
    ).eq("week_date", str(wd)).execute().data or []

@st.cache_data(ttl=60)
def load_all_employee_names():
    recs = supabase.table("weekly_records").select("employee_name").execute().data or []
    return sorted(set(r["employee_name"].strip() for r in recs if r.get("employee_name")))

@st.cache_data(ttl=60)
def load_employee_hotel_lookup():
    recs = supabase.table("weekly_records").select(
        "employee_name,client_name,week_date"
    ).order("week_date", desc=True).execute().data or []
    lookup = {}
    for r in recs:
        name = (r.get("employee_name") or "").strip()
        if name and name not in lookup:
            lookup[name] = r.get("client_name", "")
    return lookup

week_recs          = load_week_records(week_date)
all_known_names    = load_all_employee_names()
emp_hotel_lookup   = load_employee_hotel_lookup()
hotel_options      = ["— not set —"] + client_names

if selected_client != "All Hotels":
    week_recs = [r for r in week_recs if r["client_name"] == selected_client]
timesheet_names = [r["employee_name"] for r in week_recs]

if week_recs:
    st.info(f"📋 **{len(week_recs)}** timesheet employees for week **{week_date.strftime('%d %b %Y')}**")
elif all_known_names:
    st.warning(f"⚠️ No timesheets for **{week_date.strftime('%d %b %Y')}** in the selected hotel filter.")
else:
    st.warning("⚠️ No employees in database yet. Upload timesheets first.")

# ── PDF parser ────────────────────────────────────────────────
def parse_payroll_pdf(file_bytes):
    employees = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.split('\n'):
                tokens = line.strip().split()
                if not tokens or not tokens[0].isdigit():
                    continue
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

def best_match(pdf_name, name_list):
    if not name_list:
        return None
    pdf_lower   = pdf_name.lower()
    pdf_surname = pdf_lower.split()[-1] if pdf_lower.split() else ""
    for n in name_list:
        if n.lower() == pdf_lower:
            return n
    surname_matches = [n for n in name_list if pdf_surname and pdf_surname in n.lower()]
    if len(surname_matches) == 1:
        return surname_matches[0]
    pdf_words = set(pdf_lower.split())
    for n in name_list:
        if pdf_words & set(n.lower().split()):
            return n
    return None

def detect_hotel(matched_name):
    if not matched_name or matched_name in ('— no match —', '— skip —'):
        return selected_client if selected_client != "All Hotels" else "— not set —"
    for r in week_recs:
        if r["employee_name"] == matched_name:
            return r["client_name"]
    known = emp_hotel_lookup.get(matched_name, "")
    if known and known in client_names:
        return known
    return selected_client if selected_client != "All Hotels" else "— not set —"

# ── Upload ────────────────────────────────────────────────────
st.markdown("---")
st.subheader("📂 Upload Payroll File")

file_type = st.radio("File format", ["PDF", "Excel (.xlsx / .csv)"], horizontal=True)
uploaded  = st.file_uploader(
    "Upload payroll file",
    type=["pdf"] if file_type == "PDF" else ["xlsx", "xls", "csv"]
)

parsed_rows = []

if uploaded:
    if file_type == "PDF":
        try:
            employees = parse_payroll_pdf(uploaded.read())
            if not employees:
                st.error("❌ No employee data found. Check it's an ARVY payroll summary PDF.")
            else:
                st.success(f"✅ Found **{len(employees)}** employees in PDF")
                for emp in employees:
                    matched = best_match(emp['pdf_name'], all_known_names)
                    parsed_rows.append({
                        'PDF Name':    emp['pdf_name'],
                        'Emp Ref':     emp['emp_ref'],
                        'Gross Pay £': emp['gross_pay'],
                        'Net Pay £':   emp['net_pay'],
                        'Matched To':  matched or '— no match —',
                        'Hotel':       detect_hotel(matched),
                    })
        except Exception as e:
            st.error(f"❌ PDF error: {e}")
    else:
        try:
            if uploaded.name.endswith('.csv'):
                df = pd.read_csv(uploaded)
            else:
                xl = pd.ExcelFile(uploaded)
                sheet      = st.selectbox("Sheet", xl.sheet_names) if len(xl.sheet_names) > 1 else xl.sheet_names[0]
                header_row = st.number_input("Header row (0 = first row)", 0, 20, 0)
                df = pd.read_excel(uploaded, sheet_name=sheet, header=int(header_row))
            df = df.dropna(how='all').reset_index(drop=True)
            st.dataframe(df.head(20), use_container_width=True)

            cols = ['— not used —'] + list(df.columns.astype(str))
            c1, c2 = st.columns(2)
            with c1: name_col = st.selectbox("👤 Employee Name column", cols)
            with c2: amt_col  = st.selectbox("💷 Net Pay / Amount column", cols)

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
                    matched = best_match(n, all_known_names)
                    parsed_rows.append({
                        'PDF Name':    n,
                        'Emp Ref':     '—',
                        'Gross Pay £': amt,
                        'Net Pay £':   amt,
                        'Matched To':  matched or '— no match —',
                        'Hotel':       detect_hotel(matched),
                    })
        except Exception as e:
            st.error(f"❌ Excel error: {e}")

# ── Preview & manual matching ─────────────────────────────────
if parsed_rows:
    st.markdown("---")
    st.subheader("🔍 Preview & Confirm Matching")
    st.caption(f"Payments will be saved to week **{week_date.strftime('%d %b %Y')}**. Adjust employee and hotel dropdowns if needed.")

    match_options = ['— skip —'] + all_known_names
    confirmed = []

    h1, h2, h3, h4, h5 = st.columns([2, 2, 2, 1, 1])
    h1.markdown("**Payroll Name**")
    h2.markdown("**Employee (timesheet)**")
    h3.markdown("**Hotel**")
    h4.markdown("**Gross**")
    h5.markdown("**Net**")
    st.markdown("---")

    for i, row in enumerate(parsed_rows):
        c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 1, 1])
        with c1:
            st.markdown(f"**{row['PDF Name']}**  \n*Ref: {row['Emp Ref']}*")
        with c2:
            cur_idx = match_options.index(row['Matched To']) if row['Matched To'] in match_options else 0
            sel = st.selectbox("Employee", match_options, index=cur_idx,
                               key=f"match_{i}", label_visibility="collapsed")
        with c3:
            auto_hotel = detect_hotel(sel) if sel != '— skip —' else row['Hotel']
            h_idx      = hotel_options.index(auto_hotel) if auto_hotel in hotel_options else 0
            hotel_sel  = st.selectbox("Hotel", hotel_options, index=h_idx,
                                      key=f"hotel_{i}", label_visibility="collapsed")
        with c4:
            st.markdown(f"£{row['Gross Pay £']:,.2f}")
        with c5:
            st.markdown(f"**£{row['Net Pay £']:,.2f}**")

        confirmed.append({'timesheet_name': sel, 'net_pay': row['Net Pay £'],
                          'pdf_name': row['PDF Name'], 'hotel': hotel_sel})

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
            hotel   = r['hotel'] if r['hotel'] != '— not set —' else "Unknown"
            try:
                existing = supabase.table("weekly_records").select("id").eq(
                    "employee_name", ts_name).eq("week_date", str(week_date)).limit(1).execute().data
                if existing:
                    supabase.table("weekly_records").update(
                        {"payroll_amount": r['net_pay']}
                    ).eq("id", existing[0]["id"]).execute()
                else:
                    supabase.table("weekly_records").upsert({
                        "week_date": str(week_date), "employee_name": ts_name,
                        "client_name": hotel, "hours_worked": 0,
                        "payroll_amount": r['net_pay'],
                    }, on_conflict="week_date,employee_name,client_name").execute()
                saved += 1
            except Exception as e:
                errors.append(f"{ts_name}: {e}")
        load_week_records.clear()
        if errors:
            st.error(f"⚠️ Saved {saved}, errors:\n" + "\n".join(errors))
        else:
            st.success(f"✅ Payroll saved for {saved} employees — Week **{week_date.strftime('%d %b %Y')}**")
            st.balloons()

# ── Current week summary ──────────────────────────────────────
st.markdown("---")
st.subheader(f"📋 Payroll Records — {week_date.strftime('%d %b %Y')}")
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
