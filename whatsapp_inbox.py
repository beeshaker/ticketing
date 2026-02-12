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
from zoneinfo import ZoneInfo
import html

# -----------------------------------------------------------------------------
# Timezone: Kenya (Africa/Nairobi)
# -----------------------------------------------------------------------------
KENYA_TZ = ZoneInfo("Africa/Nairobi")


def kenya_now() -> datetime:
    return datetime.now(KENYA_TZ)


def whatsapp_inbox_page(db):
    # -------------------------------------------------------------------------
    # Auth guard
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
    # WhatsApp-like CSS
    # -------------------------------------------------------------------------
    st.markdown(
        """
        <style>
        /* Page spacing */
        .wa-wrap {padding: 6px 0 0 0;}
        .wa-title {font-size: 34px; font-weight: 800; margin-bottom: 4px;}
        .wa-sub {color: rgba(0,0,0,0.55); margin-bottom: 14px;}

        /* Chat panel */
        .wa-chat {
            height: 560px;
            overflow-y: auto;
            padding: 18px 14px;
            border-radius: 14px;
            background: linear-gradient(0deg, rgba(0,0,0,0.02), rgba(0,0,0,0.02)),
                        url("https://i.imgur.com/8Km9tLL.png");
            background-size: 340px;
            border: 1px solid rgba(0,0,0,0.08);
        }

        /* Bubble rows */
        .wa-row {
            display: flex;
            margin: 6px 0;
        }
        .wa-row.in {justify-content: flex-start;}
        .wa-row.out {justify-content: flex-end;}

        /* Bubbles */
        .wa-bubble {
            max-width: 78%;
            padding: 10px 12px 18px 12px;
            border-radius: 14px;
            font-size: 14px;
            line-height: 1.35;
            position: relative;
            box-shadow: 0 1px 0 rgba(0,0,0,0.05);
            white-space: pre-wrap;
            word-break: break-word;
        }
        .wa-in {
            background: white;
            border: 1px solid rgba(0,0,0,0.08);
            border-top-left-radius: 8px;
        }
        .wa-out {
            background: #DCF8C6; /* WhatsApp green */
            border: 1px solid rgba(0,0,0,0.05);
            border-top-right-radius: 8px;
        }

        /* Timestamp inside bubble */
        .wa-ts {
            position: absolute;
            right: 10px;
            bottom: 4px;
            font-size: 11px;
            color: rgba(0,0,0,0.45);
        }

        /* Meta chips (type/status/template) */
        .wa-meta {
            font-size: 11px;
            color: rgba(0,0,0,0.55);
            margin: 0 0 6px 0;
        }
        .wa-chip {
            display:inline-block;
            padding: 2px 8px;
            border-radius: 999px;
            background: rgba(0,0,0,0.06);
            margin-right: 6px;
        }

        /* Context mini row under bubbles */
        .wa-context {
            margin-top: 6px;
            font-size: 11px;
            color: rgba(0,0,0,0.55);
        }

        /* Reply box styling hints */
        .stTextArea textarea {
            border-radius: 12px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def _fmt_dt(x):
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return ""
        if isinstance(x, str):
            return x
        if hasattr(x, "strftime"):
            return x.strftime("%Y-%m-%d %H:%M")
        return str(x)

    def _fmt_time_only(x):
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return ""
        if isinstance(x, str):
            # if it already comes formatted, best effort:
            # show last 5 if looks like "... HH:MM"
            return x[-5:] if len(x) >= 5 else x
        if hasattr(x, "strftime"):
            return x.strftime("%H:%M")
        return ""

    def _safe_str(x):
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return ""
        return str(x)

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

    def _render_thread(df_thread: pd.DataFrame):
        """
        Renders a WhatsApp-like scrollable thread using HTML bubbles.
        """
        if df_thread is None or df_thread.empty:
            st.info("No messages yet for this conversation.")
            return

        chunks = ['<div class="wa-chat" id="wa-chat">']
        for _, r in df_thread.iterrows():
            direction = _safe_str(r.get("direction")).strip().lower()
            is_out = direction == "outbound"
            row_class = "out" if is_out else "in"
            bubble_class = "wa-out" if is_out else "wa-in"

            # Message bits
            body = _safe_str(r.get("body_text") or "")
            tpl = _safe_str(r.get("template_name") or "")
            mtype = _safe_str(r.get("message_type") or "text")
            status = _safe_str(r.get("status") or "")
            err = _safe_str(r.get("error_text") or "")
            ts = _fmt_time_only(r.get("created_at"))

            # Escape for HTML safety
            body_html = html.escape(body)
            tpl_html = html.escape(tpl)

            # Meta row (optional)
            meta_bits = []
            if mtype and mtype != "text":
                meta_bits.append(f'<span class="wa-chip">{html.escape(mtype)}</span>')
            if tpl:
                meta_bits.append(f'<span class="wa-chip">template: {tpl_html}</span>')
            if status:
                meta_bits.append(f'<span class="wa-chip">status: {html.escape(status)}</span>')

            meta_html = ""
            if meta_bits:
                meta_html = f'<div class="wa-meta">{"".join(meta_bits)}</div>'

            # Main content
            if body:
                content = body_html
            elif tpl:
                content = f"📌 Template: <b>{tpl_html}</b>"
            else:
                content = "—"

            # Error
            if err:
                content += f"\n\n⚠️ {html.escape(err)}"

            chunks.append(
                f"""
                <div class="wa-row {row_class}">
                  <div class="wa-bubble {bubble_class}">
                    {meta_html}
                    {content}
                    <div class="wa-ts">{html.escape(ts)}</div>
                  </div>
                </div>
                """
            )

        chunks.append("</div>")

        # Auto-scroll to bottom (best-effort)
        chunks.append(
            """
            <script>
            const el = window.parent.document.querySelector('#wa-chat');
            if (el) { el.scrollTop = el.scrollHeight; }
            </script>
            """
        )

        st.markdown("".join(chunks), unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # UI
    # -------------------------------------------------------------------------
    st.markdown('<div class="wa-wrap">', unsafe_allow_html=True)
    st.markdown('<div class="wa-title">💬 WhatsApp Inbox</div>', unsafe_allow_html=True)
    st.markdown('<div class="wa-sub">Private admin inbox (accessible only via the admin portal menu).</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

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

        # If last_at is not a datetime, keep it as-is; conversion is best-effort
        if "last_at" in conv_df.columns:
            try:
                conv_df["last_at"] = pd.to_datetime(conv_df["last_at"], errors="coerce")
            except Exception:
                pass

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
        last_row = conv_df.loc[
            conv_df["wa_number"].astype(str) == str(st.session_state.wa_selected_number)
        ].iloc[0]

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

        # Load older messages (prepend)
        if df_thread is not None and not df_thread.empty:
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
                    combined = (
                        combined.drop_duplicates(subset=["id"])
                        .sort_values("id", ascending=True)
                        .reset_index(drop=True)
                    )
                    st.session_state.wa_msg_cache = combined
                    st.rerun()

        # Render WhatsApp-like thread
        _render_thread(df_thread)

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

                    # Append synthetic row so it appears instantly
                    try:
                        now = kenya_now()
                        synthetic = {
                            "id": int(1e18) + int(now.timestamp()),
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
                            st.session_state.wa_msg_cache = (
                                pd.concat([current, pd.DataFrame([synthetic])], ignore_index=True)
                                .sort_values("id", ascending=True)
                                .reset_index(drop=True)
                            )
                    except Exception:
                        st.session_state.wa_msg_cache = None

                    st.session_state[reply_key] = ""
                    st.rerun()
