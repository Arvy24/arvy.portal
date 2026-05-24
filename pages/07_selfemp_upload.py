import streamlit as st
import pandas as pd
from db import get_client, page_header

st.set_page_config(page_title="Self-Emp Upload", page_icon="🧾", layout="wide")
page_header("🧾 Self-Employed Payments", "Upload weekly self-employed payment records")

supabase = get_client()

@st.cache_data(ttl=60)
def load_clients():
    return supabase.table("clients").select("id,name").eq("is_active",True).order("name").execute().data or []
@st.cache_data(ttl=60)
def load_weeks():
    return supabase.table("weeks").select("*").order("week_ending",desc=True).execute().data or []
@st.cache_data(ttl=60)
def load_employees():
    return supabase.table("employees").select("id,full_name,preferred_name,employee_ref").eq("is_active",True).execute().data or []

if st.sidebar.button("🔄 Refresh Data"):
    load_clients.clear(); load_weeks.clear(); load_employees.clear(); st.rerun()

clients=load_clients(); weeks=load_weeks(); employees=load_employees()
if not clients or not weeks:
    st.error("⚠️ No hotels or weeks loaded."); st.stop()

employee_map = {}
for e in employees:
    employee_map[e["full_name"].strip().lower()] = e
    if e.get("preferred_name"): employee_map[e["preferred_name"].strip().lower()] = e
    if e.get("employee_ref"):   employee_map[str(e["employee_ref"]).strip().lower()] = e

st.sidebar.header("⚙️ Select Week & Hotel")
week_options=[ w["week_ending"] for w in weeks]
selected_week=st.sidebar.selectbox("Week Ending",week_options)
week_id=next(w["id"] for w in weeks if w["week_ending"]==selected_week)
client_names=[c["name"] for c in clients]
selected_client=st.sidebar.selectbox("🏨 Hotel / Client",client_names)
client_id=next(c["id"] for c in clients if c["name"]==selected_client)
st.sidebar.markdown("---")
st.sidebar.info(f"📅 Week: **{selected_week}**\n\n🏨 Hotel: **{selected_client}**")

st.markdown("---")
st.subheader("📂 Upload Self-Employed Excel File")
uploaded=st.file_uploader("Upload Excel file (.xlsx)",type=["xlsx","xls"])

if uploaded:
    xl=pd.ExcelFile(uploaded)
    sheet=st.selectbox("Select Sheet",xl.sheet_names)
    c1,c2=st.columns(2)
    with c1: header_row=st.number_input("Header row (0=first)",0,20,0)
    with c2: skip_last=st.number_input("Skip rows at bottom",0,10,1)

    df=pd.read_excel(uploaded,sheet_name=sheet,header=int(header_row))
    df=df.dropna(how="all")
    if skip_last>0: df=df.iloc[:-skip_last]
    df=df.reset_index(drop=True)
    st.dataframe(df.head(20),use_container_width=True)

    st.markdown("---")
    st.subheader("🗂️ Map Columns")
    cols=["— not used —"]+list(df.columns.astype(str))

    c1,c2,c3=st.columns(3)
    with c1:
        name_col   = st.selectbox("👤 Employee Name / Ref",cols)
        hours_col  = st.selectbox("⏱️ Hours Paid",cols)
    with c2:
        rate_col   = st.selectbox("💷 Pay Rate (£/hr)",cols)
        gross_col  = st.selectbox("💰 Gross Amount",cols)
    with c3:
        net_col    = st.selectbox("🏦 Net Amount",cols)
        status_col = st.selectbox("📋 Payment Status (optional)",cols)

    if name_col!="— not used —":
        def safe_float(v):
            try: return float(str(v).replace("£","").replace(",","").strip())
            except: return 0.0

        preview=[]
        for _,row in df.iterrows():
            name_val=str(row[name_col]).strip() if pd.notna(row[name_col]) else ""
            if not name_val or name_val.lower() in ["nan","","name","employee","total"]: continue
            emp=employee_map.get(name_val.lower())
            preview.append({
                "Name":       name_val,
                "Hours":      safe_float(row[hours_col]) if hours_col!="— not used —" else 0,
                "Rate (£)":   safe_float(row[rate_col])  if rate_col !="— not used —" else 0,
                "Gross (£)":  safe_float(row[gross_col]) if gross_col!="— not used —" else 0,
                "Net (£)":    safe_float(row[net_col])   if net_col  !="— not used —" else 0,
                "Status":     str(row[status_col]) if status_col!="— not used —" and pd.notna(row.get(status_col)) else "paid",
                "Match":      "✅ Found" if emp else "❌ Not Found",
                "_emp":       emp,
            })

        if preview:
            st.markdown("---")
            st.subheader("🔍 Preview & Match")
            disp=pd.DataFrame([{k:v for k,v in r.items() if k!="_emp"} for r in preview])
            st.dataframe(disp,use_container_width=True)

            matched=sum(1 for r in preview if "✅" in r["Match"])
            unmatched=sum(1 for r in preview if "❌" in r["Match"])
            c1,c2,c3=st.columns(3)
            c1.metric("Total",len(preview)); c2.metric("✅ Matched",matched); c3.metric("❌ Not Found",unmatched)
            if unmatched: st.warning(f"⚠️ {unmatched} not found — will be skipped.")

            total_net=sum(r["Net (£)"] for r in preview)
            st.info(f"📊 Total Net Payment: **£{total_net:,.2f}** | Matched: **{matched}** employees")

            if matched>0:
                if st.button("💾 Save Self-Emp Payments",type="primary"):
                    saved=0; errors=[]
                    for r in preview:
                        if "❌" in r["Match"]: continue
                        emp=r["_emp"]
                        try:
                            supabase.table("self_emp_payments").upsert({
                                "employee_id":   emp["id"],
                                "client_id":     client_id,
                                "week_id":       week_id,
                                "hours_paid":    r["Hours"],
                                "pay_rate":      r["Rate (£)"],
                                "gross_amount":  r["Gross (£)"],
                                "net_amount":    r["Net (£)"],
                                "payment_status":r["Status"],
                                "source_file":   uploaded.name,
                            },on_conflict="employee_id,client_id,week_id").execute()
                            saved+=1
                        except Exception as e:
                            errors.append(f"{r['Name']}: {e}")

                    supabase.table("upload_log").insert({
                        "upload_type":"self_emp","filename":uploaded.name,
                        "week_id":week_id,"records_processed":saved,
                        "records_failed":len(errors),
                        "status":"success" if not errors else "partial",
                        "error_log":{"errors":errors} if errors else None
                    }).execute()

                    if errors:
                        st.error(f"⚠️ Saved {saved} with {len(errors)} error(s):\n"+"\n".join(errors))
                    else:
                        st.success(f"✅ Saved {saved} self-emp payments — {selected_client} | Week {selected_week}!")
                    st.balloons()
