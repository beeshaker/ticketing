# pages/verify_job_card.py  (FULL UPDATED — with main() wrapper for safe import)

def main():
    import streamlit as st
    from io import BytesIO
    import qrcode  # ✅ requirements.txt: qrcode[pil]
    from conn import Conn
    from job_card_pdf import build_job_card_pdf

    # -----------------------------------------------------------------------------
    # Page Config & Custom Styling
    # -----------------------------------------------------------------------------
    st.set_page_config(page_title="Job Card Verification | Apricot", layout="centered")

    st.markdown(
        """
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
        """,
        unsafe_allow_html=True,
    )

    db = Conn()

    # -------------------------
    # Helpers
    # -------------------------
    def _safe(v):
        return "—" if v is None or str(v).strip() == "" else str(v)

    def _build_public_verify_url(jc_id_int: int, token: str) -> str:
        """
        Build the EXACT same URL you share on WhatsApp.
        Use query-param router (most reliable on Streamlit Cloud).
        """
        base = st.secrets.get("PUBLIC_BASE_URL", "https://ticketingapricot.streamlit.app").rstrip("/")
        return f"{base}/?page=verify_job_card&id={jc_id_int}&t={token}"

    def _qr_png_bytes(data: str) -> bytes:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=7,
            border=2,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    # -------------------------
    # Data Loading & Logic
    # -------------------------
    qp = st.query_params
    jc_id = qp.get("id", None)
    token = qp.get("t", None)

    if not jc_id or not token:
        st.error("### ⚠️ Invalid Link\nPlease ensure you have the correct URL provided by Apricot Property Solutions.")
        st.stop()

    try:
        jc_id_int = int(str(jc_id).strip())
    except Exception:
        st.error("### ⚠️ Invalid Link\nThe job card reference is not valid.")
        st.stop()

    jc = db.get_job_card_public(jc_id_int, str(token))
    if not jc:
        st.error("### ❌ Record Not Found\nThis job card may have been removed or the link has expired.")
        st.stop()

    # Build the WhatsApp/public URL + QR (same link)
    public_url = _build_public_verify_url(jc_id_int, str(token))
    qr_bytes = _qr_png_bytes(public_url)

    # -------------------------
    # UI Header
    # -------------------------
    col1, col2 = st.columns([1, 2])
    with col1:
        try:
            st.image("logo1.png", width=140)
        except Exception:
            st.subheader("Apricot")
    with col2:
        st.markdown("<div style='text-align: right; color: gray;'>Verification Portal</div>", unsafe_allow_html=True)

    st.title("Job Card Verification")
    st.divider()

    # -------------------------
    # QR code block (PUBLIC)
    # -------------------------
    with st.container():
        q1, q2 = st.columns([1, 2.2])
        with q1:
            st.image(qr_bytes, width=170)
        with q2:
            st.markdown("### 📲 Scan to open this Job Card")
            st.caption("This QR code opens the same verification link shared on WhatsApp.")
            st.code(public_url, language="text")  # copy/paste fallback

    st.markdown("---")

    # -------------------------
    # PUBLIC SECTION (Always Visible)
    # -------------------------
    c1, c2, c3 = st.columns(3)
    with c1:
        st.caption("Job Card ID")
        st.markdown(f"**#{jc.get('id')}**")
    with c2:
        st.caption("Current Status")
        status = _safe(jc.get("status"))
        st.markdown(f"**{status}**")
    with c3:
        st.caption("Ticket Reference")
        ticket_ref = jc.get("ticket_id")
        st.markdown(f"**#{ticket_ref}**" if ticket_ref else "**Standalone**")

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
            unlock = db.verify_job_card_pin(jc_id_int, str(token), pin.strip())
            if not unlock:
                st.warning("The code entered does not match our records.")

    if not unlock:
        st.stop()

    # -------------------------
    # UNLOCKED SECTION
    # -------------------------
    st.toast("Identity Verified", icon="✅")

    # 1) Costs
    st.markdown("### Financial Summary")
    m1, m2 = st.columns(2)
    m1.metric(
        "Estimated Cost",
        f"KES {float(jc.get('estimated_cost')):,.2f}" if jc.get("estimated_cost") is not None else "—",
    )
    m2.metric(
        "Actual Cost",
        f"KES {float(jc.get('actual_cost')):,.2f}" if jc.get("actual_cost") is not None else "—",
    )

    # 2) Signoff
    st.markdown("### Sign-off Details")
    signoff = db.get_job_card_signoff(jc_id_int)
    if signoff:
        st.markdown(
            f"""
            <div style="background-color: #f0fff4; padding: 15px; border-radius: 8px; border-left: 5px solid #38a169;">
                <strong>Signed by:</strong> {_safe(signoff.get('signed_by_name'))} ({_safe(signoff.get('signed_by_role'))})<br>
                <strong>Date:</strong> {_safe(signoff.get('signed_at'))}<br>
                <strong>Notes:</strong> {_safe(signoff.get('signoff_notes'))}
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.info("Pending final sign-off.")

    # 3) Attachments
    st.markdown("### Project Media")
    media_df = db.fetch_job_card_media(jc_id_int)

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
                st.download_button(
                    f"📄 Download {row.get('filename', 'File')}",
                    data=row["media_blob"],
                    file_name=row.get("filename") or "attachment",
                    key=f"dl_{jc_id_int}_{idx}",
                    use_container_width=True,
                )
    else:
        st.write("No media attachments available.")

    # 4) PDF Export
    st.markdown("---")

    attachments_list = []
    if media_df is not None and not media_df.empty:
        attachments_list = [
            {"filename": r.get("filename", "attachment"), "media_type": r.get("media_type", "file")}
            for _, r in media_df.iterrows()
        ]

    pdf_bytes = build_job_card_pdf(
        job_card=jc,
        signoff=signoff,
        attachments=attachments_list,
        brand_title="Apricot Property Solutions",
        logo_path="logo1.png",
    )

    st.download_button(
        "⬇️ Download Official Job Card (PDF)",
        data=pdf_bytes,
        file_name=f"JobCard_{jc_id_int}.pdf",
        mime="application/pdf",
        use_container_width=True,
        type="primary",
        key=f"dl_pdf_{jc_id_int}",
    )

    # Optional: download QR
    with st.expander("Download QR code"):
        st.download_button(
            "⬇️ Download QR (PNG)",
            data=qr_bytes,
            file_name=f"job_card_{jc_id_int}_qr.png",
            mime="image/png",
            use_container_width=True,
            key=f"dl_qr_{jc_id_int}",
        )


# Allow running directly (optional)
if __name__ == "__main__":
    main()
