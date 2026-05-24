import streamlit as st
import pandas as pd
from db import get_client, page_header

st.set_page_config(page_title="Employee Search", page_icon="🔍", layout="wide")
page_header("🔍 Employee Search", "Find any employee and view their full payment history")

supabase = get_client()

@st.cache_data(ttl=60)
def load_employees():
    return supabase.table("employees").select(
        "id,full_name,preferred_name,employee_ref,employment_type,ni_number,utr_number,"
        "bank_name,bank_sort_code,bank_account_number,bank_account_name,phone,email,is_active,notes"
    ).order("full_name").execute().data or []

if st.sidebar.button("🔄 Refresh Data"):
    load_employees.clear(); st.rerun()

employees = load_employees()

if not employees:
    st.error("⚠️ No employees found. Please upload employees first.")
    st.stop()

# ── Search bar ────────────────────────────────────────────────
st.subheader("🔎 Search Employee")
col1, col2 = st.columns([3, 1])
with col1:
    search = st.text_input("Search by name, ref, NI number or UTR number", placeholder="e.g. John Smith / 347 / AB123456C")
with col2:
    type_filter = st.selectbox("Employment Type", ["All", "payroll", "self_emp", "utr", "mixed"])

# Filter
filtered = employees
if search:
    s = search.lower()
    filtered = [e for e in filtered if
                s in (e.get("full_name") or "").lower() or
                s in (e.get("employee_ref") or "").lower() or
                s in (e.get("ni_number") or "").lower() or
                s in (e.get("utr_number") or "").lower() or
                s in (e.get("preferred_name") or "").lower()]
if type_filter != "All":
    filtered = [e for e in filtered if e.get("employment_type") == type_filter]

st.caption(f"{len(filtered)} employee(s) found")

if not filtered:
    st.info("No employees match your search.")
    st.stop()

# ── Employee list ─────────────────────────────────────────────
emp_opts = {f"{e['employee_ref']} — {e['full_name']} ({e['employment_type']})": e for e in filtered}
selected_label = st.selectbox("Select employee to view", list(emp_opts.keys()))
emp = emp_opts[selected_label]
emp_id = emp["id"]

st.markdown("---")

# ── Employee profile card ─────────────────────────────────────
c1, c2, c3 = st.columns(3)

with c1:
    st.markdown("### 👤 Personal Details")
    st.markdown(f"**Full Name:** {emp.get('full_name','—')}")
    st.markdown(f"**Preferred Name:** {emp.get('preferred_name','—') or '—'}")
    st.markdown(f"**Employee Ref:** {emp.get('employee_ref','—')}")
    st.markdown(f"**Employment Type:** {emp.get('employment_type','—')}")
    status = "🟢 Active" if emp.get("is_active") else "🔴 Inactive"
    st.markdown(f"**Status:** {status}")

with c2:
    st.markdown("### 🔢 Tax & Identity")
    st.markdown(f"**NI Number:** {emp.get('ni_number','—') or '—'}")
    st.markdown(f"**UTR Number:** {emp.get('utr_number','—') or '—'}")
    st.markdown(f"**Phone:** {emp.get('phone','—') or '—'}")
    st.markdown(f"**Email:** {emp.get('email','—') or '—'}")

with c3:
    st.markdown("### 🏦 Bank Details")
    st.markdown(f"**Bank:** {emp.get('bank_name','—') or '—'}")
    st.markdown(f"**Sort Code:** {emp.get('bank_sort_code','—') or '—'}")
    st.markdown(f"**Account No:** {emp.get('bank_account_number','—') or '—'}")
    st.markdown(f"**Account Name:** {emp.get('bank_account_name','—') or '—'}")

if emp.get("notes"):
    st.info(f"📝 Notes: {emp['notes']}")

st.markdown("---")

# ── Payment History Tabs ──────────────────────────────────────
tab_summary, tab_payroll, tab_selfemp, tab_utr, tab_hours = st.tabs([
    "📊 Summary",
    "💷 Payroll",
    "🧾 Self-Employed",
    "📑 UTR",
    "⏱️ Hours",
])

