import streamlit as st
import pandas as pd
from db import get_client, page_header
from datetime import date

st.set_page_config(page_title="Supplier Expenses", page_icon="🧾", layout="wide")
page_header("🧾 Supplier Expenses", "Record and upload non-payroll expenses per hotel")

supabase = get_client()

@st.cache_data(ttl=60)
def load_clients():
    return supabase.table("clients").select("id,name,dept_number").eq("is_active", True).order("name").execute().data or []

@st.cache_data(ttl=60)
def load_weeks():
    return supabase.table("weeks").select("*").order("week_ending", desc=True).execute().data or []

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

CATEGORIES = [
    "Cleaning Supplies",
    "Equipment & Maintenance",
    "Uniform & PPE",
    "Travel & Transport",
    "Office & Admin",
    "Food & Beverages",
    "Subcontractor",
    "Software & Subscriptions",
    "Insurance",
    "Other",
]

tab_single, tab_bulk, tab_view = st.tabs([
    "➕ Add Single Expense",
    "📤 Bulk Upload (Excel)",
    "📊 View This Week",
])

# TAB 1 — ADD SINGLE EXPENSE
with tab_single:
    st.subheader("➕ Add a Single Expense")

    client_opts = {"Company-Wide (No Hotel)": None}
    for c in clients:
        label = f"Dept {c['dept_number']} — {c['name']}" if c.get("dept_number") else c["name"]
        client_opts[label] = c["id"]

    with st.form("single_expense_form"):
        c1, c2 = st.columns(2)
        with c1:
            sel_client  = st.selectbox("🏨 Hotel (or Company-Wide)", list(client_opts.keys()))
            category    = st.selectbox("📂 Category", CATEGORIES)
            description = st.text_input("Description", placeholder="e.g. Cleaning chemicals — Royal Hotel")
        with c2:
            amount      = st.number_input("Amount (£)", min_value=0.0, step=0.01, format="%.2f")
            supplier    = st.text_input("Supplier Name", placeholder="e.g. Bunzl, Amazon, etc.")
            notes       = st.text_area("Notes", placeholder="Optional")

        submitted = st.form_submit_button("💾 Save Expense", type="primary")

    if submitted:
        if amount == 0:
            st.error("Amount must be greater than £0.")
        elif not description:
            st.error("Please enter a description.")
        else:
            try:
                client_id = client_opts[sel_client]
                full_desc = f"{supplier} — {description}" if supplier else description
                supabase.table("expenses").insert({
                    "client_id":  client_id,
                    "week_id":    week_id,
                    "category":   category,
                    "description":full_desc,
                    "amount":     amount,
                    "notes":      notes or None,
                }).execute()
                supabase.table("upload_log").insert({
                    "upload_type": "expense_single",
                    "week_id":     week_id,
                    "records_processed": 1,
                    "records_failed":    0,
                    "status":      "success",
                    "notes":       f"{category} — £{amount:.2f}"
                }).execute()
                st.success(f"✅ Expense saved — **{category}** £{amount:,.2f} for **{sel_client}** — Week {selected_week}")
                st.balloons()
            except Exception as e:
                st.error(f"Error saving expense: {e}")

