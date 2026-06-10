import streamlit as st
import pandas as pd
from datetime import date, timedelta
from db import get_client, page_header

st.set_page_config(page_title="UTR Upload", page_icon="📑", layout="wide")
page_header("📑 UTR Upload", "Upload UTR payments — matched to timesheet employees by name")

supabase = get_client()

@st.cache_data(ttl=60)
def load_clients():
    return supabase.table("clients").select("id,name").eq("is_active", True).order("name").execute().data or []

if st.sidebar.button("🔄 Refresh"):
    load_clients.clear(); st.rerun()

clients = load_clients()
if not clients:
    st.error("⚠️ No hotels found.")
    st.stop()

st.sidebar.header("⚙️ Select Week")
week_date = st.sidebar.date_input(
    "📅 Week Date",
    value=date.today() - timedelta(days=date.today().weekday()),
)
client_names    = [c["name"] for c in clients]
selected_client = st.sidebar.selectbox("🏨 Hotel (optional)", ["All Hotels"] + client_names)
st.sidebar.markdown("---")

@st.cache_data(ttl=30)
def load_week_records(wd):
    return supabase.table("weekly_records").select("id,employee_name,client_name,hours_worked,utr_amount")\
        .eq("week_date", str(wd)).execute().data or []

week_recs   = load_week_records(week_date)
name_lookup = {r["employee_name"].strip().lower(): r for r in week_recs}

if week_recs:
    st.info(f"📋 Found **{len(week_recs)}** timesheet records for week **{week_date}**")
else:
    st.warning(f"⚠️ No timesheet records for week **{week_date}**. Upload timesheets first.")

st.markdown("---")
st.subheader("📂 Upload UTR Excel")
st.caption("Excel must have: **Employee Name** and **Amount** columns")

uploaded = st.file_uploader("Upload Excel file", type=["xlsx", "xls", "csv"])

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
    c1, c2 = st.columns(2)
    with c1:
        name_col   = st.selectbox("👤 Employee Name column", cols)
    with c2:
        amount_col = st.selectbox("💰 UTR Amount column", cols)

    if name_col != "— not used —" and amount_col != "— not used —":
        st.markdown("---")
        st.subheader("🔍 Preview & Match")

        def safe_float(v):
            try:
                return float(str(v).replace("£","").replace(",","").strip())
            except:
                return 0.0

        skip_words = {"nan","","name","employee","total","grand total","employee name"}
        rows = []
        for _, row in df.iterrows():
            name = str(row[name_col]).strip() if pd.notna(row[name_col]) else ""
            if name.lower() in skip_words or not name:
                continue
            amount = safe_float(row.get(amount_col, 0))
            if amount == 0:
                continue
            matched = name.strip().lower() in name_lookup
            rows.append({
                "Employee Name": name,
                "UTR Amount £": amount,
                "Match": "✅ Matched" if matched else "🆕 New",
            })

        if rows:
            preview_df = pd.DataFrame(rows)
            st.dataframe(preview_df, use_container_width=True, hide_index=True)

            matched_n = sum(1 for r in rows if "✅" in r["Match"])
            new_n     = sum(1 for r in rows if "🆕" in r["Match"])
            c1,c2,c3  = st.columns(3)
            c1.metric("✅ Matched", matched_n)
            c2.metric("🆕 New", new_n)
            c3.metric("Total UTR", f"£{sum(r['UTR Amount £'] for r in rows):,.2f}")

            if new_n:
                st.warning(f"⚠️ {new_n} employee(s) not in timesheets — saved with 0 hours.")

            if st.button("💾 Save UTR Payments", type="primary", use_container_width=True):
                saved = 0; errors = []
                for r in rows:
                    name = r["Employee Name"]
                    try:
                        rec = name_lookup.get(name.strip().lower())
                        if rec:
                            supabase.table("weekly_records").update({
                                "utr_amount": r["UTR Amount £"]
                            }).eq("id", rec["id"]).execute()
                        else:
                            client = selected_client if selected_client != "All Hotels" else "Unknown"
                            supabase.table("weekly_records").upsert({
                                "week_date":     str(week_date),
                                "employee_name": name,
                                "client_name":   client,
                                "hours_worked":  0,
                                "utr_amount":    r["UTR Amount £"],
                            }, on_conflict="week_date,employee_name,client_name").execute()
                        saved += 1
                    except Exception as e:
                        errors.append(f"{name}: {e}")

                load_week_records.clear()
                if errors:
                    st.error(f"⚠️ Saved {saved}, errors:\n" + "\n".join(errors))
                else:
                    st.success(f"✅ UTR payments saved for {saved} employees — Week **{week_date}**")
                    st.balloons()
        else:
            st.warning("No valid rows found. Check column mapping.")

st.markdown("---")
st.subheader(f"📋 UTR Records — Week {week_date}")
try:
    q = supabase.table("weekly_records").select("employee_name,client_name,hours_worked,utr_amount")\
        .eq("week_date", str(week_date)).gt("utr_amount", 0).order("employee_name").execute().data or []
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