# ── Summary ───────────────────────────────────────────────────
with tab_summary:
    st.subheader("📊 All-Time Payment Summary")
    try:
        hist = supabase.table("v_employee_history").select("*").eq("employee_ref", emp.get("employee_ref","")).execute().data or []
        if hist:
            total_payroll  = sum(float(r.get("payroll_net")  or 0) for r in hist)
            total_selfemp  = sum(float(r.get("self_emp_net") or 0) for r in hist)
            total_utr      = sum(float(r.get("utr_net")      or 0) for r in hist)
            total_all      = total_payroll + total_selfemp + total_utr
            total_hrs      = sum(float(r.get("hours_received") or 0) for r in hist)

            c1,c2,c3,c4,c5 = st.columns(5)
            c1.metric("Total Weeks",      len(set(r.get("week_ending") for r in hist)))
            c2.metric("Total Hours",      f"{total_hrs:.1f}")
            c3.metric("Payroll Received", f"£{total_payroll:,.2f}")
            c4.metric("Self-Emp Received",f"£{total_selfemp:,.2f}")
            c5.metric("Total Earnings",   f"£{total_all:,.2f}")

            # Weekly breakdown
            df_hist = pd.DataFrame(hist)
            cols_show = [c for c in ["week_ending","client","hours_received","payroll_net","self_emp_net","utr_net","total_received"] if c in df_hist.columns]
            if cols_show:
                df_show = df_hist[cols_show].copy()
                df_show.columns = [c.replace("_"," ").title() for c in cols_show]
                st.dataframe(df_show, use_container_width=True, hide_index=True)
        else:
            st.info("No payment history found for this employee yet.")
    except Exception as e:
        st.error(f"Error loading summary: {e}")

# ── Payroll ───────────────────────────────────────────────────
with tab_payroll:
    st.subheader("💷 Payroll Payment History")
    try:
        pp = supabase.table("payroll_payments").select(
            "*, weeks(week_ending), clients(name)"
        ).eq("employee_id", emp_id).order("created_at", desc=True).execute().data or []

        if pp:
            rows = []
            for r in pp:
                rows.append({
                    "Week":         (r.get("weeks") or {}).get("week_ending","—"),
                    "Hotel":        (r.get("clients") or {}).get("name","—"),
                    "Gross (£)":    r.get("gross_pay",0),
                    "PAYE (£)":     r.get("paye_tax",0),
                    "Emp NIC (£)":  r.get("employee_nic",0),
                    "Er NIC (£)":   r.get("employer_nic",0),
                    "Pension (£)":  r.get("employee_pension",0),
                    "Net Pay (£)":  r.get("net_pay",0),
                })
            df_pp = pd.DataFrame(rows)
            st.dataframe(df_pp, use_container_width=True, hide_index=True)

            c1,c2,c3 = st.columns(3)
            c1.metric("Weeks Paid",     len(pp))
            c2.metric("Total Gross",   f"£{sum(r['Gross (£)'] for r in rows):,.2f}")
            c3.metric("Total Net",     f"£{sum(r['Net Pay (£)'] for r in rows):,.2f}")
        else:
            st.info("No payroll records found.")
    except Exception as e:
        st.error(f"Error: {e}")

# ── Self-Emp ──────────────────────────────────────────────────
with tab_selfemp:
    st.subheader("🧾 Self-Employed Payment History")
    try:
        sp = supabase.table("self_emp_payments").select(
            "*, weeks(week_ending), clients(name)"
        ).eq("employee_id", emp_id).order("created_at", desc=True).execute().data or []

        if sp:
            rows = []
            for r in sp:
                rows.append({
                    "Week":        (r.get("weeks") or {}).get("week_ending","—"),
                    "Hotel":       (r.get("clients") or {}).get("name","—"),
                    "Hours":       r.get("hours_paid",0),
                    "Rate (£)":    r.get("pay_rate",0),
                    "Gross (£)":   r.get("gross_amount",0),
                    "Net (£)":     r.get("net_amount",0),
                    "Status":      r.get("payment_status","—"),
                })
            df_sp = pd.DataFrame(rows)
            st.dataframe(df_sp, use_container_width=True, hide_index=True)

            c1,c2,c3 = st.columns(3)
            c1.metric("Weeks Paid",   len(sp))
            c2.metric("Total Hours",  f"{sum(float(r['Hours'] or 0) for r in rows):.1f}")
            c3.metric("Total Net",   f"£{sum(float(r['Net (£)'] or 0) for r in rows):,.2f}")
        else:
            st.info("No self-employed records found.")
    except Exception as e:
        st.error(f"Error: {e}")

