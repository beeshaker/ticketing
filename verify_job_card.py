# pages/verify_job_card.py
import streamlit as st
from io import BytesIO

from conn import Conn
from job_card_pdf import build_job_card_pdf

st.set_page_config(page_title="Job Card Verification", layout="centered")

db = Conn()

# -------------------------
# Helpers
# -------------------------
def _mask_phone(phone: str) -> str:
    if not phone:
        return "—"
    s = str(phone)
    if len(s) <= 4:
        return "****"
    return f"{s[:-4]}****"

def _safe(v):
    return "—" if v is None or str(v).strip() == "" else str(v)

# -------------------------
# Read query params
# URL: /verify_job_card?id=184&t=<token>
# -------------------------
qp = st.query_params
jc_id = qp.get("id", None)
token = qp.get("t", None)

# Branding (optional)
try:
    st.image("logo1.png", width=160)
except Exception:
    pass

st.title("✅ Job Card Verification")
st.caption("Apricot Property Solutions")

if not jc_id or not token:
    st.error("Invalid verification link.")
    st.stop()

try:
    jc_id_int = int(jc_id)
except Exception:
    st.error("Invalid verification link.")
    st.stop()

# -------------------------
# Load job card by token
# -------------------------
jc = db.get_job_card_public(jc_id_int, str(token))
if not jc:
    st.error("Invalid verification link.")
    st.stop()

# Minimal always-visible info (SAFE)
st.markdown(f"### Job Card #{jc['id']}")
st.write(f"**Status:** {_safe(jc.get('status'))}")
st.write(f"**Ticket:** {f'#{jc.get('ticket_id')}' if jc.get('ticket_id') else 'Standalone'}")
st.write(f"**Property:** {_safe(jc.get('property_name'))}")
st.write(f"**Unit:** {_safe(jc.get('unit_number'))}")

st.markdown("### Description")
st.write(_safe(jc.get("description")))

st.markdown("### Protected details")
st.caption("Enter the last 4 digits of your WhatsApp number to unlock costs, attachments, and the signed job card PDF.")

# -------------------------
# Password gate (NO wrong password message)
# -------------------------
pin = st.text_input("Verification code", type="password", max_chars=4, placeholder="Last 4 digits")

unlock = False
if pin and len(pin.strip()) == 4:
    unlock = db.verify_job_card_pin(jc_id_int, str(token), pin.strip())

# If not unlocked: show nothing else, no error text
if not unlock:
    st.stop()

# -------------------------
# UNLOCKED SECTION
# -------------------------
st.success("Unlocked ✅")

st.markdown("### Costs")
st.write(f"**Estimated Cost:** {jc.get('estimated_cost') if jc.get('estimated_cost') is not None else '—'}")
st.write(f"**Actual Cost:** {jc.get('actual_cost') if jc.get('actual_cost') is not None else '—'}")

# Signoff
signoff = db.get_job_card_signoff(jc_id_int)
st.markdown("### Sign-off")
if signoff:
    st.write(f"**Signed by:** {_safe(signoff.get('signed_by_name'))} ({_safe(signoff.get('signed_by_role'))})")
    st.write(f"**Signed at:** {_safe(signoff.get('signed_at'))}")
    if signoff.get("signoff_notes"):
        st.write(f"**Notes:** {signoff.get('signoff_notes')}")
else:
    st.info("Not yet signed off.")

# Attachments
st.markdown("### Attachments")
media_df = db.fetch_job_card_media(jc_id_int)
if media_df is None or media_df.empty:
    st.info("No attachments.")
else:
    cols = st.columns(3)
    for idx, row in media_df.reset_index(drop=True).iterrows():
        with cols[idx % 3]:
            m_type = row.get("media_type")
            blob = row.get("media_blob")
            fname = row.get("filename") or "attachment"
            st.caption(fname)
            if m_type == "image":
                st.image(BytesIO(blob), use_container_width=True)
            elif m_type == "video":
                st.video(BytesIO(blob))
            else:
                st.download_button("Download", data=blob, file_name=fname, key=f"dl_pub_{jc_id_int}_{idx}")

# PDF download
st.divider()
st.markdown("### Download PDF")

attachments_list = []
if media_df is not None and not media_df.empty:
    for _, r in media_df.iterrows():
        attachments_list.append({"filename": r.get("filename", "attachment"), "media_type": r.get("media_type", "file")})

pdf_bytes = build_job_card_pdf(
    job_card=jc,
    signoff=signoff,
    attachments=attachments_list,
    brand_title="Apricot Property Solutions",
    logo_path="logo1.png",
)

st.download_button(
    "⬇️ Download Job Card PDF",
    data=pdf_bytes,
    file_name=f"job_card_{jc_id_int}.pdf",
    mime="application/pdf",
    use_container_width=True,
    key=f"pub_pdf_{jc_id_int}",
)
