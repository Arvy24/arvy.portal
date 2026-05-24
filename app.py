import streamlit as st

st.set_page_config(
    page_title="ARVY Portal",
    page_icon="🏨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    /* Header bar */
    .main-header {
        background: linear-gradient(90deg, #1B4F8A 0%, #2E6DB4 100%);
        padding: 1.5rem 2rem;
        border-radius: 10px;
        margin-bottom: 1.5rem;
        color: white;
    }
    .main-header h1 {
        color: white !important;
        font-size: 2rem;
        margin: 0;
        font-weight: 700;
    }
    .main-header p {
        color: #C8DEFF !important;
        margin: 0.3rem 0 0 0;
        font-size: 1rem;
    }

    /* Metric cards */
    div[data-testid="metric-container"] {
        background: #EEF2F7;
        border: 1px solid #D0DFF0;
        border-left: 4px solid #1B4F8A;
        border-radius: 8px;
        padding: 1rem;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #1C2B3A !important;
    }
    section[data-testid="stSidebar"] * {
        color: #E8EFF8 !important;
    }
    section[data-testid="stSidebar"] .stButton button {
        background-color: #1B4F8A !important;
        color: white !important;
        border: none;
        border-radius: 6px;
        width: 100%;
    }

    /* Nav cards */
    .nav-card {
        background: #EEF2F7;
        border: 1px solid #D0DFF0;
        border-left: 4px solid #1B4F8A;
        border-radius: 8px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.7rem;
    }
    .nav-card h4 { margin: 0 0 0.2rem 0; color: #1B4F8A; }
    .nav-card p  { margin: 0; font-size: 0.85rem; color: #4A5568; }

    /* Primary buttons */
    .stButton button[kind="primary"] {
        background-color: #1B4F8A !important;
        border-radius: 6px !important;
    }

    /* Hide default Streamlit footer */
    footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# Header
st.markdown("""
<div class="main-header">
    <h1>🏨 ARVY Hospitality Solutions Ltd</h1>
    <p>Staff & Finance Management Portal</p>
</div>
""", unsafe_allow_html=True)

# Welcome message
st.markdown("### Welcome, Raj 👋")
st.markdown("Use the **sidebar** to navigate between sections of the portal.")
st.markdown("---")

# Navigation cards
col1, col2 = st.columns(2)

with col1:
    st.markdown('<div class="nav-card"><h4>👥 Employees</h4><p>Add, search, and manage staff records. Bulk upload via CSV.</p></div>', unsafe_allow_html=True)
    st.markdown('<div class="nav-card"><h4>📋 Timesheets</h4><p>Upload weekly client timesheets and record employee hours.</p></div>', unsafe_allow_html=True)
    st.markdown('<div class="nav-card"><h4>💷 Payments</h4><p>Upload payroll, self-employed, and UTR payment records.</p></div>', unsafe_allow_html=True)
    st.markdown('<div class="nav-card"><h4>🏨 Clients</h4><p>View and manage hotel clients and their details.</p></div>', unsafe_allow_html=True)

with col2:
    st.markdown('<div class="nav-card"><h4>⏱️ Hour Disposal</h4><p>Split employee hours into payroll, self-emp, and UTR categories.</p></div>', unsafe_allow_html=True)
    st.markdown('<div class="nav-card"><h4>🧾 Invoices</h4><p>Upload and track client invoices and income records.</p></div>', unsafe_allow_html=True)
    st.markdown('<div class="nav-card"><h4>🔍 Employee Search</h4><p>Find any employee and view their full payment history.</p></div>', unsafe_allow_html=True)
    st.markdown('<div class="nav-card"><h4>📊 Reports</h4><p>Weekly, monthly, and yearly P&L reports by hotel.</p></div>', unsafe_allow_html=True)

st.markdown("---")
st.caption("ARVY Hospitality Solutions Ltd  •  Portal v1.0  •  admin@arvy24.co.uk")
