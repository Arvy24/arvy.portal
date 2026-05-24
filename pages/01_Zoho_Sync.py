import streamlit as st
import requests
from db import page_header

st.set_page_config(page_title="Zoho Connect", page_icon="🔗", layout="wide")
page_header("🔗 Zoho Books Connection", "Connect your Zoho Books account to the ARVY Portal")

ZOHO_CLIENT_ID     = "1000.GSW0VNVRO1JTNIWGLL9VMTUIK9FK1M"
ZOHO_CLIENT_SECRET = "65462c0bc2c2504afd4626aeb2c6dfd66125870734"
ZOHO_REDIRECT_URI  = "https://arvy-app-xjrhprbsbcngmmjvhr7jqt.streamlit.app/Zoho_Connect"
ZOHO_TOKEN_URL     = "https://accounts.zoho.eu/oauth/v2/token"
ZOHO_SCOPES        = "ZohoBooks.invoices.READ,ZohoBooks.bills.READ,ZohoBooks.expenses.READ,ZohoBooks.contacts.READ,ZohoBooks.settings.READ"

ZOHO_AUTH_URL = (
    f"https://accounts.zoho.eu/oauth/v2/auth"
    f"?scope={ZOHO_SCOPES}"
    f"&client_id={ZOHO_CLIENT_ID}"
    f"&response_type=code"
    f"&access_type=offline"
    f"&prompt=consent"
    f"&redirect_uri={ZOHO_REDIRECT_URI}"
)

# Already connected check
already_connected = False
try:
    _ = st.secrets["ZOHO_REFRESH_TOKEN"]
    already_connected = True
except Exception:
    pass

if already_connected:
    st.success("✅ Zoho Books is already connected!")
    st.info("Your refresh token is saved in Streamlit secrets. Use the Zoho Sync page to pull data.")
    st.stop()

# Get code from URL only ONCE using session state
params = st.query_params
incoming_code = params.get("code", None)

if incoming_code and "zoho_code" not in st.session_state:
    st.session_state.zoho_code = incoming_code
    st.query_params.clear()

# Show connect button if no code captured yet
if "zoho_code" not in st.session_state:
    st.markdown("### Connect Your Zoho Books Account")
    st.markdown("Click below — you'll be taken to Zoho to approve access, then brought back here automatically.")
    st.markdown("**Permissions:** Read Invoices · Read Bills · Read Expenses · Read Contacts")
    st.markdown("---")
    st.link_button("🔗 Connect to Zoho Books", ZOHO_AUTH_URL, type="primary")
    st.stop()

# Exchange the code — show button so user controls timing
st.info(f"✅ Authorisation code received. Click below to complete the connection.")

if st.button("🔐 Complete Zoho Connection", type="primary"):
    with st.spinner("Connecting to Zoho Books..."):
        try:
            resp = requests.post(ZOHO_TOKEN_URL, data={
                "grant_type":    "authorization_code",
                "client_id":     ZOHO_CLIENT_ID,
                "client_secret": ZOHO_CLIENT_SECRET,
                "code":          st.session_state.zoho_code,
                "redirect_uri":  ZOHO_REDIRECT_URI,
            })
            data = resp.json()

            if "refresh_token" in data:
                refresh_token = data["refresh_token"]
                access_token  = data["access_token"]
                st.success("✅ Zoho Books connected!")
                st.balloons()

                secrets_text = f'ZOHO_REFRESH_TOKEN = "{refresh_token}"\n'

                # Get Org ID
                try:
                    org_resp = requests.get(
                        "https://books.zoho.eu/api/v3/organizations",
                        headers={"Authorization": f"Zoho-oauthtoken {access_token}"}
                    )
                    orgs = org_resp.json().get("organizations", [])
                    if orgs:
                        org_id   = orgs[0].get("organization_id","")
                        org_name = orgs[0].get("name","")
                        secrets_text += f'ZOHO_ORG_ID = "{org_id}"  # {org_name}\n'
                except Exception:
                    pass

                st.markdown("---")
                st.markdown("### ⚠️ Add These to Streamlit Secrets")
                st.markdown(
                    "1. Go to [Streamlit Cloud](https://share.streamlit.io)\n"
                    "2. Click **⋮** next to your app → **Settings** → **Secrets**\n"
                    "3. Copy and paste the block below into your secrets\n"
                    "4. Click **Save**"
                )
                st.code(secrets_text, language="toml")
                del st.session_state.zoho_code

            elif "access_token" in data:
                st.warning("Zoho returned an access token but no refresh token.")
                st.markdown("Please click below to reconnect and force Zoho to issue a refresh token:")
                st.link_button("🔄 Reconnect Now", ZOHO_AUTH_URL, type="primary")
                del st.session_state.zoho_code
            else:
                st.error(f"Connection failed: {data}")
                st.link_button("Try Again", ZOHO_AUTH_URL)
                del st.session_state.zoho_code

        except Exception as e:
            st.error(f"Error: {e}")
            st.link_button("Try Again", ZOHO_AUTH_URL)
