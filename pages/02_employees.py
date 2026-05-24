import streamlit as st
import pandas as pd
import io
from db import get_client, page_header

st.set_page_config(page_title="Employees", page_icon="👥", layout="wide")
page_header("👥 Employee Management", "Add, search, upload and manage staff records")

db = get_client()

# ── Tabs ─────────────────────────────────────────────────────
tab_view, tab_bulk, tab_add, tab_assign = st.tabs([
    "📋 View All Employees",
    "📤 Bulk Upload (CSV)",
    "➕ Add Single Employee",
    "🔗 Assign to Hotel",
])

# ═══════════════════════════════════════════════════════════════
# TAB 1 — VIEW ALL EMPLOYEES
# ═══════════════════════════════════════════════════════════════
with tab_view:
    st.subheader("All Employees")

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        search_term = st.text_input("🔍 Search by name or ref", "")
    with col_f2:
        type_filter = st.selectbox("Filter by type", ["All","payroll","self_emp","utr","mixed"])

    try:
        q = db.table("employees").select("*").order("full_name")
        if type_filter != "All":
            q = q.eq("employment_type", type_filter)
        rows = q.execute().data

        if search_term:
            rows = [r for r in rows if
                    search_term.lower() in r.get("full_name","").lower() or
                    search_term.lower() in (r.get("employee_ref") or "").lower()]

        if rows:
            df = pd.DataFrame(rows)
            display_cols = ["employee_ref","full_name","employment_type",
                            "utr_number","ni_number","bank_sort_code",
                            "bank_account_number","bank_name","is_active"]
            df_display = df[[c for c in display_cols if c in df.columns]]
            df_display.columns = ["Ref","Name","Type","UTR","NI",
                                   "Sort Code","Account","Bank","Active"]

            # Colour active vs inactive
            def style_row(row):
                colour = "" if row["Active"] else "background-color:#ffe0e0"
                return [colour] * len(row)

            st.dataframe(df_display.style.apply(style_row, axis=1),
                         use_container_width=True, height=420)
            st.caption(f"{len(rows)} employee(s) found")

            # ── Remove employee ───────────────────────────────
            st.markdown("---")
            st.subheader("✖ Deactivate Employee")
            names    = [f"{r['employee_ref']} — {r['full_name']}" for r in rows]
            to_remove = st.selectbox("Select employee to deactivate", names)
            if st.button("Deactivate Selected Employee", type="secondary"):
                ref = to_remove.split(" — ")[0]
                db.table("employees").update({"is_active": False}) \
                  .eq("employee_ref", ref).execute()
                st.success(f"✅ {to_remove} deactivated. Refresh to see update.")

            # ── Reactivate ────────────────────────────────────
            inactive = [r for r in rows if not r.get("is_active")]
            if inactive:
                st.markdown("---")
                st.subheader("✔ Reactivate Employee")
                in_names   = [f"{r['employee_ref']} — {r['full_name']}" for r in inactive]
                to_reactive = st.selectbox("Select employee to reactivate", in_names)
                if st.button("Reactivate", type="primary"):
                    ref2 = to_reactive.split(" — ")[0]
                    db.table("employees").update({"is_active": True}) \
                      .eq("employee_ref", ref2).execute()
                    st.success(f"✅ {to_reactive} reactivated.")
        else:
            st.info("No employees found. Use 'Bulk Upload' or 'Add Single Employee' to get started.")

    except Exception as e:
        st.error(f"Database error: {e}")

