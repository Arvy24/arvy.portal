import streamlit as st
import pandas as pd
from db import get_client, page_header
from datetime import date

st.set_page_config(page_title="Client Invoices", page_icon="🧾", layout="wide")
page_header("🧾 Client Invoices", "Upload and record weekly client invoice income")

supabase = get_client()

@st.cache_data(ttl=60)
def load_clients():
    return supabase.table("clients").select("id,name,dept_number").eq("is_active",True).order("name").execute().data or []
@st.cache_data(ttl=60)
def load_weeks():
    return supabase.table("weeks").select("*").order("week_ending",desc=True).execute().data or []

if st.sidebar.button("🔄 Refresh Data"):
    load_clients.clear(); load_weeks.clear(); st.rerun()

clients = load_clients()
weeks   = load_weeks()

if not clients or not weeks:
    st.error("⚠️ No hotels or weeks loaded. Check Supabase permissions.")
    st.stop()

st.sidebar.header("⚙️ Select Week")
week_options  = [w["week_ending"] for w in weeks]
selected_week = st.sidebar.selectbox("Week Ending", week_options)
week_id       = next(w["id"] for w in weeks if w["week_ending"] == selected_week)
st.sidebar.markdown("---")
st.sidebar.info(f"📅 Week: **{selected_week}**")

# ── Tabs ──────────────────────────────────────────────────────
tab_single, tab_bulk, tab_view = st.tabs([
    "➕ Add Single Invoice",
    "📤 Bulk Upload (Excel)",
    "📊 View This Week"
])

# ══════════════════════════════════════════════════════════════
# TAB 1 — ADD SINGLE INVOICE
# ══════════════════════════════════════════════════════════════
with tab_single:
    st.subheader("➕ Record a Single Client Invoice")
    st.caption("Use this to enter one invoice at a time for any hotel.")

    client_opts = {f"Dept {c['dept_number']} — {c['name']}" if c['dept_number'] else c['name']: c['id'] for c in clients}

    with st.form("single_invoice_form"):
        c1, c2 = st.columns(2)
        with c1:
            sel_client    = st.selectbox("🏨 Hotel / Client", list(client_opts.keys()))
            invoice_num   = st.text_input("Invoice Number", placeholder="e.g. INV-2026-001")
            invoice_date  = st.date_input("Invoice Date", value=date.today())
            hours_invoiced= st.number_input("Hours Invoiced", min_value=0.0, step=0.5, format="%.2f")
        with c2:
            amount_net    = st.number_input("Net Amount (£)", min_value=0.0, step=0.01, format="%.2f")
            vat_amount    = st.number_input("VAT Amount (£)", min_value=0.0, step=0.01, format="%.2f")
            amount_gross  = st.number_input("Gross Amount (£)", min_value=0.0, step=0.01, format="%.2f",
                                            help="Leave 0 to auto-calculate (Net + VAT)")
            notes         = st.text_area("Notes", placeholder="Optional")

        submitted = st.form_submit_button("💾 Save Invoice", type="primary")

    if submitted:
        client_id  = client_opts[sel_client]
        gross_val  = amount_gross if amount_gross > 0 else round(amount_net + vat_amount, 2)
        if amount_net == 0:
            st.error("Net Amount must be greater than 0.")
        else:
            try:
                supabase.table("client_invoices").insert({
                    "client_id":      client_id,
                    "week_id":        week_id,
                    "invoice_number": invoice_num or None,
                    "invoice_date":   str(invoice_date),
                    "hours_invoiced": hours_invoiced,
                    "amount_net":     amount_net,
                    "vat_amount":     vat_amount,
                    "amount_gross":   gross_val,
                    "notes":          notes or None,
                }).execute()
                supabase.table("upload_log").insert({
                    "upload_type": "invoice_single",
                    "week_id":     week_id,
                    "records_processed": 1,
                    "records_failed":    0,
                    "status":      "success",
                    "notes":       f"{sel_client} — {invoice_num}"
                }).execute()
                st.success(f"✅ Invoice saved for **{sel_client}** — £{amount_net:,.2f} net | Week {selected_week}")
                st.balloons()
            except Exception as e:
                st.error(f"Error saving invoice: {e}")