# ── UTR ───────────────────────────────────────────────────────
with tab_utr:
    st.subheader("📑 UTR Payment History")
    try:
        up = supabase.table("utr_payments").select(
            "*, weeks(week_ending), clients(name)"
        ).eq("employee_id", emp_id).order("created_at", desc=True).execute().data or []

        if up:
            rows = []
            for r in up:
                rows.append({
                    "Week":        (r.get("weeks") or {}).get("week_ending","—"),
                    "Hotel":       (r.get("clients") or {}).get("name","—"),
                    "UTR No":      r.get("utr_number","—"),
                    "Hours":       r.get("hours_paid",0),
                    "Rate (£)":    r.get("pay_rate",0),
                    "Net (£)":     r.get("net_amount",0),
                    "Status":      r.get("payment_status","—"),
                })
            df_up = pd.DataFrame(rows)
            st.dataframe(df_up, use_container_width=True, hide_index=True)

            c1,c2,c3 = st.columns(3)
            c1.metric("Weeks Paid",  len(up))
            c2.metric("Total Hours", f"{sum(float(r['Hours'] or 0) for r in rows):.1f}")
            c3.metric("Total Net",  f"£{sum(float(r['Net (£)'] or 0) for r in rows):,.2f}")
        else:
            st.info("No UTR records found.")
    except Exception as e:
        st.error(f"Error: {e}")

# ── Hours ─────────────────────────────────────────────────────
with tab_hours:
    st.subheader("⏱️ Timesheet & Hour Disposal History")
    try:
        ts = supabase.table("timesheets").select(
            "hours_received, hourly_rate, source_file, weeks(week_ending), clients(name)"
        ).eq("employee_id", emp_id).order("created_at", desc=True).execute().data or []

        hd = supabase.table("hour_disposals").select(
            "hours_received, payroll_hours, self_emp_hours, utr_hours, weeks(week_ending), clients(name)"
        ).eq("employee_id", emp_id).order("created_at", desc=True).execute().data or []

        if ts:
            st.markdown("**Timesheets (hours received from client):**")
            rows_ts = []
            for r in ts:
                rows_ts.append({
                    "Week":         (r.get("weeks") or {}).get("week_ending","—"),
                    "Hotel":        (r.get("clients") or {}).get("name","—"),
                    "Hours Received": r.get("hours_received",0),
                    "Rate (£/hr)":   r.get("hourly_rate","—"),
                    "Source File":   r.get("source_file","—"),
                })
            st.dataframe(pd.DataFrame(rows_ts), use_container_width=True, hide_index=True)
            total_hrs = sum(float(r["Hours Received"] or 0) for r in rows_ts)
            st.metric("Total Hours Received", f"{total_hrs:.1f}")
        else:
            st.info("No timesheet records found.")

        if hd:
            st.markdown("---")
            st.markdown("**Hour Disposals (payroll / self-emp / UTR split):**")
            rows_hd = []
            for r in hd:
                rows_hd.append({
                    "Week":         (r.get("weeks") or {}).get("week_ending","—"),
                    "Hotel":        (r.get("clients") or {}).get("name","—"),
                    "Hrs Received": r.get("hours_received",0),
                    "Payroll Hrs":  r.get("payroll_hours",0),
                    "Self-Emp Hrs": r.get("self_emp_hours",0),
                    "UTR Hrs":      r.get("utr_hours",0),
                })
            st.dataframe(pd.DataFrame(rows_hd), use_container_width=True, hide_index=True)
        else:
            st.info("No hour disposal records found.")
    except Exception as e:
        st.error(f"Error: {e}")

st.markdown("---")
st.caption("💡 Tip: All data updates in real time as you upload new records.")
