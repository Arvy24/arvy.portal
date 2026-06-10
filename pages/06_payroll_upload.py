import streamlit as st
import pandas as pd
import pdfplumber
import io
import re
from datetime import date, timedelta, datetime
from db import get_client, page_header

st.set_page_config(page_title="Payroll Upload", page_icon="💷", layout="wide")
page_header("💷 Payroll Upload", "Select hotel & week first — then upload payroll PDF or Excel")

supabase = get_client()

@st.cache_data(ttl=60)
def load_clients():
    return supabase.table("clients").select("id,name").eq("is_active", True).order("name").execute().data or []

if st.sidebar.button("🔄 Refresh"):
    load_clients.clear(); st.rerun()

clients      = load_clients()
client_names = [c["name"] for c in clients] if clients else []

# ═══════════════════════════════════════════════════════════════
# STEP 1 — Hotel & Week (always at top)
# ═══════════════════════════════════════════════════════════════
st.subheader("1️⃣  Select Hotel & Week Dates")
st.caption("These must match the dates used when the timesheet was uploaded.")

default_monday = date.today() - timedelta(days=date.today().weekday() + 7)  # last week
default_sunday = default_monday + timedelta(days=6)

hcol, s_col, e_col = st.columns([2, 1, 1])
with hcol:
    selected_client = st.selectbox("🏨 Hotel / Client", ["All Hotels"] + client_names)
with s_col:
    week_start = st.date_input("📅 Week Start", value=default_monday)
with e_col:
    week_end = st.date_input("📅 Week End", value=default_sunday)

week_date = week_start   # primary key used for DB lookup

st.info(
    f"📌 Saving to: **{selected_client}** | "
    f"**{week_start.strftime('%d %b %Y')}** → **{week_end.strftime('%d %b %Y')}**  "
    f"  *(week key = {week_date})*"
)

# Load employees for this week (used for auto-matching)
@st.cache_data(ttl=30)
def load_week_employees(wd):
    recs = supabase.table("weekly_records").select(
        "id,employee_name,client_name,hours_worked"
    ).eq("week_date", str(wd)).execute().data or []
    return recs

@st.cache_data(ttl=60)
def load_all_employee_names():
    recs = supabase.table("weekly_records").select("employee_name").execute().data or []
    return sorted(set(r["employee_name"].strip() for r in recs if r.get("employee_name")))

week_employees  = load_week_employees(week_date)
all_known_names = load_all_employee_names()
week_names      = [r["employee_name"] for r in week_employees]

if week_employees:
    st.success(f"✅ **{len(week_employees)}** timesheet employees found for this week")
else:
    st.warning(f"⚠️ No timesheet records for **{week_start.strftime('%d %b %Y')}** — upload the timesheet first, or check the dates above match exactly.")

st.markdown("---")

# ═══════════════════════════════════════════════════════════════
# Name matching helpers
# ═══════════════════════════════════════════════════════════════
def best_match(pdf_name, name_list):
    """Match payroll name (Initial Surname) → timesheet full name."""
    if not name_list:
        return None
    pl  = pdf_name.lower().strip()
    sur = pl.split()[-1] if pl.split() else ""

    # 1. Exact
    for n in name_list:
        if n.lower() == pl:
            return n
    # 2. Surname contained in timesheet name (most useful for "A Vaghela" → "Vaghelu Aanibhui")
    matches = [n for n in name_list if sur and sur in n.lower()]
    if len(matches) == 1:
        return matches[0]
    # 3. Any word overlap
    pw = set(pl.split())
    for n in name_list:
        if pw & set(n.lower().split()):
            return n
    return None

# ═══════════════════════════════════════════════════════════════
# STEP 2 — Upload
# ═══════════════════════════════════════════════════════════════
st.subheader("2️⃣  Upload Payroll File")
file_type = st.radio("File format", ["PDF", "Excel (.xlsx / .csv)"], horizontal=True)
uploaded  = st.file_uploader(
    "Upload payroll file",
    type=["pdf"] if file_type == "PDF" else ["xlsx", "xls", "csv"]
)

