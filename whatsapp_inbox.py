# whatsapp_inbox.py
# PRIVATE MODULE (not in /pages)
# Call it from main.py like: whatsapp_inbox_page(db)
#
# Requires Conn methods:
#   - fetch_inbox_conversations(q_search: str|None, limit: int) -> pd.DataFrame
#   - fetch_conversation_messages(wa_number: str, limit: int, before_id: int|None) -> pd.DataFrame
#   - send_whatsapp_notification(to: str, message: str) -> dict

import streamlit as st
import pandas as pd
from datetime import datetime


def whatsapp_inbox_page(db):
    # -------------------------------------------------------------------------
    # Auth guard (main already does license + login, but keep a hard guard anyway)
    # -------------------------------------------------------------------------
    if "authenticated" not in st.session_state or not st.session_state["authenticated"]:
        st.error("Please login first.")
        st.stop()

    # -------------------------------------------------------------------------
    # Session defaults
    # -------------------------------------------------------------------------
    st.session_state.setdefault("wa_inbox_search", "")
    st.session_state.setdefault("wa_selected_number", None)
    st.session_state.setdefault("wa_msg_limit", 80)
    st.session_state.setdefault("wa_msg_before_id", None)
    st.session_state.setdefault("wa_msg_cache", None)

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def _fmt_dt(x):
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return "—"
        if isinstance(x, str):
            return x
        if hasattr(x, "strftime"):
            return x.strftime("%Y-%m-%d %H:%M")
        return str(x)

    def _safe_str(x):
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return ""
        return str(x)

    def _badge(direction: str):
        d = (direction or "").strip().lower()
        return "📤" if d == "outbound" else "📥"

    def _conversation_label(row) -> str:
        wa = _safe_str(row.get("wa_number") or "")
        last_at = _fmt_dt(row.get("last_at"))
        body = _safe_str(row.get("body_text") or "")
        tpl = _safe_str(row.get("template_name") or "")

        snippet = body.strip().replace("\n", " ")
        if not snippet and tpl:
            snippet = f"[template] {tpl}"
        if not snippet:
            snippet = "[no preview]"
        if len(snippet) > 55:
            snippet = snippet[:55] + "…"

        return f"{wa}  •  {last_at}  •  {snippet}"

    def _reset_thread(new_wa_number: str | None):
        st.session_state.wa_selected_number = new_wa_number
        st.session_state.wa_msg_before_id = None
        st.session_state.wa_msg_cache = None

    def _load_thread(wa_number: str):
        limit = int(st.session_state.wa_msg_limit or 80)
        before_id = st.session_state.wa_msg_before_id
        df = db.fetch_conversation_messages(
            wa_number=wa_number,
            limit=limit,
            before_id=before_id,
        )
        if df is None or df.empty:
            return df
        # Oldest -> newest for display
        return df.sort_values("id", ascending=True).reset_index(drop=True)

    # -------------------------------------------------------------------------
    # UI
    # -------------------------------------------------------------------------
    st.title("💬 WhatsApp Inbox")
    st.caption("Private admin inbox (accessible only via the admin portal menu).")

    left, right = st.columns([0.75, 1.25], gap="large")

    # ==========================
    # LEFT: Conversations
    # ==========================
    with left:
        st.subheader("📨 Conversations")

        q = st.text_input(
            "Search by number or text",
            value=st.session_state.wa_inbox_search,
            placeholder="e.g. 2547... or 'leak' or 'invoice'",
            key="wa_inbox_search",
        )

        conv_df = db.fetch_inbox_conversations(q_search=q, limit=80)
        if conv_df is None or conv_df.empty:
            st.info("No conversations found.")
            return

        if "last_at" in conv_df.columns:
            conv_df["last_at"] = pd.to_datetime(conv_df["last_at"], errors="coerce")

        wa_numbers = conv_df["wa_number"].astype(str).tolist()
        if st.session_state.wa_selected_number is None or st.session_state.wa_selected_number not in wa_numbers:
            _reset_thread(wa_numbers[0])

        selected_wa = st.selectbox(
            "Select conversation",
            options=wa_numbers,
            index=wa_numbers.index(st.session_state.wa_selected_number),
            format_func=lambda wa: _conversation_label(
                conv_df.loc[conv_df["wa_number"].astype(str) == str(wa)].iloc[0]
            ),
            key="wa_selectbox_number",
        )

        if selected_wa != st.session_state.wa_selected_number:
            _reset_thread(selected_wa)

        st.divider()

        # Context for selected conversation
        last_row = conv_df.loc[conv_df["wa_number"].astype(str) == str(st.session_state.wa_selected_number)].iloc[0]
        st.markdown("### 🧾 Context")
        st.write(f"**WhatsApp:** {st.session_state.wa_selected_number}")
        st.write(f"**Last message at:** {_fmt_dt(last_row.get('last_at'))}")
        if last_row.get("ticket_id"):
            st.write(f"**Linked Ticket:** #{int(last_row.get('ticket_id'))}")
        if last_row.get("job_card_id"):
            st.write(f"**Linked Job Card:** #{int(last_row.get('job_card_id'))}")

    # ==========================
    # RIGHT: Thread + Reply
    # ==========================
    with right:
        wa_number = st.session_state.wa_selected_number
        st.subheader(f"🗨️ Thread: {wa_number}")

        t1, t2, t3 = st.columns([1, 1, 1])
        with t1:
            if st.button("🔄 Refresh", use_container_width=True):
                st.session_state.wa_msg_cache = None
                st.session_state.wa_msg_before_id = None
                st.rerun()

        with t2:
            st.session_state.wa_msg_limit = st.selectbox(
                "Messages per load",
                options=[40, 80, 120, 200],
                index=[40, 80, 120, 200].index(int(st.session_state.wa_msg_limit or 80)),
                key="wa_msg_limit_select",
            )

        with t3:
            # Export currently loaded cache
            if st.button("🧾 Export CSV", use_container_width=True):
                df_exp = st.session_state.wa_msg_cache
                if df_exp is None or df_exp.empty:
                    st.warning("No messages loaded yet.")
                else:
                    csv = df_exp.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        "⬇️ Download CSV",
                        data=csv,
                        file_name=f"whatsapp_thread_{wa_number}.csv",
                        mime="text/csv",
                        use_container_width=True,
                        key=f"wa_dl_{wa_number}",
                    )

        st.divider()

        # Load thread (cached)
        if st.session_state.wa_msg_cache is None:
            df_thread = _load_thread(wa_number)
            st.session_state.wa_msg_cache = df_thread
        else:
            df_thread = st.session_state.wa_msg_cache

        if df_thread is None or df_thread.empty:
            st.info("No messages yet for this conversation.")
        else:
            oldest_id = int(df_thread["id"].min())

            if st.button("⬆️ Load older messages", use_container_width=True, key=f"wa_load_older_{wa_number}"):
                older = db.fetch_conversation_messages(
                    wa_number=wa_number,
                    limit=int(st.session_state.wa_msg_limit or 80),
                    before_id=oldest_id,
                )
                if older is None or older.empty:
                    st.info("No older messages found.")
                else:
                    older = older.sort_values("id", ascending=True).reset_index(drop=True)
                    combined = pd.concat([older, df_thread], ignore_index=True)
                    combined = combined.drop_duplicates(subset=["id"]).sort_values("id", ascending=True).reset_index(drop=True)
                    st.session_state.wa_msg_cache = combined
                    st.rerun()

            st.divider()

            # Render messages
            for _, r in df_thread.iterrows():
                direction = _safe_str(r.get("direction")).strip().lower()
                who = "user" if direction == "inbound" else "assistant"
                ts = _fmt_dt(r.get("created_at"))

                body = _safe_str(r.get("body_text") or "")
                tpl = _safe_str(r.get("template_name") or "")
                mtype = _safe_str(r.get("message_type") or "text")
                status = _safe_str(r.get("status") or "")
                err = _safe_str(r.get("error_text") or "")
                verify_url = _safe_str(r.get("verify_url") or "")

                header_bits = [ts]
                if mtype and mtype != "text":
                    header_bits.append(mtype)
                if tpl:
                    header_bits.append(f"template: {tpl}")
                if status:
                    header_bits.append(f"status: {status}")

                with st.chat_message(who):
                    st.caption(" • ".join(header_bits))

                    if body:
                        st.write(body)
                    elif tpl:
                        st.write(f"📌 Template: **{tpl}**")
                    else:
                        st.write("—")

                    if verify_url:
                        st.code(verify_url)

                    if err:
                        st.error(err)

                    # Context pointers
                    ticket_id = r.get("ticket_id")
                    job_card_id = r.get("job_card_id")
                    if ticket_id or job_card_id:
                        cA, cB = st.columns([1, 1])
                        with cA:
                            if ticket_id:
                                st.caption(f"Ticket: #{int(ticket_id)}")
                        with cB:
                            if job_card_id:
                                st.caption(f"Job Card: #{int(job_card_id)}")

        st.divider()

        # Reply box
        st.markdown("### ✍️ Reply")

        reply_key = f"wa_reply_{wa_number}"
        if reply_key not in st.session_state:
            st.session_state[reply_key] = ""

        reply = st.text_area(
            "Message",
            placeholder="Type your reply…",
            key=reply_key,
            height=110,
        )

        c1, c2 = st.columns([1, 1])
        with c1:
            send = st.button("📤 Send", use_container_width=True, key=f"wa_send_{wa_number}")
        with c2:
            clear = st.button("🧹 Clear", use_container_width=True, key=f"wa_clear_{wa_number}")

        if clear:
            st.session_state[reply_key] = ""
            st.rerun()

        if send:
            if not reply.strip():
                st.error("Type a message first.")
            else:
                resp = db.send_whatsapp_notification(to=wa_number, message=reply.strip())
                if isinstance(resp, dict) and resp.get("error"):
                    st.error(f"Failed: {resp['error']}")
                else:
                    st.success("✅ Sent.")

                    # Append synthetic row so it appears instantly (optional)
                    try:
                        now = datetime.now()
                        synthetic = {
                            "id": int(df_thread["id"].max()) + 1 if df_thread is not None and not df_thread.empty else 10**12,
                            "wa_number": wa_number,
                            "direction": "outbound",
                            "wa_to": wa_number,
                            "wa_from": None,
                            "message_type": "text",
                            "template_name": None,
                            "body_text": reply.strip(),
                            "verify_url": None,
                            "meta_message_id": None,
                            "status": "sent",
                            "error_text": None,
                            "ticket_id": None,
                            "job_card_id": None,
                            "created_at": now,
                        }
                        current = st.session_state.wa_msg_cache
                        if current is None or current.empty:
                            st.session_state.wa_msg_cache = pd.DataFrame([synthetic])
                        else:
                            st.session_state.wa_msg_cache = pd.concat(
                                [current, pd.DataFrame([synthetic])], ignore_index=True
                            ).sort_values("id", ascending=True).reset_index(drop=True)
                    except Exception:
                        st.session_state.wa_msg_cache = None

                    st.session_state[reply_key] = ""
                    st.rerun()