# ═══════════════════════════════════════════════════════════════
# TAB 2 — BULK UPLOAD CSV
# ═══════════════════════════════════════════════════════════════
with tab_bulk:
    st.subheader("📤 Bulk Upload Employees from CSV")

    # Download template
    template_data = {
        "employee_ref":        ["21","198","347"],
        "full_name":           ["V Mamaliga","D Heredia Corcino","R Potla"],
        "preferred_name":      ["","",""],
        "employment_type":     ["payroll","payroll","payroll"],
        "utr_number":          ["","",""],
        "ni_number":           ["","",""],
        "bank_name":           ["Barclays","Barclays","HSBC"],
        "bank_sort_code":      ["04-29-09","23-05-80","30-94-51"],
        "bank_account_number": ["14471302","25436304","11638262"],
        "bank_account_name":   ["V Mamaliga","D Heredia","R Potla"],
        "phone":               ["","",""],
        "email":               ["","",""],
        "notes":               ["","",""],
    }
    template_df = pd.DataFrame(template_data)
    csv_bytes    = template_df.to_csv(index=False).encode()

    st.download_button(
        "⬇ Download Employee Template CSV",
        data=csv_bytes,
        file_name="ARVY_Employee_Template.csv",
        mime="text/csv",
    )
    st.caption("Fill in the template with all your employees, then upload below.")

    st.markdown("**Column guide:**")
    st.markdown("""
    | Column | Required | Notes |
    |--------|----------|-------|
    | employee_ref | ✅ | Payroll ref number (e.g. 21, 198). Must be unique. |
    | full_name | ✅ | Full name as on payroll |
    | employment_type | ✅ | `payroll`, `self_emp`, `utr`, or `mixed` |
    | utr_number | — | UTR number if applicable |
    | ni_number | — | National Insurance number |
    | bank_sort_code | — | Format: 04-29-09 |
    | bank_account_number | — | 8-digit account number |
    | bank_name | — | Barclays, HSBC, etc. |
    """)

    uploaded = st.file_uploader("Upload your completed CSV", type=["csv"])

    if uploaded:
        try:
            df = pd.read_csv(uploaded, dtype=str).fillna("")

            # Validate required columns
            required = ["employee_ref","full_name","employment_type"]
            missing  = [c for c in required if c not in df.columns]
            if missing:
                st.error(f"Missing required columns: {missing}")
            else:
                st.success(f"✅ File loaded — {len(df)} employees found")
                st.dataframe(df, use_container_width=True)

                valid_types = {"payroll","self_emp","utr","mixed"}
                invalid_rows = df[~df["employment_type"].isin(valid_types)]
                if not invalid_rows.empty:
                    st.warning(f"⚠ {len(invalid_rows)} rows have invalid employment_type. "
                               f"Fix these before uploading.")
                    st.dataframe(invalid_rows)

                if st.button("⬆ Upload All Employees to Database", type="primary"):
                    success = fail = 0
                    errors  = []
                    for _, row in df.iterrows():
                        record = {k: (v if v != "" else None)
                                  for k, v in row.to_dict().items()}
                        record["is_active"] = True
                        try:
                            db.table("employees").upsert(
                                record, on_conflict="employee_ref"
                            ).execute()
                            success += 1
                        except Exception as ex:
                            fail += 1
                            errors.append(f"{row.get('full_name','?')}: {ex}")

                    db.table("upload_log").insert({
                        "upload_type": "employee_bulk",
                        "filename": uploaded.name,
                        "records_processed": success,
                        "records_failed": fail,
                        "status": "success" if fail == 0 else "partial",
                        "error_log": {"errors": errors},
                    }).execute()

                    st.success(f"✅ {success} employees uploaded successfully.")
                    if fail:
                        st.warning(f"⚠ {fail} failed:")
                        for e in errors:
                            st.caption(f"  • {e}")

        except Exception as e:
            st.error(f"Could not read file: {e}")

