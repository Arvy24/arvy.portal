import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from db import get_client, page_header

st.set_page_config(page_title="Reports", page_icon="📊", layout="wide")
page_header("📊 Reports Dashboard", "Weekly, monthly and yearly P&L by hotel and company-wide")

supabase = get_client()

@st.cache_data(ttl=120)
def load_pl():
    return supabase.table("v_weekly_pl").select("*").execute().data or []

if st.sidebar.button("🔄 Refresh Data"):
    load_pl.clear()
    st.rerun()

pl_data = load_pl()

if not pl_data:
    st.warning("No P&L data yet. Upload timesheets, payments and invoices first.")
    st.stop()

df = pd.DataFrame(pl_data)
df["week_ending"]    = pd.to_datetime(df["week_ending"])
df["income_net"]     = pd.to_numeric(df["income_net"],     errors="coerce").fillna(0)
df["payroll_cost"]   = pd.to_numeric(df["payroll_cost"],   errors="coerce").fillna(0)
df["self_emp_cost"]  = pd.to_numeric(df["self_emp_cost"],  errors="coerce").fillna(0)
df["utr_cost"]       = pd.to_numeric(df["utr_cost"],       errors="coerce").fillna(0)
df["other_expenses"] = pd.to_numeric(df["other_expenses"], errors="coerce").fillna(0)
df["gross_profit"]   = pd.to_numeric(df["gross_profit"],   errors="coerce").fillna(0)
df["total_cost"]     = df["payroll_cost"] + df["self_emp_cost"] + df["utr_cost"] + df["other_expenses"]
df["month"]          = df["week_ending"].dt.to_period("M").astype(str)
df["year"]           = df["week_ending"].dt.year
df_active            = df[(df["income_net"] > 0) | (df["total_cost"] > 0)]

st.sidebar.header("Filters")
report_type  = st.sidebar.radio("Report Period", ["Weekly", "Monthly", "Yearly", "All Time"])
all_hotels   = ["All Hotels"] + sorted(df["client"].dropna().unique().tolist())
hotel_filter = st.sidebar.selectbox("Hotel", all_hotels)
all_years    = sorted(df["year"].unique().tolist(), reverse=True)
year_filter  = st.sidebar.selectbox("Year", ["All"] + [str(y) for y in all_years])
st.sidebar.markdown("---")

df_f = df_active.copy()
if hotel_filter != "All Hotels":
    df_f = df_f[df_f["client"] == hotel_filter]
if year_filter != "All":
    df_f = df_f[df_f["year"] == int(year_filter)]

tab_pl, tab_hotel, tab_trend, tab_breakdown = st.tabs([
    "P&L Table", "By Hotel", "Trends", "Cost Breakdown"
])

with tab_pl:
    st.subheader("Profit and Loss Table")
    if report_type == "Weekly":
        grp = df_f.groupby(["week_ending", "client"]).agg(
            Income=("income_net", "sum"), Payroll=("payroll_cost", "sum"),
            SelfEmp=("self_emp_cost", "sum"), UTR=("utr_cost", "sum"),
            Other=("other_expenses", "sum"), Profit=("gross_profit", "sum")
        ).reset_index()
        grp["week_ending"] = grp["week_ending"].dt.strftime("%Y-%m-%d")
        grp.rename(columns={"week_ending": "Week", "client": "Hotel"}, inplace=True)
    elif report_type == "Monthly":
        grp = df_f.groupby(["month", "client"]).agg(
            Income=("income_net", "sum"), Payroll=("payroll_cost", "sum"),
            SelfEmp=("self_emp_cost", "sum"), UTR=("utr_cost", "sum"),
            Other=("other_expenses", "sum"), Profit=("gross_profit", "sum")
        ).reset_index()
        grp.rename(columns={"month": "Month", "client": "Hotel"}, inplace=True)
    elif report_type == "Yearly":
        grp = df_f.groupby(["year", "client"]).agg(
            Income=("income_net", "sum"), Payroll=("payroll_cost", "sum"),
            SelfEmp=("self_emp_cost", "sum"), UTR=("utr_cost", "sum"),
            Other=("other_expenses", "sum"), Profit=("gross_profit", "sum")
        ).reset_index()
        grp.rename(columns={"year": "Year", "client": "Hotel"}, inplace=True)
    else:
        grp = df_f.groupby("client").agg(
            Income=("income_net", "sum"), Payroll=("payroll_cost", "sum"),
            SelfEmp=("self_emp_cost", "sum"), UTR=("utr_cost", "sum"),
            Other=("other_expenses", "sum"), Profit=("gross_profit", "sum")
        ).reset_index()
        grp.rename(columns={"client": "Hotel"}, inplace=True)

    grp = grp.round(2)
    st.dataframe(grp, use_container_width=True, hide_index=True)
    st.markdown("---")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Income",   f"£{grp['Income'].sum():,.2f}")
    c2.metric("Total Payroll",  f"£{grp['Payroll'].sum():,.2f}")
    c3.metric("Total Self-Emp", f"£{grp['SelfEmp'].sum():,.2f}")
    c4.metric("Total UTR",      f"£{grp['UTR'].sum():,.2f}")
    profit_total = grp["Profit"].sum()
    margin = profit_total / max(grp["Income"].sum(), 1) * 100
    c5.metric("Gross Profit", f"£{profit_total:,.2f}", delta=f"{margin:.1f}% margin")
    st.download_button("Download as CSV", grp.to_csv(index=False).encode(),
        f"ARVY_PL_{report_type}.csv", "text/csv")

