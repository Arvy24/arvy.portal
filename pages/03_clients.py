# ── Hotels / Clients page ────────────────────────────────────
import streamlit as st
import pandas as pd
from db import get_client

st.title("🏨 Hotels & Clients")
st.markdown("---")

db = get_client()

tab_view, tab_add = st.tabs(["📋 View All Hotels", "➕ Add New Hotel"])

with tab_view:
    try:
        rows = db.table("clients").select("*").order("dept_number").execute().data
        if rows:
            df = pd.DataFrame(rows)
            cols = ["dept_number","name","short_name","location","is_active"]
            df2  = df[[c for c in cols if c in df.columns]].copy()
            df2.columns = ["Dept No","Hotel Name","Short Name","Location","Active"]
            st.dataframe(df2, use_container_width=True, height=500)
            st.caption(f"{len(rows)} hotels loaded")

            st.markdown("---")
            st.subheader("✖ Deactivate Hotel")
            names   = [f"Dept {r.get('dept_number','?')} — {r['name']}" for r in rows]
            to_deact = st.selectbox("Select hotel", names)
            if st.button("Deactivate Hotel", type="secondary"):
                hotel_name = to_deact.split(" — ", 1)[1]
                db.table("clients").update({"is_active": False}) \
                  .eq("name", hotel_name).execute()
                st.success(f"✅ {hotel_name} deactivated.")
        else:
            st.info("No clients found.")
    except Exception as e:
        st.error(f"Error: {e}")

with tab_add:
    st.subheader("➕ Add a New Hotel / Client")
    with st.form("add_client"):
        c1, c2 = st.columns(2)
        with c1:
            dept = st.number_input("Dept Number (leave 0 if none)", min_value=0, step=1)
            name = st.text_input("Hotel Name *")
            short= st.text_input("Short Name",  placeholder="e.g. Royal")
        with c2:
            loc  = st.text_input("Location",    placeholder="e.g. London")
        sub = st.form_submit_button("Add Hotel", type="primary")
    if sub:
        if not name:
            st.error("Hotel name is required.")
        else:
            try:
                db.table("clients").insert({
                    "dept_number": int(dept) if dept else None,
                    "name":        name.strip(),
                    "short_name":  short or None,
                    "location":    loc   or None,
                    "is_active":   True,
                }).execute()
                st.success(f"✅ {name} added successfully.")
            except Exception as e:
                st.error(f"Error: {e}")
