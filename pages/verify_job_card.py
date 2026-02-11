import streamlit as st
from io import BytesIO
from conn import Conn
from job_card_pdf import build_job_card_pdf

# -----------------------------------------------------------------------------
# Page Config & Custom Styling
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Job Card Verification | Apricot", layout="centered")

# Custom CSS for a modern "Card" feel and better typography
st.markdown("""
    <style>
    [data-testid="stSidebar"], header, footer {display:none !important;}
    .block-container {padding-top: 2rem; max-width: 800px;}
    
    /* Main Card Styling */
    .main-card {
        background-color: #f8f9fa;
        padding: 2rem;
        border-radius: 12px;
        border: 1px solid #e9ecef;
        margin-bottom: 2rem;
    }
    
    /* Status Badge Styling */
    .status-badge {
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.85rem;
        font-weight: 600;
        text-transform: uppercase;
        background-color: #e2e8f0;
        color: #475569;
    }
    
    .stButton button {
        border-radius: 8px;
        font-weight: 600;
    }
    </style>
    """, unsafe_allow_html=True)

db = Conn()

# -------------------------
# Helpers
# -------------------------
def _safe(v):
    return "—" if v is None or str(v).strip() == "" else str(v)

# -------------------------
# Data Loading & Logic
# -------------------------
qp = st.query_params
jc_id = qp.get("id", None)
token = qp.get("t", None)

if not jc_id or not token:
    st.error("### ⚠️ Invalid Link\nPlease ensure you have the correct URL provided by Apricot Property Solutions.")
    st.stop()

jc = db.get_job_card_public(int(jc_id), str(token))
if not jc:
    st.error("### ❌ Record Not Found\nThis job card may have been removed or the link has expired.")
    st.stop()

# -------------------------
# UI Header
# -------------------------
col1, col2 = st.columns([1, 2])
with col1:
    try:
        st.image("logo1.png", width=140)
    except:
        st.subheader("Apricot")
with col2:
    st.markdown(f"<div style='text-align: right; color: gray;'>Verification Portal</div>", unsafe_allow_html=True)

st.title("Job Card Verification")
st.divider()

# -------------------------
# PUBLIC SECTION (Always Visible)
# -------------------------
# Use columns for a "Dashboard" look
c1, c2, c3 = st.columns(3)
with c1:
    st.caption("Job Card ID")
    st.markdown(f"**#{jc.get('id')}**")
with c2:
    st.caption("Current Status")
    status = _safe(jc.get('status'))
    st.markdown(f"**{status}**")
with c3:
    st.caption("Ticket Reference")
    st.markdown(f"**{jc.get('ticket_id', 'Standalone')}**")

st.markdown("---")

# Main Property Info
with st.container():
    col_left, col_right = st.columns(2)
    with col_left:
        st.markdown("##### 📍 Location")
        st.write(f"**Property:** {_safe(jc.get('property_name'))}")
        st.write(f"**Unit:** {_safe(jc.get('unit_number'))}")
    
    with col_right:
        st.markdown("##### 📝 Scope of Work")
        st.write(_safe(jc.get("description")))

# -------------------------
# SECURITY GATE
# -------------------------
st.markdown("### 🔒 Private Details")
with st.expander("Verification Required", expanded=True):
    st.info("To view costs, signed documents, and photos, please verify your identity.")
    pin = st.text_input("Last 4 digits of your registered WhatsApp number", type="password", max_chars=4)
    
    unlock = False
    if pin and len(pin.strip()) == 4:
        unlock = db.verify_job_card_pin(int(jc_id), str(token), pin.strip())
        if not unlock:
            st.warning("The code entered does not match our records.")

if not unlock:
    st.stop()

# -------------------------
# UNLOCKED SECTION (Professional Layout)
# -------------------------
st.toast("Identity Verified", icon="✅")

# 1. Costs in a clean Metric layout
st.markdown("### Financial Summary")
m1, m2 = st.columns(2)
m1.metric("Estimated Cost", f"KES {jc.get('estimated_cost', 0):,.2f}" if jc.get('estimated_cost') else "—")
m2.metric("Actual Cost", f"KES {jc.get('actual_cost', 0):,.2f}" if jc.get('actual_cost') else "—")

# 2. Sign-off Details
st.markdown("### Sign-off Details")
signoff = db.get_job_card_signoff(int(jc_id))
if signoff:
    with st.container():
        st.markdown(f"""
        <div style="background-color: #f0fff4; padding: 15px; border-radius: 8px; border-left: 5px solid #38a169;">
            <strong>Signed by:</strong> {_safe(signoff.get('signed_by_name'))} ({_safe(signoff.get('signed_by_role'))})<br>
            <strong>Date:</strong> {_safe(signoff.get('signed_at'))}<br>
            <strong>Notes:</strong> {_safe(signoff.get('signoff_notes'))}
        </div>
        """, unsafe_allow_html=True)
else:
    st.info("Pending final sign-off.")

# 3. Attachments Gallery
st.markdown("### Project Media")
media_df = db.fetch_job_card_media(int(jc_id))
if media_df is not None and not media_df.empty:
    tabs = st.tabs(["Gallery", "Downloads"])
    
    with tabs[0]:
        cols = st.columns(3)
        for idx, row in media_df.reset_index(drop=True).iterrows():
            with cols[idx % 3]:
                if row.get("media_type") == "image":
                    st.image(BytesIO(row["media_blob"]), use_container_width=True)
                elif row.get("media_type") == "video":
                    st.video(BytesIO(row["media_blob"]))
    
    with tabs[1]:
        for idx, row in media_df.iterrows():
            st.download_button(f"📄 Download {row.get('filename', 'File')}", 
                             data=row["media_blob"], 
                             file_name=row.get("filename"),
                             key=f"dl_{idx}")
else:
    st.write("No media attachments available.")

# 4. Final Export
st.markdown("---")
attachments_list = [{"filename": r.get("filename", "attachment"), "media_type": r.get("media_type", "file")} 
                    for _, r in media_df.iterrows()] if media_df is not None else []

pdf_bytes = build_job_card_pdf(
    job_card=jc, signoff=signoff, attachments=attachments_list,
    brand_title="Apricot Property Solutions", logo_path="logo1.png"
)

st.download_button(
    "⬇️ Download Official Job Card (PDF)",
    data=pdf_bytes,
    file_name=f"JobCard_{jc_id}.pdf",
    mime="application/pdf",
    use_container_width=True,
    type="primary"
)