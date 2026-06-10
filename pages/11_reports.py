import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta
from db import get_client, page_header

st.set_page_config(page_title="Reports", page_icon="📊", layout="wide")
page_header("📊 Reports & Dashboard", "Total hours, payroll costs and gross profit by hotel")

supabase = get_client()

if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear(); st.rerun()

# ── Load data ─────────────────────────────────────────────────
@st.cache_data(ttl=120)
def load_records():
    return supabase.table("weekly_records").select("*").execute().data or []

@st.cache_data(ttl=120)
def load_invoices():
    return supabase.table("zoho_invoices").select("*").execute().data or []

records  = load_records()
invoices = load_invoices()

if not records:
    st.warning("⚠️ No records yet. Upload timesheets and payments first.")
    st.stop()

df = pd.DataFrame(records)
df["week_date"]       = pd.to_datetime(df["week_date"])
df["hours_worked"]    = pd.to_numeric(df["hours_worked"],    errors="coerce").fillna(0)
df["payroll_amount"]  = pd.to_numeric(df["payroll_amount"],  errors="coerce").fillna(0)
df["self_emp_amount"] = pd.to_numeric(df["self_emp_amount"], errors="coerce").fillna(0)
df["utr_amount"]      = pd.to_numeric(df["utr_amount"],      errors="coerce").fillna(0)
df["total_paid"]      = df["payroll_amount"] + df["self_emp_amount"] + df["utr_amount"]
df["month"]           = df["week_date"].dt.to_period("M").astype(str)
df["year"]            = df["week_date"].dt.year

# Invoices (income)
df_inv = pd.DataFrame(invoices) if invoices else pd.DataFrame()
if not df_inv.empty:
    df_inv["date"]  = pd.to_datetime(df_inv["date"])
    df_inv["total"] = pd.to_numeric(df_inv["total"], errors="coerce").fillna(0)

# ── Sidebar filters ───────────────────────────────────────────
st.sidebar.header("🔽 Filters")
filter_type   = st.sidebar.selectbox("Period", ["All Time","This Week","Last Week","This Month","Last Month","This Year","Custom"])
all_hotels    = ["All Hotels"] + sorted(df["client_name"].dropna().unique().tolist())
hotel_filter  = st.sidebar.selectbox("🏨 Hotel", all_hotels)

today = date.today()
if filter_type == "This Week":
    date_from = today - timedelta(days=today.weekday())
    date_to   = today
elif filter_type == "Last Week":
    date_from = today - timedelta(days=today.weekday() + 7)
    date_to   = today - timedelta(days=today.weekday() + 1)
elif filter_type == "This Month":
    date_from = today.replace(day=1)
    date_to   = today
elif filter_type == "Last Month":
    first_this = today.replace(day=1)
    date_to    = first_this - timedelta(days=1)
    date_from  = date_to.replace(day=1)
elif filter_type == "This Year":
    date_from = today.replace(month=1, day=1)
    date_to   = today
elif filter_type == "Custom":
    date_from = st.sidebar.date_input("From", value=today - timedelta(days=30))
    date_to   = st.sidebar.date_input("To",   value=today)
else:
    date_from = None
    date_to   = None

# Apply filters
df_f = df.copy()
if date_from:
    df_f = df_f[df_f["week_date"].dt.date >= date_from]
if date_to:
    df_f = df_f[df_f["week_date"].dt.date <= date_to]
if hotel_filter != "All Hotels":
    df_f = df_f[df_f["client_name"] == hotel_filter]

# Filter invoices
df_inv_f = df_inv.copy() if not df_inv.empty else pd.DataFrame()
if not df_inv_f.empty:
    if date_from:
        df_inv_f = df_inv_f[df_inv_f["date"].dt.date >= date_from]
    if date_to:
        df_inv_f = df_inv_f[df_inv_f["date"].dt.date <= date_to]
    if hotel_filter != "All Hotels":
        df_inv_f = df_inv_f[df_inv_f["client_name"].str.lower().str.contains(hotel_filter.lower(), na=False)]

# ── KPI Cards ─────────────────────────────────────────────────
st.subheader("📊 Summary")

total_hours   = df_f["hours_worked"].sum()
total_payroll = df_f["payroll_amount"].sum()
total_self    = df_f["self_emp_amount"].sum()
total_utr     = df_f["utr_amount"].sum()
total_cost    = df_f["total_paid"].sum()
total_income  = float(df_inv_f["total"].sum()) if not df_inv_f.empty else 0.0
gross_profit  = total_income - total_cost
margin        = (gross_profit / total_income * 100) if total_income > 0 else 0

c1,c2,c3,c4 = st.columns(4)
c1.metric("⏱️ Total Hours",    f"{total_hours:,.1f}")
c2.metric("💰 Total Income",   f"£{total_income:,.2f}")
c3.metric("💸 Total Cost",     f"£{total_cost:,.2f}")
c4.metric("📈 Gross Profit",   f"£{gross_profit:,.2f}", delta=f"{margin:.1f}% margin")

