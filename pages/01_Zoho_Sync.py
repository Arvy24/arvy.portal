import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
from db import get_client, page_header

st.set_page_config(page_title="Zoho Sync", page_icon="🔄", layout="wide")
page_header("🔄 Zoho Books Sync", "Pull invoices, bills and expenses from Zoho Books into ARVY Portal")

supabase = get_client()

# ── Credentials ───────────────────────────────────────────────────────────────
CLIENT_ID     = "1000.GSW0VNVRO1JTNIWGLL9VMTUIK9FK1M"
CLIENT_SECRET = "65462c0bc2c2504afd4626aeb2c6dfd66125870734"
TOKEN_URL     = "https://accounts.zoho.eu/oauth/v2/token"
API_BASE     = https://www.zohoapis.eu/books/v3

try:
    REFRESH_TOKEN = st.secrets["ZOHO_REFRESH_TOKEN"]
except KeyError:
    st.error("❌ ZOHO_REFRESH_TOKEN not found in Streamlit secrets. Please complete Zoho Connect first.")
    st.stop()

try:
    ORG_ID = st.secrets["ZOHO_ORG_ID"]
except KeyError:
    ORG_ID = None

# ── Get access token ──────────────────────────────────────────────────────────
def get_access_token():
    resp = requests.post(TOKEN_URL, data={
        "grant_type":    "refresh_token",
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
    })
    return resp.json()

def zoho_headers(token):
    return {"Authorization": f"Zoho-oauthtoken {token}"}

# ── Test connection ───────────────────────────────────────────────────────────
st.subheader("🔌 Connection Status")
col_test, col_refresh = st.columns([1, 1])

with col_test:
    if st.button("🧪 Test Zoho Connection", use_container_width=True):
        with st.spinner("Testing..."):
            token_data = get_access_token()
            if "access_token" not in token_data:
                st.error(f"❌ Token failed: {token_data}")
            else:
                access_token = token_data["access_token"]
                st.success(f"✅ Access token OK")

                # Try to get orgs
                org_resp = requests.get(
                    f"{API_BASE}/organizations",
                    headers=zoho_headers(access_token)
                )
                org_data = org_resp.json()
                orgs = org_data.get("organizations", [])

                if orgs:
                    for o in orgs:
                        st.info(f"🏢 **{o.get('name')}** — Org ID: `{o.get('organization_id')}`")
                        if not ORG_ID:
                            st.warning("⚠️ ZOHO_ORG_ID not in secrets. Add it and redeploy.")
                else:
                    st.error(f"No orgs found: {org_data}")

with col_refresh:
    if st.button("🗑️ Clear Token Cache", use_container_width=True):
        for key in list(st.session_state.keys()):
            if "token" in key.lower() or "zoho" in key.lower():
                del st.session_state[key]
        st.cache_data.clear()
        st.rerun()

st.markdown("---")

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.header("⚙️ Sync Options")
date_range    = st.sidebar.selectbox("Date Range", ["Last 30 days", "Last 90 days", "Last 6 months", "This financial year", "All time"])
sync_invoices = st.sidebar.checkbox("📄 Invoices", value=True)
sync_bills    = st.sidebar.checkbox("🧾 Bills",    value=True)
sync_expenses = st.sidebar.checkbox("💳 Expenses", value=True)
show_debug    = st.sidebar.checkbox("🐛 Show debug output", value=False)
st.sidebar.markdown("---")

today = datetime.today().date()
if date_range == "Last 30 days":
    from_date = today - timedelta(days=30)
elif date_range == "Last 90 days":
    from_date = today - timedelta(days=90)
elif date_range == "Last 6 months":
    from_date = today - timedelta(days=183)
elif date_range == "This financial year":
    fy_start = datetime(today.year, 4, 6).date()
    if today < fy_start:
        fy_start = datetime(today.year - 1, 4, 6).date()
    from_date = fy_start
else:
    from_date = None

# ── Sync ──────────────────────────────────────────────────────────────────────
st.subheader("🔄 Run Sync")
if not ORG_ID:
    st.warning("⚠️ ZOHO_ORG_ID is missing from secrets. Run the Test above to find your Org ID, then add it to secrets.")

