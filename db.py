import streamlit as st
from supabase import create_client, Client

@st.cache_resource
def get_client() -> Client:
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
    except Exception:
        st.error("⚠️ Supabase credentials not found. "
                 "Add SUPABASE_URL and SUPABASE_KEY in Streamlit Cloud secrets.")
        st.stop()
    return create_client(url, key)


def apply_style():
    st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #1B4F8A 0%, #2E6DB4 100%);
        padding: 1.2rem 1.8rem;
        border-radius: 10px;
        margin-bottom: 1.5rem;
    }
    .main-header h1 { color: white !important; font-size: 1.8rem; margin: 0; font-weight: 700; }
    .main-header p  { color: #C8DEFF !important; margin: 0.3rem 0 0 0; font-size: 0.95rem; }

    div[data-testid="metric-container"] {
        background: #EEF2F7;
        border: 1px solid #D0DFF0;
        border-left: 4px solid #1B4F8A;
        border-radius: 8px;
        padding: 1rem;
    }
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
    .stButton button[kind="primary"] {
        background-color: #1B4F8A !important;
        border-radius: 6px !important;
    }
    div[data-testid="stDataFrame"] {
        border: 1px solid #D0DFF0;
        border-radius: 8px;
    }
    footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


def page_header(title: str, subtitle: str = ""):
    apply_style()
    sub_html = f"<p>{subtitle}</p>" if subtitle else ""
    st.markdown(f"""
<div class="main-header">
    <h1>{title}</h1>
    {sub_html}
</div>
""", unsafe_allow_html=True)