c5,c6,c7,c8 = st.columns(4)
c5.metric("💷 Payroll",        f"£{total_payroll:,.2f}")
c6.metric("🧾 Self-Emp",       f"£{total_self:,.2f}")
c7.metric("📑 UTR",            f"£{total_utr:,.2f}")
c8.metric("👥 Employees",      df_f["employee_name"].nunique())

st.markdown("---")

# ── Tabs ──────────────────────────────────────────────────────
tab_hotel, tab_weekly, tab_trend, tab_cost = st.tabs([
    "🏨 By Hotel", "📋 Weekly Records", "📈 Trends", "🍩 Cost Breakdown"
])

with tab_hotel:
    st.subheader("🏨 Performance by Hotel")
    hotel_grp = df_f.groupby("client_name").agg(
        Hours=("hours_worked","sum"),
        Payroll=("payroll_amount","sum"),
        SelfEmp=("self_emp_amount","sum"),
        UTR=("utr_amount","sum"),
        Total_Cost=("total_paid","sum"),
        Employees=("employee_name","nunique"),
    ).reset_index().rename(columns={"client_name":"Hotel"})
    hotel_grp["Total_Cost"] = hotel_grp["Total_Cost"].round(2)

    fig = px.bar(hotel_grp, x="Hotel", y="Total_Cost", color="Total_Cost",
        color_continuous_scale=["#1B4F8A","#2E6DB4","#5B9BD5"],
        title="Total Cost by Hotel", text=hotel_grp["Total_Cost"].apply(lambda x: f"£{x:,.0f}"))
    fig.update_layout(plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        font_color="#1C2B3A", showlegend=False, xaxis_tickangle=-45)
    fig.update_traces(textposition="outside")
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(hotel_grp, use_container_width=True, hide_index=True)

with tab_weekly:
    st.subheader("📋 Weekly Records")
    grp = df_f.groupby(["week_date","client_name"]).agg(
        Employees=("employee_name","nunique"),
        Hours=("hours_worked","sum"),
        Payroll=("payroll_amount","sum"),
        SelfEmp=("self_emp_amount","sum"),
        UTR=("utr_amount","sum"),
        Total=("total_paid","sum"),
    ).reset_index()
    grp["week_date"] = grp["week_date"].dt.strftime("%d %b %Y")
    grp.rename(columns={"week_date":"Week","client_name":"Hotel"}, inplace=True)
    st.dataframe(grp, use_container_width=True, hide_index=True)
    csv = grp.to_csv(index=False).encode()
    st.download_button("⬇ Download as CSV", csv, "ARVY_weekly_records.csv", "text/csv")

with tab_trend:
    st.subheader("📈 Weekly Trends")
    trend = df_f.groupby("week_date").agg(
        Hours=("hours_worked","sum"),
        Cost=("total_paid","sum"),
    ).reset_index()
    trend["week_date"] = trend["week_date"].dt.strftime("%Y-%m-%d")

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=trend["week_date"], y=trend["Hours"],
        mode="lines+markers", name="Hours", line=dict(color="#1B4F8A", width=2), yaxis="y2"))
    fig2.add_trace(go.Scatter(x=trend["week_date"], y=trend["Cost"],
        mode="lines+markers", name="Total Cost £", line=dict(color="#e74c3c", width=2)))
    fig2.update_layout(
        title="Hours & Cost by Week",
        xaxis_title="Week",
        yaxis=dict(title="Amount £", titlefont=dict(color="#e74c3c")),
        yaxis2=dict(title="Hours", titlefont=dict(color="#1B4F8A"), overlaying="y", side="right"),
        plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        font_color="#1C2B3A", hovermode="x unified",
        legend=dict(orientation="h", y=-0.2)
    )
    st.plotly_chart(fig2, use_container_width=True)

with tab_cost:
    st.subheader("🍩 Cost Breakdown")
    totals = {
        "Payroll": float(df_f["payroll_amount"].sum()),
        "Self-Emp": float(df_f["self_emp_amount"].sum()),
        "UTR": float(df_f["utr_amount"].sum()),
    }
    totals = {k: v for k, v in totals.items() if v > 0}
    if totals:
        c1, c2 = st.columns(2)
        with c1:
            fig3 = px.pie(names=list(totals.keys()), values=list(totals.values()),
                title="Cost Split", color_discrete_sequence=["#1B4F8A","#2E6DB4","#5B9BD5"], hole=0.4)
            fig3.update_layout(plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF", font_color="#1C2B3A")
            st.plotly_chart(fig3, use_container_width=True)
        with c2:
            st.markdown("### 💰 Cost Summary")
            for k, v in totals.items():
                pct = v / max(sum(totals.values()), 1) * 100
                st.metric(k, f"£{v:,.2f}", delta=f"{pct:.1f}% of costs")
            st.markdown("---")
            st.metric("Total Cost",    f"£{sum(totals.values()):,.2f}")
            st.metric("Total Income",  f"£{total_income:,.2f}")
            st.metric("Gross Profit",  f"£{gross_profit:,.2f}")
            st.metric("Profit Margin", f"{margin:.1f}%")
    else:
        st.info("No cost data for the selected filters.")

st.markdown("---")
st.caption("📊 Data from Supabase & Zoho Books  •  ARVY Portal v1.0")