# ── PDF parser ────────────────────────────────────────────────
def parse_payroll_pdf(file_bytes):
    employees = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.split('\n'):
                tokens = line.strip().split()
                if not tokens or not tokens[0].isdigit(): continue
                if any(kw in line.lower() for kw in ['total:','department:','process date total']): continue
                emp_ref    = tokens[0]
                name_parts = []
                num_start  = 1
                for i, t in enumerate(tokens[1:], 1):
                    try:    float(t.replace(',','')); num_start = i; break
                    except: name_parts.append(t)
                if not name_parts: continue
                numbers = []
                for t in tokens[num_start:]:
                    try:    numbers.append(float(t.replace(',','')))
                    except: pass
                if len(numbers) < 3: continue
                employees.append({
                    'emp_ref':   emp_ref,
                    'pdf_name':  ' '.join(name_parts),
                    'gross_pay': numbers[1],
                    'net_pay':   numbers[-1],
                })
    return employees

raw_rows = []  # {pdf_name, emp_ref, gross_pay, net_pay}

if uploaded:
    if file_type == "PDF":
        try:
            emps = parse_payroll_pdf(uploaded.read())
            if not emps:
                st.error("❌ No employee data found. Check it's an ARVY payroll summary PDF.")
            else:
                st.success(f"✅ Parsed **{len(emps)}** employees from PDF")
                raw_rows = emps
        except Exception as e:
            st.error(f"❌ PDF error: {e}")
    else:
        try:
            if uploaded.name.endswith('.csv'):
                df_up = pd.read_csv(uploaded)
            else:
                xl         = pd.ExcelFile(uploaded)
                sheet      = st.selectbox("Sheet", xl.sheet_names) if len(xl.sheet_names) > 1 else xl.sheet_names[0]
                header_row = st.number_input("Header row (0 = first row)", 0, 20, 0)
                df_up = pd.read_excel(uploaded, sheet_name=sheet, header=int(header_row))
            df_up = df_up.dropna(how='all').reset_index(drop=True)
            st.dataframe(df_up.head(20), use_container_width=True)

            cols = ['— not used —'] + list(df_up.columns.astype(str))
            c1, c2 = st.columns(2)
            with c1: name_col = st.selectbox("👤 Employee Name column", cols)
            with c2: amt_col  = st.selectbox("💷 Net Pay column", cols)

            if name_col != '— not used —' and amt_col != '— not used —':
                skip = {'nan','','name','employee','total','grand total','employee name'}
                for _, row in df_up.iterrows():
                    n = str(row[name_col]).strip() if pd.notna(row[name_col]) else ''
                    if n.lower() in skip or not n: continue
                    try:    amt = float(str(row[amt_col]).replace('£','').replace(',','').strip())
                    except: continue
                    if amt == 0: continue
                    raw_rows.append({'emp_ref':'—','pdf_name':n,'gross_pay':amt,'net_pay':amt})
                if raw_rows:
                    st.success(f"✅ Parsed **{len(raw_rows)}** employees from Excel")
        except Exception as e:
            st.error(f"❌ Excel error: {e}")

