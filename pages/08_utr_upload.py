import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime
from db import get_client, page_header

st.set_page_config(page_title="UTR Upload", page_icon="📑", layout="wide")
page_header("📑 UTR Upload", "Select hotel & week first — then upload UTR payment file")

supabase = get_client()

@st.cache_data(ttl=60)
def load_clients():
    return supabase.table("clients").select("id,name").eq("is_active", True).order("name").execute().data or []

if st.sidebar.button("🔄 Refresh"):
    load_clients.clear(); st.rerun()

clients      = load_clients()
client_names = [c["name"] for c in clients] if clients else []
if not clients:
    st.error("⚠️ No hotels found."); st.stop()

# ═══════════════════════════════════════════════════════════════
# STEP 1 — Hotel & Week
# ═══════════════════════════════════════════════════════════════
st.subheader("1️⃣  Select Hotel & Week Dates")
st.caption("Must match the dates used when the timesheet was uploaded.")

default_monday = date.today() - timedelta(days=date.today().weekday() + 7)
default_sunday = default_monday + timedelta(days=6)

hcol, s_col, e_col = st.columns([2, 1, 1])
with hcol:    selected_client = st.selectbox("🏨 Hotel / Client", ["All Hotels"] + client_names)
with s_col:   week_start = st.date_input("📅 Week Start", value=default_monday)
with e_col:   week_end   = st.date_input("📅 Week End",   value=default_sunday)

week_date = week_start

st.info(
    f"📌 Saving to: **{selected_client}** | "
    f"**{week_start.strftime('%d %b %Y')}** → **{week_end.strftime('%d %b %Y')}**"
)

@st.cache_data(ttl=30)
def load_week_employees(wd):
    return supabase.table("weekly_records").select(
        "id,employee_name,client_name"
    ).eq("week_date", str(wd)).execute().data or []

week_employees = load_week_employees(week_date)
name_lookup    = {r["employee_name"].strip().lower(): r for r in week_employees}
week_names     = [r["employee_name"] for r in week_employees]

if week_employees:
    st.success(f"✅ **{len(week_employees)}** timesheet employees found for this week")
else:
    st.warning("⚠️ No timesheet records for this week — upload the timesheet first.")

st.markdown("---")

# ═══════════════════════════════════════════════════════════════
# STEP 2 — Upload
# ═══════════════════════════════════════════════════════════════
st.subheader("2️⃣  Upload UTR Payment File")
st.caption("Excel / CSV with Employee Name and UTR Amount columns")
uploaded = st.file_uploader("Upload file", type=["xlsx", "xls", "csv"])

df = None
if uploaded:
    try:
        if uploaded.name.endswith(".csv"):
            df = pd.read_csv(uploaded)
        else:
            xl         = pd.ExcelFile(uploaded)
            sheet      = st.selectbox("Sheet", xl.sheet_names) if len(xl.sheet_names) > 1 else xl.sheet_names[0]
            header_row = st.number_input("Header row (0 = first row)", 0, 20, 0)
            df = pd.read_excel(uploaded, sheet_name=sheet, header=int(header_row))
        df = df.dropna(how="all").reset_index(drop=True)
        st.success(f"✅ File loaded — {len(df)} rows")
        st.dataframe(df.head(20), use_container_width=True)
    except Exception as e:
        st.error(f"File error: {e}")

