import streamlit as st
import pandas as pd
from db import get_client, page_header

st.set_page_config(page_title="UTR Upload", page_icon="📑", layout="wide")
page_header("📑 UTR Payments", "Upload weekly UTR staff payment records")

supabase = get_client()

@st.cache_data(ttl=60)
def load_clients():
    return supabase.table("clients").select("id,name").eq("is_active",True).order("name").execute().data or []
@st.cache_data(ttl=60)
def load_weeks():
    return supabase.table("weeks").select("*").order("week_ending",desc=True).execute().data or []
@st.cache_data(ttl=60)
def load_employees():
    return supabase.table("employees").select("id,full_name,preferred_name,employee_ref,utr_number").eq("is_active",True).execute().data or []

if st.sidebar.button("🔄 Refresh Data"):
    load_clients.clear(); load_weeks.clear(); load_employees.clear(); st.rerun()

clients=load_clients(); weeks=load_weeks(); employees=load_employees()
if not clients or not weeks:
    st.error("⚠️ No hotels or weeks loaded."); st.stop()

employee_map={}
for e in employees:
    employee_map[e["full_name"].strip().lower()]=e
    if e.get("preferred_name"): employee_map[e["preferred_name"].strip().lower()]=e
    if e.get("employee_ref"):   employee_map[str(e["employee_ref"]).strip().lower()]=e
    if e.get("utr_number"):     employee_map[str(e["utr_number"]).strip().lower()]=e

st.sidebar.header("⚙️ Select Week & Hotel")
week_options=[w["week_ending"] for w in weeks]
selected_week=st.sidebar.selectbox("Week Ending",week_options)
week_id=next(w["id"] for w in weeks if w["week_ending"]==selected_week)
client_names=[c["name"] for c in clients]
selected_client=st.sidebar.selectbox("🏨 Hotel / Client",client_names)
client_id=next(c["id"] for c in clients if c["name"]==selected_client)
st.sidebar.markdown("---")
st.sidebar.info(f"📅 Week: **{selected_week}**\n\n🏨 Hotel: **{selected_client}**")

st.markdown("---")
st.subheader("📂 Upload UTR Staff Excel File")
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
        name_col  = st.selectbox("👤 Employee Name / Ref",cols)
        utr_col   = st.selectbox("🔢 UTR Number (optional)",cols)
        hours_col = st.selectbox("⏱️ Hours Paid",cols)
    with c2:
        rate_col  = st.selectbox("💷 Pay Rate (£/hr)",cols)
        net_col   = st.selectbox("🏦 Net Amount",cols)
    with c3:
        sort_col  = st.selectbox("🏦 Sort Code (optional)",cols)
        acc_col   = st.selectbox("🏦 Account Number (optional)",cols)
        accname_col=st.selectbox("🏦 Account Name (optional)",cols)

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
                "Name":        name_val,
                "UTR":         str(row[utr_col]) if utr_col!="— not used —" and pd.notna(row.get(utr_col)) else "",
                "Hours":       safe_float(row[hours_col]) if hours_col!="— not used —" else 0,
                "Rate (£)":    safe_float(row[rate_col])  if rate_col !="— not used —" else 0,
                "Net (£)":     safe_float(row[net_col])   if net_col  !="— not used —" else 0,
                "Sort Code":   str(row[sort_col])    if sort_col   !="— not used —" and pd.notna(row.get(sort_col))    else "",
                "Acc Number":  str(row[acc_col])     if acc_col    !="— not used —" and pd.notna(row.get(acc_col))     else "",
                "Acc Name":    str(row[accname_col]) if accname_col!="— not used —" and pd.notna(row.get(accname_col)) else "",
                "Match":       "✅ Found" if emp else "❌ Not Found",
                "_emp":        emp,
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
                if st.button("💾 Save UTR Payments",type="primary"):
                    saved=0; errors=[]
                    for r in preview:
                        if "❌" in r["Match"]: continue
                        emp=r["_emp"]
                        try:
                            supabase.table("utr_payments").upsert({
                                "employee_id":          emp["id"],
                                "client_id":            client_id,
                                "week_id":              week_id,
                                "utr_number":           r["UTR"] or emp.get("utr_number"),
                                "hours_paid":           r["Hours"],
                                "pay_rate":             r["Rate (£)"],
                                "net_amount":           r["Net (£)"],
                                "payment_status":       "paid",
                                "bank_sort_code":       r["Sort Code"] or None,
                                "bank_account_number":  r["Acc Number"] or None,
                                "bank_account_name":    r["Acc Name"] or None,
                                "source_file":          uploaded.name,
                            },on_conflict="employee_id,client_id,week_id").execute()
                            saved+=1
                        except Exception as e:
                            errors.append(f"{r['Name']}: {e}")

                    supabase.table("upload_log").insert({
                        "upload_type":"utr","filename":uploaded.name,
                        "week_id":week_id,"records_processed":saved,
                        "records_failed":len(errors),
                        "status":"success" if not errors else "partial",
                        "error_log":{"errors":errors} if errors else None
                    }).execute()

                    if errors:
                        st.error(f"⚠️ Saved {saved} with {len(errors)} error(s):\n"+"\n".join(errors))
                    else:
                        st.success(f"✅ Saved {saved} UTR payments — {selected_client} | Week {selected_week}!")
                    st.balloons()
