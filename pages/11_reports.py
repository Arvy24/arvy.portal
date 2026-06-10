import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta
from db import get_client, page_header

st.set_page_config(page_title="Reports", page_icon="📊", layout="wide")
page_header("📊 Reports & Dashboard", "Income vs costs — all figures from Zoho Books (bank reconciled)")

supabase = get_client()

if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear(); st.rerun()

# ── Load data ─────────────────────────────────────────────────
@st.cache_data(ttl=120)
def load_invoices():
    return supabase.table("zoho_invoices").select("*").execute().data or []

@st.cache_data(ttl=120)
def load_expenses():
    return supabase.table("zoho_expenses").select("*").execute().data or []

@st.cache_data(ttl=120)
def load_bills():
    return supabase.table("zoho_bills").select("*").execute().data or []

@st.cache_data(ttl=120)
def load_records():
    return supabase.table("weekly_records").select("*").execute().data or []

invoices = load_invoices()
expenses = load_expenses()
bills    = load_bills()
records  = load_records()

# ── Build DataFrames ──────────────────────────────────────────
def to_df(data, date_col="date"):
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data).copy()
    if date_col in df.columns:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    if "total" in df.columns:
        df["total"] = pd.to_numeric(df["total"], errors="coerce").fillna(0)
    return df

df_inv   = to_df(invoices)
df_exp   = to_df(expenses)
df_bills = to_df(bills)

df_wr = pd.DataFrame(records).copy() if records else pd.DataFrame()
if not df_wr.empty:
    df_wr["week_date"]    = pd.to_datetime(df_wr["week_date"])
    df_wr["hours_worked"] = pd.to_numeric(df_wr["hours_worked"], errors="coerce").fillna(0)

# ── Sidebar filters ───────────────────────────────────────────
st.sidebar.header("🔽 Filters")
filter_type = st.sidebar.selectbox("Period", [
    "All Time","This Week","Last Week","This Month","Last Month","This Year","Custom"
])
all_hotels   = ["All Hotels"] + sorted(df_inv["client_name"].dropna().unique().tolist()) if not df_inv.empty else ["All Hotels"]
hotel_filter = st.sidebar.selectbox("🏨 Hotel", all_hotels)

today = date.today()
date_from = date_to = None
if filter_type == "This Week":
    date_from = today - timedelta(days=today.weekday()); date_to = today
elif filter_type == "Last Week":
    date_from = today - timedelta(days=today.weekday()+7); date_to = today - timedelta(days=today.weekday()+1)
elif filter_type == "This Month":
    date_from = today.replace(day=1); date_to = today
elif filter_type == "Last Month":
    first = today.replace(day=1); date_to = first - timedelta(days=1); date_from = date_to.replace(day=1)
elif filter_type == "This Year":
    date_from = today.replace(month=1, day=1); date_to = today
elif filter_type == "Custom":
    date_from = st.sidebar.date_input("From", value=today - timedelta(days=30))
    date_to   = st.sidebar.date_input("To",   value=today)

def apply_date_filter(df, col="date"):
    if df.empty: return df
    out = df.copy()
    if date_from: out = out[out[col].dt.date >= date_from]
    if date_to:   out = out[out[col].dt.date <= date_to]
    return out

def apply_hotel_filter(df, col="client_name"):
    if df.empty or hotel_filter == "All Hotels": return df
    return df[df[col].str.lower().str.contains(hotel_filter.lower(), na=False)].copy()

CHART_LAYOUT = dict(
    plot_bgcolor="#FFFFFF",
    paper_bgcolor="#FFFFFF",
    font=dict(color="#1C2B3A"),
    margin=dict(t=50, b=60, l=40, r=20),
)

# Apply filters
df_inv_f   = apply_hotel_filter(apply_date_filter(df_inv),   "client_name")
df_exp_f   = apply_date_filter(df_exp).copy()
df_bills_f = apply_date_filter(df_bills).copy()

# Weekly records — hours only
df_wr_f = df_wr.copy() if not df_wr.empty else pd.DataFrame()
if not df_wr_f.empty:
    if date_from: df_wr_f = df_wr_f[df_wr_f["week_date"].dt.date >= date_from]
    if date_to:   df_wr_f = df_wr_f[df_wr_f["week_date"].dt.date <= date_to]
    if hotel_filter != "All Hotels":
        df_wr_f = df_wr_f[df_wr_f["client_name"] == hotel_filter]

