import streamlit as st
import requests
from db import get_client, page_header

st.set_page_config(page_title="Zoho Connect", page_icon="🔗", layout="wide")
page_header("🔗 Zoho Books Connection", "Connect your Zoho Books account to the ARVY Portal")

ZOHO_CLIENT_ID     = "1000.GSW0VNVRO1JTNIWGLL9VMTUIK9FK1M"
ZOHO_CLIENT_SECRET = "65462c0bc2c2504afd4626aeb2c6dfd66125870734"
ZOHO_REDIRECT_URI  = "https://arvy-app-xjrhprbsbcngmmjvhr7jqt.streamlit.app/Zoho_Connect"
ZOHO_AUTH_URL      = (
    "https://accounts.zoho.eu/oauth/v2/auth"
    "?scope=ZohoBooks.invoices.READ,ZohoBooks.bills.READ,"
    "ZohoBooks.expenses.READ,ZohoBooks.contacts.READ,ZohoBooks.settings.READ"
    f"&client_id={ZOHO_CLIENT_ID}"
    "&response_type=code"
    "&access_type=offline"
    f"&redirect_uri={ZOHO_REDIRECT_URI}"
)
ZOHO_TOKEN_URL = "https://accounts.zoho.eu/oauth/v2/token"

# Check if we already have a refresh token in secrets
already_connected = False
try:
    _ = st.secrets["ZOHO_REFRESH_TOKEN"]
    already_connected = True
except Exception:
    pass

# Check if Zoho has redirected back with a code
params = st.query_params
code   = params.get("code", None)

if already_connected and not code:
    st.success("✅ Zoho Books is already connected!")
    st.info("Your Zoho Books account is linked. Use the **Zoho Sync** page to pull invoices and expenses.")
    if st.button("🔄 Reconnect Zoho Books"):
        st.markdown(f"[Click here to reconnect]({ZOHO_AUTH_URL})")
    st.stop()

if code:
    # Exchange code for tokens
    st.info("🔄 Exchanging authorisation code for tokens...")
    try:
        resp = requests.post(ZOHO_TOKEN_URL, data={
            "grant_type":    "authorization_code",
            "client_id":     ZOHO_CLIENT_ID,
            "client_secret": ZOHO_CLIENT_SECRET,
            "code":          code,
            "redirect_uri":  ZOHO_REDIRECT_URI,
        })
        data = resp.json()

        if "refresh_token" in data:
            refresh_token = data["refresh_token"]
            access_token  = data["access_token"]

            st.success("✅ Zoho Books connected successfully!")
            st.balloons()

            st.markdown("---")
            st.markdown("### ⚠️ Important — Save Your Refresh Token")
            st.markdown(
                "Copy the refresh token below and add it to your **Streamlit Cloud Secrets**. "
                "You only need to do this once."
            )

            st.code(f'ZOHO_REFRESH_TOKEN = "{refresh_token}"', language="toml")

            st.markdown("**Steps to save:**")
            st.markdown(
                "1. Go to [Streamlit Cloud](https://share.streamlit.io)\n"
                "2. Click ⋮ next to your app → **Settings** → **Secrets**\n"
                "3. Add the line above to your secrets\n"
                "4. Click **Save** — the app will redeploy\n"
                "5. Come back to this page — it will show Connected ✅"
            )

            # Also get Zoho Org ID
            st.markdown("---")
            st.markdown("### 🏢 Get Your Zoho Organisation ID")
            try:
                org_resp = requests.get(
                    "https://books.zoho.eu/api/v3/organizations",
                    headers={"Authorization": f"Zoho-oauthtoken {access_token}"}
                )
                orgs = org_resp.json().get("organizations", [])
                if orgs:
                    st.markdown("**Also add this to your Streamlit secrets:**")
                    for org in orgs:
                        org_id   = org.get("organization_id","")
                        org_name = org.get("name","")
                        st.code(f'ZOHO_ORG_ID = "{org_id}"  # {org_name}', language="toml")
                else:
                    st.warning("Could not fetch organisation ID. You may need to add it manually.")
            except Exception as e:
                st.warning(f"Could not fetch organisation: {e}")

        else:
            st.error(f"❌ Token exchange failed: {data}")
            st.markdown(f"[Try connecting again]({ZOHO_AUTH_URL})")

    except Exception as e:
        st.error(f"Error during token exchange: {e}")

else:
    # Show connect button
    st.markdown("### Connect Your Zoho Books Account")
    st.markdown(
        "Click the button below to securely log in to Zoho Books and grant the ARVY Portal "
        "read access to your invoices, bills and expenses."
    )
    st.markdown("**Permissions requested:**")
    st.markdown("- 📄 Read Invoices\n- 🧾 Read Bills\n- 💰 Read Expenses\n- 👥 Read Contacts\n- ⚙️ Read Settings")
    st.markdown("---")
    st.link_button("🔗 Connect to Zoho Books", ZOHO_AUTH_URL, type="primary")
    st.caption("You will be redirected to Zoho to log in and approve access. You will be brought back here automatically.")