if df is not None:
    cols = ["— not used —"] + list(df.columns.astype(str))
    c1, c2 = st.columns(2)
    with c1: name_col   = st.selectbox("👤 Employee Name column", cols)
    with c2: amount_col = st.selectbox("💰 UTR Amount column", cols)

    if name_col != "— not used —" and amount_col != "— not used —":
        def safe_float(v):
            try: return float(str(v).replace("£","").replace(",","").strip())
            except: return 0.0

        skip = {"nan","","name","employee","total","grand total","employee name"}
        raw_rows = []
        for _, row in df.iterrows():
            n = str(row[name_col]).strip() if pd.notna(row[name_col]) else ""
            if n.lower() in skip or not n: continue
            amt = safe_float(row.get(amount_col, 0))
            if amt == 0: continue
            raw_rows.append({"name": n, "amount": amt})

        if not raw_rows:
            st.warning("No valid rows found. Check column mapping.")
        else:
            st.markdown("---")
            st.subheader("3️⃣  Auto-Match Results")

            matched_rows   = []
            unmatched_rows = []
            for r in raw_rows:
                matched = r["name"].strip().lower() in name_lookup
                (matched_rows if matched else unmatched_rows).append(r)

            if matched_rows:
                st.success(f"✅ **{len(matched_rows)}** employees matched to timesheet")
                df_m = pd.DataFrame([{
                    "Employee Name":  r["name"],
                    "UTR Amount £":   r["amount"],
                    "Status":         "✅ Matched",
                } for r in matched_rows])
                st.dataframe(df_m, use_container_width=True, hide_index=True)

            unmatched_resolved = []
            if unmatched_rows:
                st.warning(f"⚠️ **{len(unmatched_rows)}** employee(s) not found in timesheet — assign manually:")
                match_opts = ['— skip —'] + week_names
                for i, r in enumerate(unmatched_rows):
                    c1, c2, c3 = st.columns([3, 3, 1])
                    with c1: st.markdown(f"**{r['name']}**")
                    with c2:
                        sel = st.selectbox("Match to", match_opts, key=f"um_{i}",
                                           label_visibility="collapsed")
                    with c3: st.markdown(f"**£{r['amount']:,.2f}**")
                    if sel != '— skip —':
                        unmatched_resolved.append({"name": sel, "amount": r["amount"]})

            all_to_save = matched_rows + unmatched_resolved
            total       = sum(r["amount"] for r in all_to_save)

            st.markdown("---")
            c1, c2, c3 = st.columns(3)
            c1.metric("To Save", len(all_to_save))
            c2.metric("Skipped", len(unmatched_rows) - len(unmatched_resolved))
            c3.metric("Total UTR", f"£{total:,.2f}")

            if all_to_save and st.button("💾 Save UTR Payments", type="primary", use_container_width=True):
                saved = 0; errors = []
                hotel = selected_client if selected_client != "All Hotels" else "Unknown"
                for r in all_to_save:
                    name = r["name"]
                    try:
                        existing = supabase.table("weekly_records").select("id").eq(
                            "employee_name", name).eq("week_date", str(week_date)).limit(1).execute().data
                        if existing:
                            supabase.table("weekly_records").update(
                                {"utr_amount": r["amount"]}
                            ).eq("id", existing[0]["id"]).execute()
                        else:
                            supabase.table("weekly_records").upsert({
                                "week_date":     str(week_date),
                                "employee_name": name,
                                "client_name":   hotel,
                                "hours_worked":  0,
                                "utr_amount":    r["amount"],
                            }, on_conflict="week_date,employee_name,client_name").execute()
                        saved += 1
                    except Exception as e:
                        errors.append(f"{name}: {e}")
                if errors:
                    st.error(f"⚠️ Saved {saved}, errors:\n" + "\n".join(errors))
                else:
                    st.success(f"✅ UTR payments saved for {saved} employees — **{week_start.strftime('%d %b %Y')} → {week_end.strftime('%d %b %Y')}**")
                    st.balloons()

st.markdown("---")
st.subheader(f"📋 UTR Records — {week_start.strftime('%d %b %Y')} → {week_end.strftime('%d %b %Y')}")
try:
    q = supabase.table("weekly_records").select(
        "employee_name,client_name,hours_worked,utr_amount"
    ).eq("week_date", str(week_date)).gt("utr_amount", 0).order("employee_name").execute().data or []
    if q:
        df_q = pd.DataFrame(q)
        df_q.columns = ["Employee","Hotel","Hours","UTR £"]
        st.dataframe(df_q, use_container_width=True, hide_index=True)
        st.metric("Total UTR", f"£{df_q['UTR £'].sum():,.2f}")
    else:
        st.info("No UTR records yet for this week.")
except Exception as e:
    st.warning(f"Could not load: {e}")

st.markdown("---")
st.caption("📑 UTR Upload  •  ARVY Portal v1.0")
