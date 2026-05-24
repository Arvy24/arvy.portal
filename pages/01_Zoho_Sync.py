import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
from db import get_client, page_header

st.set_page_config(page_title="Zoho Sync", page_icon="🔄", layout="wide")
page_header("🔄 Zoho Books Sync", "Pull invoices, bills and expenses from Zoho Books into ARVY Portal")

supabase = get_client()

# ── Zoho credentials from secrets ────────────────────────────────────────────
try:
    REFRESH_TOKEN = st.secrets["ZOHO_REFRESH_TOKEN"]
    ORG_ID        = st.secrets["ZOHO_ORG_ID"]
    CLIENT_ID     = st.secrets["ZOHO_CLIENT_ID"]        if "ZOHO_CLIENT_ID"     in st.secrets else "1000.GSW0VNVRO1JTNIWGLL9VMTUIK9FK1M"
    CLIENT_SECRET = st.secrets["ZOHO_CLIENT_SECRET"]    if "ZOHO_CLIENT_SECRET" in st.secrets else "65462c0bc2c2504afd4626aeb2c6dfd66125870734"
except KeyError as e:
    st.error(f"Missing secret: {e}. Please complete the Zoho Connect step first.")
    st.stop()

TOKEN_URL = "https://accounts.zoho.eu/oauth/v2/token"
API_BASE  = f"https://books.zoho.eu/api/v3"

# ── Get fresh access token ────────────────────────────────────────────────────
@st.cache_data(ttl=3000)   # Zoho access tokens live ~60 min; refresh every 50 min
def get_access_token():
    resp = requests.post(TOKEN_URL, data={
        "grant_type":    "refresh_token",
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
    })
    data = resp.json()
    if "access_token" not in data:
        st.error(f"Could not refresh Zoho token: {data}")
        st.stop()
    return data["access_token"]

def zoho_headers(token):
    return {
        "Authorization": f"Zoho-oauthtoken {token}",
        "Content-Type":  "application/json",
    }

def zoho_get_all(endpoint, key, token, extra_params=None):
    """Page through Zoho API and return all records."""
    items = []
    page  = 1
    while True:
        params = {"organization_id": ORG_ID, "page": page, "per_page": 200}
        if extra_params:
            params.update(extra_params)
        r = requests.get(f"{API_BASE}/{endpoint}", headers=zoho_headers(token), params=params)
        data = r.json()
        batch = data.get(key, [])
        items.extend(batch)
        if not data.get("page_context", {}).get("has_more_page", False):
            break
        page += 1
    return items

# ── Sidebar controls ──────────────────────────────────────────────────────────
st.sidebar.header("⚙️ Sync Options")
date_range = st.sidebar.selectbox("Date Range", ["Last 30 days", "Last 90 days", "Last 6 months", "This financial year", "All time"])
sync_invoices = st.sidebar.checkbox("📄 Invoices (Income)",   value=True)
sync_bills    = st.sidebar.checkbox("🧾 Bills (Supplier)",    value=True)
sync_expenses = st.sidebar.checkbox("💳 Expenses",            value=True)
st.sidebar.markdown("---")

# Convert date range to filter dates
today = datetime.today().date()
if date_range == "Last 30 days":
    from_date = today - timedelta(days=30)
elif date_range == "Last 90 days":
    from_date = today - timedelta(days=90)
elif date_range == "Last 6 months":
    from_date = today - timedelta(days=183)
elif date_range == "This financial year":
    # UK financial year: April 6
    fy_start = datetime(today.year, 4, 6).date()
    if today < fy_start:
        fy_start = datetime(today.year - 1, 4, 6).date()
    from_date = fy_start
else:
    from_date = None  # All time

date_filter = {"date_start": str(from_date)} if from_date else {}

# ── Sync button ───────────────────────────────────────────────────────────────
col1, col2 = st.columns([2, 1])
with col1:
    run_sync = st.button("🔄 Sync Now from Zoho Books", type="primary", use_container_width=True)
with col2:
    if st.button("🔁 Force Token Refresh"):
        get_access_token.clear()
        st.rerun()

st.markdown("---")

# ── Status display ────────────────────────────────────────────────────────────
status = st.empty()