# ══════════════════════════════════════════════════════════════
# TAB 2 — BULK UPLOAD EXCEL
# ══════════════════════════════════════════════════════════════
with tab_bulk:
    st.subheader("📤 Bulk Upload Invoices from Excel")
    st.caption("Upload a spreadsheet with one row per hotel invoice.")

    # Download template
    template = pd.DataFrame({
        "hotel_name":      ["Royal National Hotel", "Tavistock Hotel"],
        "invoice_number":  ["INV-001", "INV-002"],
        "invoice_date":    ["2026-05-03", "2026-05-03"],
        "hours_invoiced":  [320.5, 180.0],
        "amount_net":      [5000.00, 2800.00],
        "vat_amount":      [1000.00, 560.00],
        "amount_gross":    [6000.00, 3360.00],
        "notes":           ["", ""],
    })
    st.download_button(
        "⬇ Download Invoice Template",
        template.to_csv(index=False).encode(),
        "ARVY_Invoice_Template.csv", "text/csv"
    )

    uploaded = st.file_uploader("Upload Excel file", type=["xlsx","xls","csv"])

    if uploaded:
        if uploaded.name.endswith(".csv"):
            df = pd.read_csv(uploaded, dtype=str).fillna("")
        else:
            xl    = pd.ExcelFile(uploaded)
            sheet = st.selectbox("Select Sheet", xl.sheet_names)
            c1,c2 = st.columns(2)
            with c1: header_row = st.number_input("Header row (0=first)", 0, 20, 0)
            with c2: skip_last  = st.number_input("Skip rows at bottom",  0, 10, 1)
            df = pd.read_excel(uploaded, sheet_name=sheet, header=int(header_row))
            df = df.dropna(how="all")
            if skip_last > 0: df = df.iloc[:-skip_last]
            df = df.reset_index(drop=True)

        st.dataframe(df.head(20), use_container_width=True)

        st.markdown("---")
        st.subheader("🗂️ Map Columns")
        cols = ["— not used —"] + list(df.columns.astype(str))
        c1,c2,c3 = st.columns(3)
        with c1:
            hotel_col   = st.selectbox("🏨 Hotel Name column", cols)
            inv_col     = st.selectbox("📋 Invoice Number",    cols)
            date_col    = st.selectbox("📅 Invoice Date",      cols)
        with c2:
            hours_col   = st.selectbox("⏱️ Hours Invoiced",    cols)
            net_col     = st.selectbox("💷 Net Amount",         cols)
        with c3:
            vat_col     = st.selectbox("📊 VAT Amount",         cols)
            gross_col   = st.selectbox("💰 Gross Amount",       cols)
            notes_col   = st.selectbox("📝 Notes (optional)",   cols)

        client_name_map = {c["name"].strip().lower(): c["id"] for c in clients}
        # also map short names
        for c in clients:
            if c.get("name"):
                client_name_map[c["name"].strip().lower()] = c["id"]

        if hotel_col != "— not used —" and net_col != "— not used —":
            def safe_float(v):
                try: return float(str(v).replace("£","").replace(",","").strip())
                except: return 0.0

            preview = []
            for _, row in df.iterrows():
                hotel_val = str(row[hotel_col]).strip() if pd.notna(row[hotel_col]) else ""
                if not hotel_val or hotel_val.lower() in ["nan","","hotel","client"]: continue
                cid   = client_name_map.get(hotel_val.lower())
                match = "✅ Found" if cid else "❌ Not Found"
                net   = safe_float(row[net_col]) if net_col != "— not used —" else 0
                vat   = safe_float(row[vat_col]) if vat_col != "— not used —" else 0
                gross = safe_float(row[gross_col]) if gross_col != "— not used —" else round(net+vat,2)
                preview.append({
                    "Hotel":         hotel_val,
                    "Invoice No":    str(row[inv_col])  if inv_col  !="— not used —" and pd.notna(row.get(inv_col))  else "",
                    "Date":          str(row[date_col]) if date_col !="— not used —" and pd.notna(row.get(date_col)) else str(date.today()),
                    "Hours":         safe_float(row[hours_col]) if hours_col!="— not used —" else 0,
                    "Net (£)":       net,
                    "VAT (£)":       vat,
                    "Gross (£)":     gross,
                    "Notes":         str(row[notes_col]) if notes_col!="— not used —" and pd.notna(row.get(notes_col)) else "",
                    "Match":         match,
                    "_client_id":    cid,
                })

            if preview:
                st.markdown("---")
                disp = pd.DataFrame([{k:v for k,v in r.items() if k!="_client_id"} for r in preview])
                st.dataframe(disp, use_container_width=True)

                matched   = sum(1 for r in preview if "✅" in r["Match"])
                unmatched = sum(1 for r in preview if "❌" in r["Match"])
                c1,c2,c3  = st.columns(3)
                c1.metric("Total", len(preview))
                c2.metric("✅ Matched", matched)
                c3.metric("❌ Not Found", unmatched)

                total_net = sum(r["Net (£)"] for r in preview)
                st.info(f"📊 Total Net Income: **£{total_net:,.2f}** | Matched: **{matched}** hotels")

                if unmatched:
                    st.warning(f"⚠️ {unmatched} hotel(s) not matched — will be skipped.")

                if matched > 0:
                    if st.button("💾 Save All Invoices", type="primary"):
                        saved=0; errors=[]
                        for r in preview:
                            if "❌" in r["Match"]: continue
                            try:
                                supabase.table("client_invoices").insert({
                                    "client_id":      r["_client_id"],
                                    "week_id":        week_id,
                                    "invoice_number": r["Invoice No"] or None,
                                    "invoice_date":   r["Date"],
                                    "hours_invoiced": r["Hours"],
                                    "amount_net":     r["Net (£)"],
                                    "vat_amount":     r["VAT (£)"],
                                    "amount_gross":   r["Gross (£)"],
                                    "notes":          r["Notes"] or None,
                                    "source_file":    uploaded.name,
                                }).execute()
                                saved += 1
                            except Exception as e:
                                errors.append(f"{r['Hotel']}: {e}")

                        supabase.table("upload_log").insert({
                            "upload_type":"invoice_bulk","filename":uploaded.name,
                            "week_id":week_id,"records_processed":saved,
                            "records_failed":len(errors),
                            "status":"success" if not errors else "partial",
                            "error_log":{"errors":errors} if errors else None
                        }).execute()

                        if errors:
                            st.error(f"⚠️ Saved {saved} with {len(errors)} error(s):\n"+"\n".join(errors))
                        else:
                            st.success(f"✅ Saved {saved} invoices — Week {selected_week}!")
                        st.balloons()