# ── Totals ────────────────────────────────────────────────────
total_income   = float(df_inv_f["total"].sum())   if not df_inv_f.empty else 0
total_expenses = float(df_exp_f["total"].sum())   if not df_exp_f.empty else 0
total_bills    = float(df_bills_f["total"].sum()) if not df_bills_f.empty else 0
total_cost     = total_expenses + total_bills
gross_profit   = total_income - total_cost
margin         = (gross_profit / total_income * 100) if total_income > 0 else 0
total_hours    = float(df_wr_f["hours_worked"].sum()) if not df_wr_f.empty else 0

# ── KPI Cards ─────────────────────────────────────────────────
st.subheader("📊 Summary")
st.caption("💡 Income = Zoho Invoices  |  Costs = Zoho Expenses + Bills (bank reconciled)  |  Hours = timesheet uploads")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("⏱️ Total Hours",    f"{total_hours:,.1f}")
c2.metric("💰 Total Income",   f"£{total_income:,.2f}")
c3.metric("💸 Total Expenses", f"£{total_expenses:,.2f}")
c4.metric("🧾 Total Bills",    f"£{total_bills:,.2f}")
c5.metric("📈 Gross Profit",   f"£{gross_profit:,.2f}",
          delta=f"{margin:.1f}% margin",
          delta_color="normal" if gross_profit >= 0 else "inverse")

st.markdown("---")

# ── Tabs ──────────────────────────────────────────────────────
tab_pl, tab_hotel, tab_trend, tab_breakdown, tab_hours = st.tabs([
    "📋 P&L Summary", "🏨 By Hotel", "📈 Trends", "🍩 Cost Breakdown", "⏱️ Hours Detail"
])

# ─────────────────────────────────────────────────────────────
with tab_pl:
    st.subheader("📋 Profit & Loss Summary")
    pl_rows = [
        {"Category": "INCOME", "Item": "Client Invoices (Zoho)",
         "Amount £": round(total_income, 2)},
        {"Category": "COSTS",  "Item": "Expenses (Zoho — incl. payroll/UTR/self-emp/other)",
         "Amount £": round(total_expenses, 2)},
        {"Category": "COSTS",  "Item": "Supplier Bills (Zoho)",
         "Amount £": round(total_bills, 2)},
        {"Category": "TOTAL",  "Item": "Total Costs",
         "Amount £": round(total_cost, 2)},
        {"Category": "RESULT", "Item": "Gross Profit",
         "Amount £": round(gross_profit, 2)},
        {"Category": "RESULT", "Item": "Profit Margin %",
         "Amount £": round(margin, 2)},
    ]
    df_pl = pd.DataFrame(pl_rows)
    st.dataframe(df_pl, use_container_width=True, hide_index=True)
    csv = df_pl.to_csv(index=False).encode()
    st.download_button("⬇ Download P&L as CSV", csv, "ARVY_PL.csv", "text/csv")

# ─────────────────────────────────────────────────────────────
with tab_hotel:
    st.subheader("🏨 Income by Hotel (from Zoho Invoices)")
    if not df_inv_f.empty:
        hotel_grp = df_inv_f.groupby("client_name").agg(
            Invoices=("total","count"),
            Income=("total","sum"),
            Outstanding=("balance","sum"),
        ).reset_index().rename(columns={"client_name":"Hotel"}).sort_values("Income", ascending=False)

        try:
            fig = px.bar(
                hotel_grp, x="Hotel", y="Income",
                color="Income",
                color_continuous_scale=["#1B4F8A","#2E6DB4","#27ae60"],
                title="Income by Hotel",
                text=hotel_grp["Income"].apply(lambda x: f"£{x:,.0f}"),
            )
            fig.update_layout(**CHART_LAYOUT, showlegend=False, xaxis_tickangle=-45)
            fig.update_traces(textposition="outside")
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.warning(f"Chart error: {e}")

        st.dataframe(hotel_grp.round(2), use_container_width=True, hide_index=True)
    else:
        st.info("No invoice data. Sync from Zoho Books first.")