run_sync = st.button("🔄 Sync Now from Zoho Books", type="primary", use_container_width=True)

if run_sync:
    if not ORG_ID:
        st.error("Cannot sync without ZOHO_ORG_ID. Add it to your Streamlit secrets first.")
        st.stop()

    # Get token
    token_data = get_access_token()
    if "access_token" not in token_data:
        st.error(f"❌ Could not get access token: {token_data}")
        st.stop()
    access_token = token_data["access_token"]
    st.success("✅ Token obtained")

    def fetch_all(endpoint, key):
        """Pull ALL records from Zoho (no date filter in API — we filter locally after)."""
        items, page = [], 1
        while True:
            params = {"organization_id": ORG_ID, "page": page, "per_page": 200}
            r = requests.get(f"{API_BASE}/{endpoint}", headers=zoho_headers(access_token), params=params)
            if show_debug:
                st.caption(f"GET {endpoint} page {page} → {r.status_code}")
                st.json(r.json())
            data = r.json()
            if r.status_code != 200:
                st.error(f"Zoho API error on {endpoint} (HTTP {r.status_code}): {data}")
                return None
            if data.get("code", 0) != 0:
                st.error(f"Zoho API error on {endpoint}: {data.get('message', data)}")
                return None
            batch = data.get(key, [])
            items.extend(batch)
            if not data.get("page_context", {}).get("has_more_page", False):
                break
            page += 1
        return items

    def filter_by_date(records, date_field="date"):
        """Filter records locally after fetching from Zoho."""
        if not from_date:
            return records
        filtered = []
        for r in records:
            d = r.get(date_field, "")
            if d and d >= str(from_date):
                filtered.append(r)
        return filtered

    results = {}

    # ── Invoices ──────────────────────────────────────────────────────────────
    if sync_invoices:
        with st.spinner("Fetching invoices..."):
            invoices_raw = fetch_all("invoices", "invoices")
            invoices = filter_by_date(invoices_raw) if invoices_raw is not None else None
            if invoices is not None:
                rows = []
                for inv in invoices:
                    rows.append({
                        "zoho_invoice_id": inv.get("invoice_id", ""),
                        "invoice_number":  inv.get("invoice_number", ""),
                        "client_name":     inv.get("customer_name", ""),
                        "date":            inv.get("date") or None,
                        "due_date":        inv.get("due_date") or None,
                        "status":          inv.get("status", ""),
                        "total":           float(inv.get("total", 0) or 0),
                        "balance":         float(inv.get("balance", 0) or 0),
                        "currency_code":   inv.get("currency_code", "GBP"),
                    })
                if rows:
                    try:
                        supabase.table("zoho_invoices").upsert(rows, on_conflict="zoho_invoice_id").execute()
                        st.success(f"✅ {len(rows)} invoices synced to Supabase")
                        results["Invoices"] = len(rows)
                    except Exception as e:
                        st.error(f"❌ Supabase error saving invoices: {e}")
                        st.info("👉 Have you created the zoho_invoices table? Run the SQL from the setup instructions.")
                else:
                    st.info("No invoices found in Zoho for selected date range.")

    # ── Bills ─────────────────────────────────────────────────────────────────
    if sync_bills:
        with st.spinner("Fetching bills..."):
            bills_raw = fetch_all("bills", "bills")
            bills = filter_by_date(bills_raw) if bills_raw is not None else None
            if bills is not None:
                rows = []
                for b in bills:
                    rows.append({
                        "zoho_bill_id": b.get("bill_id", ""),
                        "bill_number":  b.get("bill_number", ""),
                        "vendor_name":  b.get("vendor_name", ""),
                        "date":         b.get("date") or None,
                        "due_date":     b.get("due_date") or None,
                        "status":       b.get("status", ""),
                        "total":        float(b.get("total", 0) or 0),
                        "balance":      float(b.get("balance", 0) or 0),
                        "currency_code": b.get("currency_code", "GBP"),
                    })
                if rows:
                    try:
                        supabase.table("zoho_bills").upsert(rows, on_conflict="zoho_bill_id").execute()
                        st.success(f"✅ {len(rows)} bills synced to Supabase")
                        results["Bills"] = len(rows)
                    except Exception as e:
                        st.error(f"❌ Supabase error saving bills: {e}")
                        st.info("👉 Have you created the zoho_bills table? Run the SQL from the setup instructions.")
                else:
                    st.info("No bills found in Zoho for selected date range.")

    # ── Expenses ──────────────────────────────────────────────────────────────
    if sync_expenses:
        with st.spinner("Fetching expenses..."):
            exps_raw = fetch_all("expenses", "expenses")
            exps = filter_by_date(exps_raw) if exps_raw is not None else None
            if exps is not None:
                rows = []
                for exp in exps:
                    rows.append({
                        "zoho_expense_id": exp.get("expense_id", ""),
                        "date":            exp.get("date") or None,
                        "account_name":    exp.get("account_name", ""),
                        "description":     exp.get("description", ""),
                        "vendor_name":     exp.get("vendor_name", ""),
                        "total":           float(exp.get("total", 0) or 0),
                        "status":          exp.get("status", ""),
                        "currency_code":   exp.get("currency_code", "GBP"),
                    })
                if rows:
                    try:
                        supabase.table("zoho_expenses").upsert(rows, on_conflict="zoho_expense_id").execute()
                        st.success(f"✅ {len(rows)} expenses synced to Supabase")
                        results["Expenses"] = len(rows)
                    except Exception as e:
                        st.error(f"❌ Supabase error saving expenses: {e}")
                        st.info("👉 Have you created the zoho_expenses table? Run the SQL from the setup instructions.")
                else:
                    st.info("No expenses found in Zoho for selected date range.")

    if results:
        st.markdown("---")
        st.subheader("✅ Sync Complete")
        for k, v in results.items():
            st.markdown(f"- **{k}:** {v} records")
        st.caption(f"Synced at {datetime.now().strftime('%d %b %Y %H:%M')}")