# ═══════════════════════════════════════════════════════════════
# TAB 3 — ADD SINGLE EMPLOYEE
# ═══════════════════════════════════════════════════════════════
with tab_add:
    st.subheader("➕ Add a Single Employee")

    with st.form("add_employee_form"):
        col1, col2 = st.columns(2)
        with col1:
            ref       = st.text_input("Employee Ref *", placeholder="e.g. 347")
            full_name = st.text_input("Full Name *",    placeholder="e.g. R Potla")
            pref_name = st.text_input("Preferred Name", placeholder="Optional")
            emp_type  = st.selectbox("Employment Type *",
                                     ["payroll","self_emp","utr","mixed"])
            utr_num   = st.text_input("UTR Number",     placeholder="e.g. UTR 3326935345")
            ni_num    = st.text_input("NI Number",      placeholder="e.g. AB123456C")
        with col2:
            bank_name = st.text_input("Bank Name",      placeholder="e.g. Barclays")
            sort_code = st.text_input("Sort Code",      placeholder="e.g. 04-29-09")
            acc_num   = st.text_input("Account Number", placeholder="e.g. 14471302")
            acc_name  = st.text_input("Account Name",   placeholder="Name on account")
            phone     = st.text_input("Phone",          placeholder="Optional")
            email     = st.text_input("Email",          placeholder="Optional")
        notes = st.text_area("Notes", placeholder="Optional")

        submitted = st.form_submit_button("Save Employee", type="primary")

    if submitted:
        if not ref or not full_name:
            st.error("Employee Ref and Full Name are required.")
        else:
            try:
                db.table("employees").upsert({
                    "employee_ref":        ref.strip(),
                    "full_name":           full_name.strip(),
                    "preferred_name":      pref_name or None,
                    "employment_type":     emp_type,
                    "utr_number":          utr_num   or None,
                    "ni_number":           ni_num    or None,
                    "bank_name":           bank_name or None,
                    "bank_sort_code":      sort_code or None,
                    "bank_account_number": acc_num   or None,
                    "bank_account_name":   acc_name  or None,
                    "phone":               phone     or None,
                    "email":               email     or None,
                    "notes":               notes     or None,
                    "is_active":           True,
                }, on_conflict="employee_ref").execute()
                st.success(f"✅ Employee '{full_name}' saved successfully.")
            except Exception as e:
                st.error(f"Error saving employee: {e}")

# ═══════════════════════════════════════════════════════════════
# TAB 4 — ASSIGN EMPLOYEE TO HOTEL
# ═══════════════════════════════════════════════════════════════
with tab_assign:
    st.subheader("🔗 Assign Employees to Hotels")
    st.caption("Link which employees work at which hotels. "
               "One employee can be assigned to multiple hotels.")

    try:
        emps    = db.table("employees").select("id,employee_ref,full_name") \
                    .eq("is_active", True).order("full_name").execute().data
        clients = db.table("clients").select("id,name,dept_number") \
                    .eq("is_active", True).order("name").execute().data

        if not emps:
            st.info("No employees yet. Upload employees first.")
        elif not clients:
            st.info("No clients found.")
        else:
            emp_opts    = {f"{e['employee_ref']} — {e['full_name']}": e['id']
                           for e in emps}
            client_opts = {f"Dept {c['dept_number']} — {c['name']}" if c['dept_number']
                           else c['name']: c['id']
                           for c in clients}

            with st.form("assign_form"):
                sel_emp    = st.selectbox("Select Employee", list(emp_opts.keys()))
                sel_hotels = st.multiselect("Assign to Hotels", list(client_opts.keys()))
                rate       = st.number_input("Agreed Hourly Rate (£)", min_value=0.0,
                                              value=11.44, step=0.01)
                start_date = st.date_input("Start Date")
                submitted2 = st.form_submit_button("Save Assignments", type="primary")

            if submitted2:
                emp_id = emp_opts[sel_emp]
                ok = fail = 0
                for hotel_label in sel_hotels:
                    client_id = client_opts[hotel_label]
                    try:
                        db.table("employee_client_assignments").upsert({
                            "employee_id": emp_id,
                            "client_id":   client_id,
                            "hourly_rate": float(rate),
                            "start_date":  str(start_date),
                            "is_active":   True,
                        }, on_conflict="employee_id,client_id").execute()
                        ok += 1
                    except Exception as ex:
                        fail += 1
                if ok:
                    st.success(f"✅ {ok} hotel assignment(s) saved for {sel_emp}.")
                if fail:
                    st.warning(f"⚠ {fail} assignment(s) failed.")

            # Show existing assignments
            st.markdown("---")
            st.subheader("Current Assignments")
            assigns = db.table("employee_client_assignments") \
                        .select("employees(employee_ref,full_name), clients(name,dept_number), hourly_rate, is_active") \
                        .execute().data
            if assigns:
                rows_flat = []
                for a in assigns:
                    rows_flat.append({
                        "Employee": f"{a['employees']['employee_ref']} — {a['employees']['full_name']}",
                        "Hotel":    a['clients']['name'],
                        "Rate (£)": a['hourly_rate'],
                        "Active":   a['is_active'],
                    })
                adf = pd.DataFrame(rows_flat)
                st.dataframe(adf, use_container_width=True, height=300)

    except Exception as e:
        st.error(f"Error loading data: {e}")