# ═══════════════════════════════════════════════════════════════
# STEP 3 — Auto-match & preview (no per-row dropdowns)
# ═══════════════════════════════════════════════════════════════
if raw_rows:
    st.markdown("---")
    st.subheader("3️⃣  Auto-Match Results")

    # Prefer week_names for matching (same week) — fall back to all_known_names
    match_pool_primary   = week_names if week_names else all_known_names
    match_pool_secondary = all_known_names

    matched_rows   = []
    unmatched_rows = []

    for emp in raw_rows:
        m = best_match(emp['pdf_name'], match_pool_primary)
        if not m and match_pool_secondary:
            m = best_match(emp['pdf_name'], match_pool_secondary)
        # Get hotel from week record if found
        hotel = selected_client if selected_client != "All Hotels" else "— not set —"
        for wr in week_employees:
            if wr["employee_name"] == m:
                hotel = wr["client_name"]
                break
        row = {**emp, 'matched_name': m, 'hotel': hotel}
        (matched_rows if m else unmatched_rows).append(row)

    # ── Matched table ─────────────────────────────────────────
    if matched_rows:
        st.success(f"✅ **{len(matched_rows)}** employees auto-matched")
        df_match = pd.DataFrame([{
            "Payroll Name":  r['pdf_name'],
            "Ref":           r['emp_ref'],
            "→ Timesheet":   r['matched_name'],
            "Hotel":         r['hotel'],
            "Gross £":       r['gross_pay'],
            "Net Pay £":     r['net_pay'],
        } for r in matched_rows])
        st.dataframe(df_match, use_container_width=True, hide_index=True)

    # ── Unmatched — small dropdown section ───────────────────
    unmatched_resolved = []
    if unmatched_rows:
        st.warning(f"⚠️ **{len(unmatched_rows)}** employee(s) could not be auto-matched — assign manually below:")
        match_opts = ['— skip —'] + (week_names if week_names else all_known_names)
        for i, emp in enumerate(unmatched_rows):
            c1, c2, c3, c4 = st.columns([2, 3, 1, 1])
            with c1: st.markdown(f"**{emp['pdf_name']}** *(Ref {emp['emp_ref']})*")
            with c2:
                sel = st.selectbox("Match to", match_opts, key=f"um_{i}",
                                   label_visibility="collapsed")
            with c3: st.markdown(f"£{emp['gross_pay']:,.2f}")
            with c4: st.markdown(f"**£{emp['net_pay']:,.2f}**")
            if sel != '— skip —':
                unmatched_resolved.append({**emp, 'matched_name': sel, 'hotel': selected_client if selected_client != "All Hotels" else "— not set —"})

    all_to_save  = matched_rows + unmatched_resolved
    total_net    = sum(r['net_pay'] for r in all_to_save)
    skipped      = len(unmatched_rows) - len(unmatched_resolved)

    st.markdown("---")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Auto-matched",   len(matched_rows))
    c2.metric("Manually fixed", len(unmatched_resolved))
    c3.metric("Skipped",        skipped)
    c4.metric("Total Net Pay",  f"£{total_net:,.2f}")

    if all_to_save and st.button("💾 Save All Payroll Payments", type="primary", use_container_width=True):
        saved = 0; errors = []
        hotel_default = selected_client if selected_client != "All Hotels" else "Unknown"
        for r in all_to_save:
            ts_name = r['matched_name']
            hotel   = r['hotel'] if r['hotel'] not in ('— not set —','') else hotel_default
            try:
                existing = supabase.table("weekly_records").select("id").eq(
                    "employee_name", ts_name).eq("week_date", str(week_date)).limit(1).execute().data
                if existing:
                    supabase.table("weekly_records").update(
                        {"payroll_amount": r['net_pay']}
                    ).eq("id", existing[0]["id"]).execute()
                else:
                    supabase.table("weekly_records").upsert({
                        "week_date":      str(week_date),
                        "employee_name":  ts_name,
                        "client_name":    hotel,
                        "hours_worked":   0,
                        "payroll_amount": r['net_pay'],
                    }, on_conflict="week_date,employee_name,client_name").execute()
                saved += 1
            except Exception as e:
                errors.append(f"{ts_name}: {e}")

        if errors:
            st.error(f"⚠️ Saved {saved}, errors:\n" + "\n".join(errors))
        else:
            st.success(f"✅ Payroll saved for {saved} employees — **{week_start.strftime('%d %b %Y')} → {week_end.strftime('%d %b %Y')}**")
            st.balloons()

# ═══════════════════════════════════════════════════════════════
# Current week summary
# ═══════════════════════════════════════════════════════════════
st.markdown("---")
st.subheader(f"📋 Payroll Records — {week_start.strftime('%d %b %Y')} → {week_end.strftime('%d %b %Y')}")
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
        st.info("No payroll records saved for this week yet.")
except Exception as e:
    st.warning(f"Could not load: {e}")

st.markdown("---")
st.caption("💷 Payroll Upload  •  ARVY Portal v1.0")
