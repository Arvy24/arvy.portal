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
