import streamlit as st

st.set_page_config(
    page_title="ARVY Portal",
    page_icon="🏨",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🏨 ARVY Hospitality Solutions Ltd")
st.markdown("### Staff & Finance Portal")
st.markdown("---")

st.markdown("""
Welcome to the ARVY Portal. Use the sidebar to navigate.

| Page | What it does |
|------|-------------|
| 👥 Employees | Upload, add, remove, assign to hotels |
| 🏨 Clients | View and manage hotels |
| 📋 Timesheets | Upload weekly hours per employee |
| ⚖️ Hour Disposal | Split hours: payroll / self-emp / UTR |
| 💼 Payroll Upload | Upload payroll PDF each week |
| 🤝 Self-Emp Upload | Upload self-employed payment sheet |
| 📝 UTR Upload | Upload UTR payment sheet |
| 💰 Invoices | Upload client income invoices |
| 🔍 Search | Search any employee — full history |
| 📊 Reports | Weekly / monthly / yearly P&L |
""")

st.info("👈 Start with **Employees** in the sidebar to upload your staff list.")