# ══════════════════════════════════════════════════════════════
# TAB 3 — VIEW THIS WEEK
# ══════════════════════════════════════════════════════════════
with tab_view:
    st.subheader(f"📊 Invoices — Week ending {selected_week}")
    try:
        res = supabase.table("client_invoices").select(
            "invoice_number, invoice_date, hours_invoiced, amount_net, vat_amount, amount_gross, notes, clients(name, dept_number)"
        ).eq("week_id", week_id).order("created_at").execute()

        if res.data:
            rows = []
            for r in res.data:
                c = r.get("clients", {}) or {}
                rows.append({
                    "Hotel":       c.get("name","—"),
                    "Dept":        c.get("dept_number","—"),
                    "Invoice No":  r["invoice_number"],
                    "Date":        r["invoice_date"],
                    "Hours":       r["hours_invoiced"],
                    "Net (£)":     r["amount_net"],
                    "VAT (£)":     r["vat_amount"],
                    "Gross (£)":   r["amount_gross"],
                    "Notes":       r["notes"],
                })
            df_view = pd.DataFrame(rows)
            st.dataframe(df_view, use_container_width=True, hide_index=True)

            total_net   = sum(r["Net (£)"]   for r in rows)
            total_gross = sum(r["Gross (£)"] for r in rows)
            c1,c2,c3 = st.columns(3)
            c1.metric("Invoices",      len(rows))
            c2.metric("Total Net",    f"£{total_net:,.2f}")
            c3.metric("Total Gross",  f"£{total_gross:,.2f}")
        else:
            st.info("No invoices recorded for this week yet.")
    except Exception as e:
        st.error(f"Error loading invoices: {e}")