with tab_hotel:
    st.subheader("Performance by Hotel")
    hotel_summary = df_f.groupby("client").agg(
        Weeks=("week_ending", "nunique"),
        Income=("income_net", "sum"),
        Total_Cost=("total_cost", "sum"),
        Profit=("gross_profit", "sum"),
    ).reset_index()
    hotel_summary["Margin_pct"] = (
        hotel_summary["Profit"] / hotel_summary["Income"].replace(0, 1) * 100
    ).round(1)
    hotel_summary = hotel_summary.sort_values("Profit", ascending=False).reset_index(drop=True)
    hotel_summary.rename(columns={"client": "Hotel"}, inplace=True)
    fig_bar = px.bar(hotel_summary, x="Hotel", y="Profit", color="Profit",
        color_continuous_scale=["#e74c3c", "#f39c12", "#27ae60"],
        title="Gross Profit by Hotel",
        text=hotel_summary["Profit"].apply(lambda x: f"£{x:,.0f}"))
    fig_bar.update_layout(plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        font_color="#1C2B3A", showlegend=False, xaxis_tickangle=-45)
    fig_bar.update_traces(textposition="outside")
    st.plotly_chart(fig_bar, use_container_width=True)
    st.dataframe(hotel_summary.round(2), use_container_width=True, hide_index=True)

with tab_trend:
    st.subheader("Trends")
    if report_type in ["Weekly", "All Time"]:
        trend = df_f.groupby("week_ending").agg(
            Income=("income_net", "sum"),
            Total_Cost=("total_cost", "sum"),
            Profit=("gross_profit", "sum")
        ).reset_index()
        trend["week_ending"] = trend["week_ending"].dt.strftime("%Y-%m-%d")
        x_col = "week_ending"
        x_label = "Week Ending"
    elif report_type == "Monthly":
        trend = df_f.groupby("month").agg(
            Income=("income_net", "sum"),
            Total_Cost=("total_cost", "sum"),
            Profit=("gross_profit", "sum")
        ).reset_index()
        x_col = "month"
        x_label = "Month"
    else:
        trend = df_f.groupby("year").agg(
            Income=("income_net", "sum"),
            Total_Cost=("total_cost", "sum"),
            Profit=("gross_profit", "sum")
        ).reset_index()
        x_col = "year"
        x_label = "Year"
    fig_line = go.Figure()
    fig_line.add_trace(go.Scatter(x=trend[x_col], y=trend["Income"],
        mode="lines+markers", name="Income", line=dict(color="#1B4F8A", width=2)))
    fig_line.add_trace(go.Scatter(x=trend[x_col], y=trend["Total_Cost"],
        mode="lines+markers", name="Total Cost", line=dict(color="#e74c3c", width=2)))
    fig_line.add_trace(go.Scatter(x=trend[x_col], y=trend["Profit"],
        mode="lines+markers", name="Gross Profit", line=dict(color="#27ae60", width=2)))
    fig_line.update_layout(title=f"Income vs Cost vs Profit by {x_label}",
        xaxis_title=x_label, yaxis_title="Amount (£)",
        plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        font_color="#1C2B3A", hovermode="x unified",
        legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig_line, use_container_width=True)

with tab_breakdown:
    st.subheader("Cost Breakdown")
    totals = {
        "Payroll":  float(df_f["payroll_cost"].sum()),
        "Self-Emp": float(df_f["self_emp_cost"].sum()),
        "UTR":      float(df_f["utr_cost"].sum()),
        "Other":    float(df_f["other_expenses"].sum()),
    }
    totals = {k: v for k, v in totals.items() if v > 0}
    if totals:
        c1, c2 = st.columns(2)
        with c1:
            fig_pie = px.pie(names=list(totals.keys()), values=list(totals.values()),
                title="Cost Split",
                color_discrete_sequence=["#1B4F8A", "#2E6DB4", "#5B9BD5", "#95B8D1"],
                hole=0.4)
            fig_pie.update_layout(plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
                font_color="#1C2B3A")
            st.plotly_chart(fig_pie, use_container_width=True)
        with c2:
            total_cost   = sum(totals.values())
            total_income = float(df_f["income_net"].sum())
            total_profit = float(df_f["gross_profit"].sum())
            margin       = total_profit / max(total_income, 1) * 100
            st.markdown("### Summary")
            st.metric("Total Income",  f"£{total_income:,.2f}")
            st.metric("Total Cost",    f"£{total_cost:,.2f}")
            st.metric("Gross Profit",  f"£{total_profit:,.2f}")
            st.metric("Profit Margin", f"{margin:.1f}%")
            st.markdown("---")
            for k, v in totals.items():
                pct = v / max(total_cost, 1) * 100
                st.markdown(f"**{k}:** £{v:,.2f} ({pct:.1f}% of costs)")
    else:
        st.info("No cost data available for the selected filters.")

st.markdown("---")
st.caption("Data pulled live from Supabase - ARVY Portal v1.0")
