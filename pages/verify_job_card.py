# pages/verify_job_card.py  (UPDATED — Light-mode friendly + still looks ok in dark)

def main():
    import streamlit as st
    from io import BytesIO

    from conn import Conn
    from job_card_pdf import build_job_card_pdf

    # -------------------------------------------------------------------------
    # Page Config
    # -------------------------------------------------------------------------
    st.set_page_config(page_title="Job Card Verification | Apricot", layout="centered")

    # -------------------------------------------------------------------------
    # Light-mode friendly CSS (also adapts in dark mode)
    # -------------------------------------------------------------------------
    st.markdown(
        """
        <style>
        /* Hide sidebar + Streamlit chrome */
        [data-testid="stSidebar"], header, footer {display:none !important;}
        .block-container {padding-top: 2rem; max-width: 800px;}

        /* Theme variables */
        :root{
            --card-bg: #ffffff;
            --card-border: rgba(15, 23, 42, 0.12);
            --text: #0f172a;
            --muted: rgba(15, 23, 42, 0.68);
            --soft: rgba(15, 23, 42, 0.06);
            --shadow: 0 10px 28px rgba(2, 6, 23, 0.08);

            --badge-bg: rgba(2, 132, 199, 0.10);
            --badge-text: #075985;

            --success-bg: rgba(34, 197, 94, 0.10);
            --success-border: rgba(34, 197, 94, 0.35);

            --warn-bg: rgba(245, 158, 11, 0.12);
            --warn-border: rgba(245, 158, 11, 0.38);
        }

        /* Dark mode overrides (keeps it readable if user switches) */
        @media (prefers-color-scheme: dark) {
            :root{
                --card-bg: rgba(255,255,255,0.06);
                --card-border: rgba(255,255,255,0.14);
                --text: rgba(255,255,255,0.92);
                --muted: rgba(255,255,255,0.62);
                --soft: rgba(255,255,255,0.06);
                --shadow: 0 10px 28px rgba(0,0,0,0.35);

                --badge-bg: rgba(56, 189, 248, 0.14);
                --badge-text: rgba(224, 242, 254, 0.92);

                --success-bg: rgba(34, 197, 94, 0.12);
                --success-border: rgba(34, 197, 94, 0.35);

                --warn-bg: rgba(245, 158, 11, 0.14);
                --warn-border: rgba(245, 158, 11, 0.40);
            }
        }

        /* Card */
        .ap-card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 14px;
            padding: 18px 18px 14px 18px;
            box-shadow: var(--shadow);
        }

        .ap-muted { color: var(--muted); }

        /* Badge */
        .ap-badge {
            display:inline-block;
            padding: 4px 10px;
            border-radius: 999px;
            font-size: 0.82rem;
            font-weight: 700;
            text-transform: uppercase;
            background: var(--badge-bg);
            color: var(--badge-text);
            border: 1px solid rgba(2,132,199,0.20);
        }

        /* Buttons */
        .stButton button {
            border-radius: 10px !important;
            font-weight: 700 !important;
        }

        /* Metrics look a bit cleaner */
        [data-testid="stMetricValue"] { color: var(--text) !important; }
        [data-testid="stMetricLabel"] { color: var(--muted) !important; }

        /* Make captions readable in light mode */
        .stCaption { color: var(--muted) !important; }

        /* Inputs */
        input, textarea {
            border-radius: 10px !important;
        }

        /* Expander header contrast */
        [data-testid="stExpander"] {
            border-radius: 12px;
            border: 1px solid var(--card-border);
            overflow: hidden;
        }

        /* Divider spacing */
        hr { margin: 1rem 0 !important; }
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

    # -------------------------
    # UI Header
    # -------------------------
    top_l, top_r = st.columns([1, 2])
    with top_l:
        try:
            st.image("logo1.png", width=140)
        except Exception:
            st.subheader("Apricot")
    with top_r:
        st.markdown("<div class='ap-muted' style='text-align:right;'>Verification Portal</div>", unsafe_allow_html=True)

    st.title("Job Card Verification")
    st.divider()

    # -------------------------
    # PUBLIC SECTION (Always Visible) — in a light card
    # -------------------------
    with st.container():
        st.markdown("<div class='ap-card'>", unsafe_allow_html=True)

        c1, c2, c3 = st.columns(3)
        with c1:
            st.caption("Job Card ID")
            st.markdown(f"**#{jc.get('id')}**")
        with c2:
            st.caption("Current Status")
            status = _safe(jc.get("status"))
            st.markdown(f"<span class='ap-badge'>{status}</span>", unsafe_allow_html=True)
        with c3:
            st.caption("Ticket Reference")
            ticket_ref = jc.get("ticket_id")
            st.markdown(f"**#{ticket_ref}**" if ticket_ref else "**Standalone**")

        st.markdown("<hr/>", unsafe_allow_html=True)

        col_left, col_right = st.columns(2)
        with col_left:
            st.markdown("##### 📍 Location")
            st.write(f"**Property:** {_safe(jc.get('property_name'))}")
            st.write(f"**Unit:** {_safe(jc.get('unit_number'))}")

        with col_right:
            st.markdown("##### 📝 Scope of Work")
            st.write(_safe(jc.get("description")))

        st.markdown("</div>", unsafe_allow_html=True)

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
            <div class="ap-card" style="border-left:6px solid rgba(34, 197, 94, 0.65);">
                <div style="font-weight:800; margin-bottom:6px;">Signed ✅</div>
                <div><b>Signed by:</b> {_safe(signoff.get('signed_by_name'))} ({_safe(signoff.get('signed_by_role'))})</div>
                <div><b>Date:</b> {_safe(signoff.get('signed_at'))}</div>
                <div><b>Notes:</b> {_safe(signoff.get('signoff_notes'))}</div>
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

    # IMPORTANT: pass the public URL so the QR appears on the PDF (job_card_pdf.py)
    # Use the exact WhatsApp link format you send.
    base = st.secrets.get("PUBLIC_BASE_URL", "https://ticketingapricot.streamlit.app").rstrip("/")
    public_url = f"{base}/?page=verify_job_card&id={jc_id_int}&t={token}"

    pdf_bytes = build_job_card_pdf(
        job_card=jc,
        signoff=signoff,
        attachments=attachments_list,
        brand_title="Apricot Property Solutions",
        logo_path="logo1.png",
        public_verify_url=public_url,  # ✅ QR ON PDF
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


if __name__ == "__main__":
    main()
