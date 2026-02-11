import streamlit as st
import pandas as pd
from io import BytesIO

def job_cards_page(db):
    st.title("🧾 Job Cards")

    tabs = st.tabs(["➕ Create Job Card", "📋 Manage Job Cards"])

    # ---------------------------------------------------------------------
    # TAB 1: CREATE
    # ---------------------------------------------------------------------
    with tabs[0]:
        st.subheader("Create Job Card")

        link_mode = st.radio("Create mode", ["From Ticket", "Standalone"], horizontal=True)

        admin_users = db.fetch_admin_users()
        admin_options = {a["id"]: a["name"] for a in admin_users}

        if link_mode == "From Ticket":
            ticket_id = st.number_input("Ticket ID", min_value=1, step=1)

            title = st.text_input("Title (optional)")
            assigned_admin_id = st.selectbox(
                "Assign to (optional)",
                options=[None] + list(admin_options.keys()),
                format_func=lambda x: "— Not assigned —" if x is None else admin_options[x],
            )
            estimated_cost = st.number_input("Estimated cost (optional)", min_value=0.0, step=100.0)
            copy_media = st.checkbox("Copy ticket attachments into job card", value=True)

            if st.button("Create Job Card from Ticket", use_container_width=True):
                jc_id = db.create_job_card_from_ticket(
                    ticket_id=int(ticket_id),
                    created_by_admin_id=st.session_state.get("admin_id"),
                    assigned_admin_id=assigned_admin_id,
                    title=title.strip() if title.strip() else None,
                    estimated_cost=float(estimated_cost) if estimated_cost > 0 else None,
                    copy_media=copy_media,
                )
                st.success(f"✅ Job Card created: #{jc_id}")
                st.session_state["open_job_card_id"] = jc_id

        else:
            properties = db.get_all_ticket_properties()
            prop_map = {"— None —": None}
            for p in properties:
                prop_map[f"{p['name']} (ID {p['id']})"] = p["id"]

            title = st.text_input("Title (optional)")
            description = st.text_area("Description", height=120)
            activities = st.text_area("Activities (optional)", height=120)

            property_label = st.selectbox("Property (optional)", list(prop_map.keys()))
            property_id = prop_map[property_label]

            unit_number = st.text_input("Unit number (optional)")
            assigned_admin_id = st.selectbox(
                "Assign to (optional)",
                options=[None] + list(admin_options.keys()),
                format_func=lambda x: "— Not assigned —" if x is None else admin_options[x],
            )
            estimated_cost = st.number_input("Estimated cost (optional)", min_value=0.0, step=100.0)

            if st.button("Create Standalone Job Card", use_container_width=True):
                if not description.strip():
                    st.error("Description is required.")
                else:
                    jc_id = db.create_job_card_standalone(
                        description=description.strip(),
                        property_id=property_id,
                        unit_number=unit_number.strip() if unit_number.strip() else None,
                        created_by_admin_id=st.session_state.get("admin_id"),
                        assigned_admin_id=assigned_admin_id,
                        title=title.strip() if title.strip() else None,
                        activities=activities.strip() if activities.strip() else None,
                        estimated_cost=float(estimated_cost) if estimated_cost > 0 else None,
                    )
                    st.success(f"✅ Job Card created: #{jc_id}")
                    st.session_state["open_job_card_id"] = jc_id

        # Quick open if created
        open_id = st.session_state.get("open_job_card_id")
        if open_id:
            st.divider()
            st.info(f"Open Job Card #{open_id} from the Manage tab to view details.")

    # ---------------------------------------------------------------------
    # TAB 2: MANAGE
    # ---------------------------------------------------------------------
    with tabs[1]:
        st.subheader("Manage Job Cards")

        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            status = st.selectbox("Status", ["All", "Open", "In Progress", "Completed", "Signed Off", "Cancelled"])
        with c2:
            has_ticket = st.selectbox("Linked to Ticket?", ["All", "Yes", "No"])
        with c3:
            property_id = st.selectbox("Property", ["All"] + [p["id"] for p in db.get_all_ticket_properties()])

        df = db.fetch_job_cards(
            status=status,
            property_id=property_id,
            has_ticket=has_ticket if has_ticket != "All" else None
        )

        if df is None or df.empty:
            st.info("No job cards found.")
            return

        st.dataframe(df, use_container_width=True, hide_index=True)

        job_card_id = st.number_input("Open Job Card ID", min_value=1, step=1)
        if st.button("Open Job Card", use_container_width=True):
            st.session_state["job_card_view_id"] = int(job_card_id)

        view_id = st.session_state.get("job_card_view_id")
        if view_id:
            st.divider()
            jc = db.get_job_card(view_id)
            if not jc:
                st.error("Job card not found.")
                return

            st.markdown(f"## 🧾 Job Card #{jc['id']}")
            st.write(f"**Status:** {jc['status']}")
            st.write(f"**Ticket:** {jc['ticket_id'] if jc.get('ticket_id') else '— Standalone —'}")
            st.write(f"**Property:** {jc.get('property_name') or '—'}  |  **Unit:** {jc.get('unit_number') or '—'}")
            st.write(f"**Assigned:** {jc.get('assigned_to_name') or '—'}")

            st.markdown("### Description")
            st.write(jc["description"])

            st.markdown("### Activities")
            st.code(jc.get("activities") or "—", language="text")

            st.markdown("### Costs")
            est = st.number_input("Estimated cost", min_value=0.0, step=100.0, value=float(jc["estimated_cost"] or 0))
            act = st.number_input("Actual cost", min_value=0.0, step=100.0, value=float(jc["actual_cost"] or 0))
            if st.button("Save Costs"):
                db.update_job_card_costs(view_id, est if est > 0 else None, act if act > 0 else None)
                st.success("✅ Costs updated")

            st.markdown("### Update Status")
            new_status = st.selectbox(
                "Status",
                ["Open","In Progress","Completed","Signed Off","Cancelled"],
                index=["Open","In Progress","Completed","Signed Off","Cancelled"].index(jc["status"])
            )
            if st.button("Save Status"):
                db.update_job_card_status(view_id, new_status)
                st.success("✅ Status updated")

            st.markdown("### Attachments")
            media_df = db.fetch_job_card_media(view_id)
            if media_df is None or media_df.empty:
                st.info("No media attached to this job card.")
            else:
                cols = st.columns(3)
                for idx, row in media_df.reset_index(drop=True).iterrows():
                    with cols[idx % 3]:
                        m_type = row["media_type"]
                        m_blob = row["media_blob"]
                        f_name = row.get("filename", "attachment")

                        st.caption(f_name)
                        if m_type == "image":
                            st.image(BytesIO(m_blob), use_container_width=True)
                        elif m_type == "video":
                            st.video(BytesIO(m_blob))
                        else:
                            st.download_button("📥 Download", data=m_blob, file_name=f_name, key=f"jc_dl_{view_id}_{idx}")

            up = st.file_uploader("Upload new attachment", type=None)
            if up is not None:
                blob = up.read()
                guessed_type = "image" if up.type and up.type.startswith("image/") else ("video" if up.type and up.type.startswith("video/") else "document")
                db.add_job_card_media(view_id, guessed_type, blob, up.name)
                st.success("✅ Uploaded")
                st.rerun()

            st.markdown("### Sign Off")
            signed_by = st.text_input("Signed by name")
            role = st.text_input("Role (Tenant/Owner/Supervisor/etc)", value="Tenant")
            notes = st.text_area("Sign-off notes (optional)")
            sig_file = st.file_uploader("Signature file (optional)", type=None, key="sig_up")

            if st.button("Sign Off Job Card", use_container_width=True):
                if not signed_by.strip():
                    st.error("Signed by name is required.")
                else:
                    sig_blob = sig_file.read() if sig_file else None
                    sig_name = sig_file.name if sig_file else None
                    db.signoff_job_card(
                        view_id,
                        signed_by_name=signed_by.strip(),
                        signed_by_role=role.strip() if role.strip() else None,
                        signoff_notes=notes.strip() if notes.strip() else None,
                        signature_blob=sig_blob,
                        signature_filename=sig_name,
                    )
                    st.success("✅ Signed off and locked")
                    st.rerun()