if run_sync:
    token = get_access_token()
    results = {}

    # ── 1. INVOICES ───────────────────────────────────────────────────────────
    if sync_invoices:
        with st.spinner("Fetching invoices from Zoho Books..."):
            try:
                invoices = zoho_get_all("invoices", "invoices", token, date_filter)
                rows = []
                for inv in invoices:
                    rows.append({
                        "zoho_invoice_id": inv.get("invoice_id", ""),
                        "invoice_number":  inv.get("invoice_number", ""),
                        "client_name":     inv.get("customer_name", ""),
                        "date":            inv.get("date", ""),
                        "due_date":        inv.get("due_date", ""),
                        "status":          inv.get("status", ""),
                        "total":           float(inv.get("total", 0)),
                        "balance":         float(inv.get("balance", 0)),
                        "currency_code":   inv.get("currency_code", "GBP"),
                    })

                if rows:
                    # Upsert into Supabase (create table if not exists)
                    supabase.table("zoho_invoices").upsert(rows, on_conflict="zoho_invoice_id").execute()
                    results["Invoices"] = {"count": len(rows), "status": "✅"}
                    st.success(f"✅ {len(rows)} invoices synced")
                else:
                    results["Invoices"] = {"count": 0, "status": "⚠️ None found"}
                    st.info("No invoices found for the selected date range.")
            except Exception as e:
                results["Invoices"] = {"count": 0, "status": f"❌ {e}"}
                st.error(f"Invoice sync failed: {e}")

    # ── 2. BILLS ─────────────────────────────────────────────────────────────
    if sync_bills:
        with st.spinner("Fetching bills from Zoho Books..."):
            try:
                bills = zoho_get_all("bills", "bills", token, date_filter)
                rows = []
                for bill in bills:
                    rows.append({
                        "zoho_bill_id":  bill.get("bill_id", ""),
                        "bill_number":   bill.get("bill_number", ""),
                        "vendor_name":   bill.get("vendor_name", ""),
                        "date":          bill.get("date", ""),
                        "due_date":      bill.get("due_date", ""),
                        "status":        bill.get("status", ""),
                        "total":         float(bill.get("total", 0)),
                        "balance":       float(bill.get("balance", 0)),
                        "currency_code": bill.get("currency_code", "GBP"),
                    })

                if rows:
                    supabase.table("zoho_bills").upsert(rows, on_conflict="zoho_bill_id").execute()
                    results["Bills"] = {"count": len(rows), "status": "✅"}
                    st.success(f"✅ {len(rows)} bills synced")
                else:
                    results["Bills"] = {"count": 0, "status": "⚠️ None found"}
                    st.info("No bills found for the selected date range.")
            except Exception as e:
                results["Bills"] = {"count": 0, "status": f"❌ {e}"}
                st.error(f"Bill sync failed: {e}")

    # ── 3. EXPENSES ───────────────────────────────────────────────────────────
    if sync_expenses:
        with st.spinner("Fetching expenses from Zoho Books..."):
            try:
                exps = zoho_get_all("expenses", "expenses", token, date_filter)
                rows = []
                for exp in exps:
                    rows.append({
                        "zoho_expense_id": exp.get("expense_id", ""),
                        "date":            exp.get("date", ""),
                        "account_name":    exp.get("account_name", ""),
                        "description":     exp.get("description", ""),
                        "vendor_name":     exp.get("vendor_name", ""),
                        "total":           float(exp.get("total", 0)),
                        "status":          exp.get("status", ""),
                        "currency_code":   exp.get("currency_code", "GBP"),
                    })

                if rows:
                    supabase.table("zoho_expenses").upsert(rows, on_conflict="zoho_expense_id").execute()
                    results["Expenses"] = {"count": len(rows), "status": "✅"}
                    st.success(f"✅ {len(rows)} expenses synced")
                else:
                    results["Expenses"] = {"count": 0, "status": "⚠️ None found"}
                    st.info("No expenses found for the selected date range.")
            except Exception as e:
                results["Expenses"] = {"count": 0, "status": f"❌ {e}"}
                st.error(f"Expense sync failed: {e}")

    # ── Summary ───────────────────────────────────────────────────────────────
    if results:
        st.markdown("---")
        st.subheader("📊 Sync Summary")
        summary_df = pd.DataFrame([
            {"Type": k, "Records": v["count"], "Status": v["status"]}
            for k, v in results.items()
        ])
        st.dataframe(summary_df, use_container_width=True, hide_index=True)
        st.caption(f"Last synced: {datetime.now().strftime('%d %b %Y at %H:%M')}")

# ── Preview synced data ───────────────────────────────────────────────────────
st.markdown("---")
st.subheader("📋 Synced Data Preview")

tab_inv, tab_bills, tab_exp = st.tabs(["📄 Invoices", "🧾 Bills", "💳 Expenses"])

with tab_inv:
    try:
        inv_data = supabase.table("zoho_invoices").select("*").order("date", desc=True).limit(100).execute().data
        if inv_data:
            df_inv = pd.DataFrame(inv_data)
            total_income = df_inv["total"].sum()
            outstanding  = df_inv[df_inv["status"] != "paid"]["balance"].sum()
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Invoices", len(df_inv))
            c2.metric("Total Value", f"£{total_income:,.2f}")
            c3.metric("Outstanding", f"£{outstanding:,.2f}")
            st.dataframe(df_inv[["invoice_number","client_name","date","due_date","total","balance","status"]],
                         use_container_width=True, hide_index=True)
        else:
            st.info("No invoices synced yet. Click **Sync Now** above.")
    except Exception as e:
        st.warning(f"Could not load invoices — table may not exist yet. Run a sync first. ({e})")

with tab_bills:
    try:
        bill_data = supabase.table("zoho_bills").select("*").order("date", desc=True).limit(100).execute().data
        if bill_data:
            df_bills = pd.DataFrame(bill_data)
            total_bills = df_bills["total"].sum()
            c1, c2 = st.columns(2)
            c1.metric("Total Bills", len(df_bills))
            c2.metric("Total Value", f"£{total_bills:,.2f}")
            st.dataframe(df_bills[["bill_number","vendor_name","date","due_date","total","balance","status"]],
                         use_container_width=True, hide_index=True)
        else:
            st.info("No bills synced yet. Click **Sync Now** above.")
    except Exception as e:
        st.warning(f"Could not load bills — table may not exist yet. Run a sync first. ({e})")

with tab_exp:
    try:
        exp_data = supabase.table("zoho_expenses").select("*").order("date", desc=True).limit(100).execute().data
        if exp_data:
            df_exp = pd.DataFrame(exp_data)
            total_exp = df_exp["total"].sum()
            c1, c2 = st.columns(2)
            c1.metric("Total Expenses", len(df_exp))
            c2.metric("Total Value", f"£{total_exp:,.2f}")
            st.dataframe(df_exp[["date","account_name","vendor_name","description","total","status"]],
                         use_container_width=True, hide_index=True)
        else:
            st.info("No expenses synced yet. Click **Sync Now** above.")
    except Exception as e:
        st.warning(f"Could not load expenses — table may not exist yet. Run a sync first. ({e})")

st.markdown("---")
st.caption("🔄 Data pulled live from Zoho Books EU  •  ARVY Portal v1.0")