# TAB 2 — BULK UPLOAD
with tab_bulk:
    st.subheader("📤 Bulk Upload Expenses from Excel")
    st.caption("Upload a spreadsheet with one row per expense line.")

    template = pd.DataFrame({
        "hotel_name":  ["Royal National Hotel", "Company-Wide", "Tavistock Hotel"],
        "category":    ["Cleaning Supplies", "Software & Subscriptions", "Equipment & Maintenance"],
        "description": ["Cleaning chemicals", "Xero subscription", "Vacuum repair"],
        "supplier":    ["Bunzl", "Xero Ltd", "Dyson Service"],
        "amount":      [250.00, 45.00, 120.00],
        "notes":       ["", "Monthly", ""],
    })
    st.download_button(
        "⬇ Download Expense Template",
        template.to_csv(index=False).encode(),
        "ARVY_Expense_Template.csv", "text/csv"
    )

    uploaded = st.file_uploader("Upload Excel or CSV file", type=["xlsx","xls","csv"])

    if uploaded:
        if uploaded.name.endswith(".csv"):
            df = pd.read_csv(uploaded, dtype=str).fillna("")
        else:
            xl    = pd.ExcelFile(uploaded)
            sheet = st.selectbox("Select Sheet", xl.sheet_names)
            c1, c2 = st.columns(2)
            with c1: header_row = st.number_input("Header row (0=first)", 0, 20, 0)
            with c2: skip_last  = st.number_input("Skip rows at bottom",  0, 10, 0)
            df = pd.read_excel(uploaded, sheet_name=sheet, header=int(header_row))
            df = df.dropna(how="all")
            if skip_last > 0: df = df.iloc[:-skip_last]
            df = df.reset_index(drop=True)

        st.dataframe(df.head(20), use_container_width=True)
        st.markdown("---")
        st.subheader("🗂️ Map Columns")
        cols = ["— not used —"] + list(df.columns.astype(str))

        c1, c2, c3 = st.columns(3)
        with c1:
            hotel_col   = st.selectbox("🏨 Hotel Name (optional)", cols)
            cat_col     = st.selectbox("📂 Category", cols)
        with c2:
            desc_col    = st.selectbox("📝 Description", cols)
            supplier_col= st.selectbox("🏢 Supplier (optional)", cols)
        with c3:
            amount_col  = st.selectbox("💷 Amount (£)", cols)
            notes_col   = st.selectbox("📋 Notes (optional)", cols)

        client_name_map = {c["name"].strip().lower(): c["id"] for c in clients}

        if desc_col != "— not used —" and amount_col != "— not used —":
            def safe_float(v):
                try: return float(str(v).replace("£","").replace(",","").strip())
                except: return 0.0

            preview = []
            for _, row in df.iterrows():
                desc_val    = str(row[desc_col]).strip()   if pd.notna(row[desc_col])   else ""
                amount_val  = safe_float(row[amount_col])  if pd.notna(row.get(amount_col)) else 0.0
                hotel_val   = str(row[hotel_col]).strip()  if hotel_col  != "— not used —" and pd.notna(row.get(hotel_col))   else ""
                supplier_val= str(row[supplier_col]).strip() if supplier_col != "— not used —" and pd.notna(row.get(supplier_col)) else ""
                cat_val     = str(row[cat_col]).strip()    if cat_col    != "— not used —" and pd.notna(row.get(cat_col))    else "Other"
                notes_val   = str(row[notes_col]).strip()  if notes_col  != "— not used —" and pd.notna(row.get(notes_col))  else ""

                if not desc_val or desc_val.lower() in ["nan","","description"]: continue
                if amount_val == 0: continue

                client_id = client_name_map.get(hotel_val.lower()) if hotel_val else None
                full_desc = f"{supplier_val} — {desc_val}" if supplier_val else desc_val

                preview.append({
                    "Hotel":       hotel_val or "Company-Wide",
                    "Category":    cat_val,
                    "Description": full_desc,
                    "Amount (£)":  amount_val,
                    "Notes":       notes_val,
                    "_client_id":  client_id,
                })

            if preview:
                st.markdown("---")
                st.subheader("🔍 Preview")
                disp = pd.DataFrame([{k:v for k,v in r.items() if k!="_client_id"} for r in preview])
                st.dataframe(disp, use_container_width=True, hide_index=True)

                total_amount = sum(r["Amount (£)"] for r in preview)
                c1, c2 = st.columns(2)
                c1.metric("Total Rows",    len(preview))
                c2.metric("Total Amount", f"£{total_amount:,.2f}")

                if st.button("💾 Save All Expenses", type="primary"):
                    saved=0; errors=[]
                    for r in preview:
                        try:
                            supabase.table("expenses").insert({
                                "client_id":   r["_client_id"],
                                "week_id":     week_id,
                                "category":    r["Category"],
                                "description": r["Description"],
                                "amount":      r["Amount (£)"],
                                "notes":       r["Notes"] or None,
                                "source_file": uploaded.name,
                            }).execute()
                            saved += 1
                        except Exception as e:
                            errors.append(f"{r['Description']}: {e}")

                    supabase.table("upload_log").insert({
                        "upload_type": "expense_bulk", "filename": uploaded.name,
                        "week_id": week_id, "records_processed": saved,
                        "records_failed": len(errors),
                        "status": "success" if not errors else "partial",
                        "error_log": {"errors": errors} if errors else None
                    }).execute()

                    if errors:
                        st.error(f"⚠️ Saved {saved} with {len(errors)} error(s):\n" + "\n".join(errors))
                    else:
                        st.success(f"✅ Saved {saved} expenses — Week {selected_week}!")
                    st.balloons()
            else:
                st.warning("No valid rows found. Check column mapping.")

# TAB 3 — VIEW THIS WEEK
with tab_view:
    st.subheader(f"📊 Expenses — Week ending {selected_week}")
    try:
        res = supabase.table("expenses").select(
            "category, description, amount, notes, source_file, clients(name)"
        ).eq("week_id", week_id).order("category").execute()

        if res.data:
            rows = []
            for r in res.data:
                c = r.get("clients") or {}
                rows.append({
                    "Hotel":       c.get("name", "Company-Wide"),
                    "Category":    r["category"],
                    "Description": r["description"],
                    "Amount (£)":  r["amount"],
                    "Notes":       r["notes"],
                })
            df_view = pd.DataFrame(rows)
            st.dataframe(df_view, use_container_width=True, hide_index=True)

            st.markdown("---")
            by_cat = df_view.groupby("Category")["Amount (£)"].sum().sort_values(ascending=False)
            c1, c2 = st.columns(2)
            with c1:
                st.metric("Total Expenses", f"£{df_view['Amount (£)'].sum():,.2f}")
                st.metric("No. of Lines",   len(rows))
            with c2:
                st.markdown("**By Category:**")
                for cat, amt in by_cat.items():
                    st.markdown(f"- **{cat}:** £{amt:,.2f}")
        else:
            st.info("No expenses recorded for this week yet.")
    except Exception as e:
        st.error(f"Error loading expenses: {e}")