# ─────────────────────────────────────────────────────────────
with tab_trend:
    st.subheader("📈 Monthly Trends")
    try:
        if not df_inv_f.empty:
            df_inv_trend = df_inv_f.copy()
            df_inv_trend["month"] = df_inv_trend["date"].dt.to_period("M").dt.to_timestamp()
            inv_monthly = df_inv_trend.groupby("month")["total"].sum().reset_index()
            inv_monthly.columns = ["Month", "Income"]

            df_exp_trend = df_exp_f.copy()
            exp_monthly = pd.DataFrame()
            if not df_exp_trend.empty and "date" in df_exp_trend.columns:
                df_exp_trend["month"] = df_exp_trend["date"].dt.to_period("M").dt.to_timestamp()
                exp_monthly = df_exp_trend.groupby("month")["total"].sum().reset_index()
                exp_monthly.columns = ["Month", "Costs"]

            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(
                x=inv_monthly["Month"].astype(str),
                y=inv_monthly["Income"],
                mode="lines+markers",
                name="Income",
                line=dict(color="#27ae60", width=2),
            ))
            if not exp_monthly.empty:
                fig2.add_trace(go.Scatter(
                    x=exp_monthly["Month"].astype(str),
                    y=exp_monthly["Costs"],
                    mode="lines+markers",
                    name="Total Costs",
                    line=dict(color="#e74c3c", width=2),
                ))
            fig2.update_layout(
                title="Income vs Costs by Month",
                xaxis_title="Month",
                yaxis_title="Amount £",
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                **CHART_LAYOUT,
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No data for trends. Sync from Zoho Books first.")
    except Exception as e:
        st.warning(f"Could not render trend chart: {e}")

# ─────────────────────────────────────────────────────────────
with tab_breakdown:
    st.subheader("🍩 Cost Breakdown by Category")
    try:
        if not df_exp_f.empty and "account_name" in df_exp_f.columns:
            cat_grp = df_exp_f.groupby("account_name")["total"].sum().reset_index()
            cat_grp.columns = ["Category","Amount"]
            cat_grp = cat_grp[cat_grp["Amount"] > 0].sort_values("Amount", ascending=False).copy()

            if not df_bills_f.empty:
                bills_total = float(df_bills_f["total"].sum())
                cat_grp = pd.concat([
                    cat_grp,
                    pd.DataFrame([{"Category":"Supplier Bills","Amount":bills_total}])
                ], ignore_index=True)

            c1, c2 = st.columns(2)
            with c1:
                fig3 = px.pie(cat_grp, names="Category", values="Amount",
                              title="Costs by Category", hole=0.4)
                fig3.update_layout(**CHART_LAYOUT)
                st.plotly_chart(fig3, use_container_width=True)
            with c2:
                st.dataframe(cat_grp.round(2), use_container_width=True, hide_index=True)
                st.markdown("---")
                st.metric("Total Costs",  f"£{total_cost:,.2f}")
                st.metric("Total Income", f"£{total_income:,.2f}")
                st.metric("Gross Profit", f"£{gross_profit:,.2f}")
        else:
            st.info("No expense breakdown available. Sync from Zoho Books first.")
    except Exception as e:
        st.warning(f"Could not render breakdown: {e}")

# ─────────────────────────────────────────────────────────────
with tab_hours:
    st.subheader("⏱️ Hours by Hotel (from Timesheets)")
    st.caption("Hours tracked via timesheet uploads — not from Zoho")
    if not df_wr_f.empty:
        hrs_grp = df_wr_f.groupby("client_name").agg(
            Weeks=("week_date","nunique"),
            Employees=("employee_name","nunique"),
            Hours=("hours_worked","sum"),
        ).reset_index().rename(columns={"client_name":"Hotel"}).sort_values("Hours", ascending=False)
        st.dataframe(hrs_grp.round(1), use_container_width=True, hide_index=True)
        st.metric("Total Hours All Hotels", f"{total_hours:,.1f}")
    else:
        st.info("No timesheet records yet. Upload timesheets first.")

st.markdown("---")
st.caption("📊 Income & Costs from Zoho Books (bank reconciled)  |  Hours from timesheet uploads  •  ARVY Portal v1.0")