# ── Preview ───────────────────────────────────────────────────────────────────
st.markdown("---")
st.subheader("📋 Synced Data Preview")
tab_inv, tab_bills, tab_exp = st.tabs(["📄 Invoices", "🧾 Bills", "💳 Expenses"])

with tab_inv:
    try:
        data = supabase.table("zoho_invoices").select("*").order("date", desc=True).limit(200).execute().data or []
        if data:
            df = pd.DataFrame(data)
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Invoices", len(df))
            c2.metric("Total Value", f"£{df['total'].sum():,.2f}")
            c3.metric("Outstanding", f"£{df[df['status'] != 'paid']['balance'].sum():,.2f}")
            st.dataframe(df[["invoice_number","client_name","date","due_date","total","balance","status"]], use_container_width=True, hide_index=True)
        else:
            st.info("No invoices yet. Click Sync Now above.")
    except Exception as e:
        st.warning(f"Table not ready: {e}")

with tab_bills:
    try:
        data = supabase.table("zoho_bills").select("*").order("date", desc=True).limit(200).execute().data or []
        if data:
            df = pd.DataFrame(data)
            c1, c2 = st.columns(2)
            c1.metric("Total Bills", len(df))
            c2.metric("Total Value", f"£{df['total'].sum():,.2f}")
            st.dataframe(df[["bill_number","vendor_name","date","due_date","total","balance","status"]], use_container_width=True, hide_index=True)
        else:
            st.info("No bills yet. Click Sync Now above.")
    except Exception as e:
        st.warning(f"Table not ready: {e}")

with tab_exp:
    try:
        data = supabase.table("zoho_expenses").select("*").order("date", desc=True).limit(200).execute().data or []
        if data:
            df = pd.DataFrame(data)
            c1, c2 = st.columns(2)
            c1.metric("Total Expenses", len(df))
            c2.metric("Total Value", f"£{df['total'].sum():,.2f}")
            st.dataframe(df[["date","account_name","vendor_name","description","total","status"]], use_container_width=True, hide_index=True)
        else:
            st.info("No expenses yet. Click Sync Now above.")
    except Exception as e:
        st.warning(f"Table not ready: {e}")

st.markdown("---")
st.caption("🔄 Zoho Books EU  •  ARVY Portal v1.0")
