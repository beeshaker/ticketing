# whatsapp_inbox.py
# PRIVATE MODULE (not in /pages)
# Call it from main.py like: whatsapp_inbox_page(db)
#
# Requires Conn methods:
#   - fetch_inbox_conversations(q_search: str|None, limit: int) -> pd.DataFrame
#   - fetch_conversation_messages(wa_number: str, limit: int, before_id: int|None) -> pd.DataFrame
#   - send_whatsapp_notification(to: str, message: str) -> dict

from __future__ import annotations

import json
import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

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
    st.session_state.setdefault("wa_msg_cache", None)

    # typing indicator controls (UI-only)
    st.session_state.setdefault("wa_show_typing", False)
    st.session_state.setdefault("wa_typing_until", None)

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def _fmt_dt(x):
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return ""
        if isinstance(x, str):
            return x
        if hasattr(x, "strftime"):
            return x.strftime("%H:%M")
        return str(x)

    def _fmt_day(x):
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return ""
        try:
            dt = pd.to_datetime(x)
            return dt.strftime("%d %b %Y")
        except Exception:
            return str(x)

    def _safe_str(x):
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return ""
        return str(x)

    def _safe_int(x):
        try:
            if x is None or (isinstance(x, float) and pd.isna(x)):
                return None
            return int(x)
        except Exception:
            return None

    def _initials(name: str) -> str:
        name = (name or "").strip()
        if not name:
            return "U"
        parts = [p for p in name.split() if p]
        if len(parts) == 1:
            return parts[0][:1].upper()
        return (parts[0][:1] + parts[-1][:1]).upper()

    def _avatar_color(seed: str) -> str:
        # stable pastel-ish palette; no randomness
        palette = ["#25D366", "#128C7E", "#34B7F1", "#6C5CE7", "#E17055", "#00B894", "#0984E3", "#D63031"]
        s = sum(ord(c) for c in (seed or ""))
        return palette[s % len(palette)]

    def _status_checkmarks(status: str, direction: str) -> str:
        # WhatsApp-like:
        # - sent: ✓ (grey)
        # - delivered: ✓✓ (grey)
        # - read: ✓✓ (blue)
        # inbound messages don't show checks
        if (direction or "").lower() != "outbound":
            return ""

        s = (status or "").strip().lower()
        if not s:
            return ""  # no status -> no checks

        if s in {"sent", "queued", "accepted"}:
            return '<span class="wa-ticks wa-grey">✓</span>'
        if s in {"delivered"}:
            return '<span class="wa-ticks wa-grey">✓✓</span>'
        if s in {"read", "seen"}:
            return '<span class="wa-ticks wa-blue">✓✓</span>'

        # fallback: show delivered-style if unknown but present
        return '<span class="wa-ticks wa-grey">✓✓</span>'

    def _conversation_label(row) -> str:
        wa = _safe_str(row.get("wa_number") or "")
        body = _safe_str(row.get("body_text") or "")
        tpl = _safe_str(row.get("template_name") or "")
        snippet = body.strip().replace("\n", " ")
        if not snippet and tpl:
            snippet = f"[template] {tpl}"
        if not snippet:
            snippet = "[no preview]"
        if len(snippet) > 42:
            snippet = snippet[:42] + "…"
        return f"{wa} — {snippet}"

    def _reset_thread(new_wa_number: str | None):
        st.session_state.wa_selected_number = new_wa_number
        st.session_state.wa_msg_cache = None
        st.session_state.wa_show_typing = False
        st.session_state.wa_typing_until = None

    def _load_thread(wa_number: str):
        limit = int(st.session_state.wa_msg_limit or 80)
        df = db.fetch_conversation_messages(
            wa_number=wa_number,
            limit=limit,
            before_id=None,
        )
        if df is None or df.empty:
            return df
        return df.sort_values("id", ascending=True).reset_index(drop=True)

    def _extract_name_from_meta(meta_json_val) -> str | None:
        """
        Optional: if your whatsapp_messages meta_json stores sender profile name.
        We'll try gently; otherwise return None.
        """
        if meta_json_val is None or (isinstance(meta_json_val, float) and pd.isna(meta_json_val)):
            return None
        try:
            if isinstance(meta_json_val, (dict, list)):
                obj = meta_json_val
            else:
                obj = json.loads(str(meta_json_val))
            # common patterns (best effort)
            if isinstance(obj, dict):
                if "profile_name" in obj:
                    return str(obj.get("profile_name") or "").strip() or None
                if "name" in obj and isinstance(obj["name"], str):
                    return obj["name"].strip() or None
                # nested
                profile = obj.get("profile") or obj.get("contact") or obj.get("from") or {}
                if isinstance(profile, dict):
                    for k in ("name", "profile_name", "display_name"):
                        v = profile.get(k)
                        if isinstance(v, str) and v.strip():
                            return v.strip()
        except Exception:
            return None
        return None

    # -------------------------------------------------------------------------
    # WhatsApp-like CSS (pixel-ish clone)
    # -------------------------------------------------------------------------
    st.markdown(
        """
        <style>
        /* Page spacing */
        .block-container { padding-top: 1.0rem; padding-bottom: 1.0rem; }

        /* Remove "ugly" background image: enforce clean app background */
        html, body, [data-testid="stAppViewContainer"] {
            background: #ECE5DD !important;  /* WhatsApp chat wallpaper base */
        }
        [data-testid="stHeader"] { background: rgba(0,0,0,0); }

        /* Hide Streamlit default elements that spoil the clone */
        [data-testid="stToolbar"] {visibility: hidden; height: 0px;}
        footer {visibility: hidden; height: 0px;}

        /* Layout columns */
        .wa-shell { display:flex; gap:18px; align-items:stretch; }
        .wa-left, .wa-right { border-radius: 14px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.10); }

        /* Left (chat list) */
        .wa-left {
            background: #FFFFFF;
            border: 1px solid rgba(0,0,0,0.06);
        }
        .wa-left-header {
            padding: 12px 14px;
            background: #F0F2F5;
            border-bottom: 1px solid rgba(0,0,0,0.06);
            display:flex; align-items:center; justify-content:space-between;
        }
        .wa-left-title { font-weight: 800; color:#111B21; }
        .wa-left-sub { color:#667781; font-size:12px; margin-top:2px; }

        /* Right (chat) */
        .wa-right {
            background: #EFEAE2;
            border: 1px solid rgba(0,0,0,0.06);
        }
        .wa-header {
            background: #075E54;
            color: white;
            padding: 10px 12px;
            display:flex;
            align-items:center;
            justify-content:space-between;
            gap:12px;
        }
        .wa-head-left { display:flex; align-items:center; gap:10px; min-width: 0; }
        .wa-avatar {
            width: 36px; height: 36px; border-radius: 50%;
            display:flex; align-items:center; justify-content:center;
            font-weight: 800; color:#fff; flex: 0 0 auto;
            box-shadow: 0 6px 14px rgba(0,0,0,0.12);
        }
        .wa-title-wrap { min-width:0; }
        .wa-title {
            font-weight: 800;
            font-size: 15px;
            line-height: 1.1;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .wa-presence {
            font-size: 12px;
            opacity: 0.85;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .wa-head-actions { display:flex; gap:10px; align-items:center; opacity:0.95; }
        .wa-pill {
            background: rgba(255,255,255,0.14);
            border: 1px solid rgba(255,255,255,0.18);
            padding: 6px 10px;
            border-radius: 999px;
            font-size: 12px;
        }

        /* Chat body */
        .wa-body {
            padding: 16px 16px 10px 16px;
            height: 58vh;
            overflow-y: auto;
        }

        /* Date separator */
        .wa-day {
            display:flex;
            justify-content:center;
            margin: 10px 0 12px 0;
        }
        .wa-day > span {
            font-size: 12px;
            color: #54656F;
            background: rgba(255,255,255,0.85);
            border: 1px solid rgba(0,0,0,0.06);
            padding: 4px 10px;
            border-radius: 999px;
        }

        /* Message bubbles */
        .wa-row { display:flex; margin: 6px 0; }
        .wa-row.in { justify-content:flex-start; }
        .wa-row.out { justify-content:flex-end; }

        .wa-bubble {
            max-width: 72%;
            padding: 8px 10px 18px 10px;
            border-radius: 10px;
            position: relative;
            box-shadow: 0 2px 0 rgba(0,0,0,0.04);
            border: 1px solid rgba(0,0,0,0.04);
            word-wrap: break-word;
            white-space: pre-wrap;
            font-size: 14px;
            line-height: 1.25;
        }
        .wa-in { background: #FFFFFF; color:#111B21; }
        .wa-out { background: #D9FDD3; color:#111B21; }

        /* Bubble tails */
        .wa-row.in .wa-bubble:before{
            content:"";
            position:absolute;
            left:-6px; top:8px;
            width: 0; height: 0;
            border-top: 6px solid transparent;
            border-bottom: 6px solid transparent;
            border-right: 6px solid #FFFFFF;
        }
        .wa-row.out .wa-bubble:before{
            content:"";
            position:absolute;
            right:-6px; top:8px;
            width: 0; height: 0;
            border-top: 6px solid transparent;
            border-bottom: 6px solid transparent;
            border-left: 6px solid #D9FDD3;
        }

        /* Meta line in bubble */
        .wa-meta {
            position:absolute;
            right: 8px;
            bottom: 4px;
            display:flex;
            gap: 6px;
            align-items:center;
            font-size: 11px;
            color: #667781;
        }
        .wa-ticks { font-weight: 900; letter-spacing: -1px; }
        .wa-grey { color: #8696A0; }
        .wa-blue { color: #53BDEB; }

        /* Typing indicator */
        .wa-typing {
            display:flex;
            align-items:center;
            gap:10px;
            padding: 8px 12px;
            margin: 10px 0 6px 0;
        }
        .wa-typing .wa-bubble {
            padding: 10px 12px 10px 12px;
            border-radius: 18px;
        }
        .dots {
            display:inline-flex;
            gap:4px;
        }
        .dot {
            width:6px; height:6px;
            border-radius:50%;
            background:#8696A0;
            opacity:0.55;
            animation: waDot 1.2s infinite ease-in-out;
        }
        .dot:nth-child(2){ animation-delay: 0.15s; }
        .dot:nth-child(3){ animation-delay: 0.30s; }
        @keyframes waDot {
            0%, 80%, 100% { transform: translateY(0); opacity:0.45; }
            40% { transform: translateY(-3px); opacity:0.95; }
        }

        /* Composer */
        .wa-composer {
            background:#F0F2F5;
            border-top: 1px solid rgba(0,0,0,0.06);
            padding: 10px 12px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # -------------------------------------------------------------------------
    # Title (minimal)
    # -------------------------------------------------------------------------
    st.markdown("")

    # -------------------------------------------------------------------------
    # Layout: left = conversation list; right = chat
    # -------------------------------------------------------------------------
    left, right = st.columns([0.60, 1.40], gap="large")

    # ==========================
    # LEFT: Conversations
    # ==========================
    with left:
        st.markdown(
            """
            <div class="wa-left">
                <div class="wa-left-header">
                    <div>
                        <div class="wa-left-title">WhatsApp Inbox</div>
                        <div class="wa-left-sub">Private admin inbox</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        q = st.text_input(
            "Search",
            value=st.session_state.wa_inbox_search,
            placeholder="Search number or message text…",
            key="wa_inbox_search",
        )

        conv_df = db.fetch_inbox_conversations(q_search=q, limit=120)
        if conv_df is None or conv_df.empty:
            st.info("No conversations found.")
            return

        if "last_at" in conv_df.columns:
            conv_df["last_at"] = pd.to_datetime(conv_df["last_at"], errors="coerce")

        wa_numbers = conv_df["wa_number"].astype(str).tolist()

        if st.session_state.wa_selected_number is None or st.session_state.wa_selected_number not in wa_numbers:
            _reset_thread(wa_numbers[0])

        selected_wa = st.selectbox(
            "Chats",
            options=wa_numbers,
            index=wa_numbers.index(st.session_state.wa_selected_number),
            format_func=lambda wa: _conversation_label(
                conv_df.loc[conv_df["wa_number"].astype(str) == str(wa)].iloc[0]
            ),
            key="wa_selectbox_number",
            label_visibility="collapsed",
        )

        if selected_wa != st.session_state.wa_selected_number:
            _reset_thread(selected_wa)

        # Small context block
        last_row = conv_df.loc[conv_df["wa_number"].astype(str) == str(st.session_state.wa_selected_number)].iloc[0]
        st.caption(f"Selected: **{st.session_state.wa_selected_number}**  •  Last: {_fmt_day(last_row.get('last_at'))}")

        # Controls
        cA, cB = st.columns([1, 1])
        with cA:
            if st.button("🔄 Refresh list", use_container_width=True):
                st.session_state.wa_msg_cache = None
                st.rerun()
        with cB:
            st.session_state.wa_msg_limit = st.selectbox(
                "Load",
                options=[40, 80, 120, 200],
                index=[40, 80, 120, 200].index(int(st.session_state.wa_msg_limit or 80)),
                key="wa_msg_limit_select",
                label_visibility="collapsed",
            )

    # ==========================
    # RIGHT: Chat UI (WhatsApp-like)
    # ==========================
    with right:
        wa_number = st.session_state.wa_selected_number

        # Load messages (cached)
        if st.session_state.wa_msg_cache is None:
            df_thread = _load_thread(wa_number)
            st.session_state.wa_msg_cache = df_thread
        else:
            df_thread = st.session_state.wa_msg_cache

        # Derive "contact name" best-effort (from meta_json if present; else number)
        contact_name = None
        if df_thread is not None and not df_thread.empty and "meta_json" in df_thread.columns:
            # take the latest inbound meta_json first
            cand = df_thread[df_thread["direction"].astype(str).str.lower() == "inbound"]
            if not cand.empty:
                contact_name = _extract_name_from_meta(cand.iloc[-1].get("meta_json"))
            if not contact_name:
                contact_name = _extract_name_from_meta(df_thread.iloc[-1].get("meta_json"))
        if not contact_name:
            contact_name = wa_number

        avatar_bg = _avatar_color(wa_number)
        avatar_txt = _initials(contact_name if contact_name != wa_number else "User")

        # Header bar (WhatsApp)
        st.markdown(
            f"""
            <div class="wa-right">
              <div class="wa-header">
                <div class="wa-head-left">
                  <div class="wa-avatar" style="background:{avatar_bg}">{avatar_txt}</div>
                  <div class="wa-title-wrap">
                    <div class="wa-title">{_safe_str(contact_name)}</div>
                    <div class="wa-presence">online</div>
                  </div>
                </div>
                <div class="wa-head-actions">
                  <div class="wa-pill">🔍 Search</div>
                  <div class="wa-pill">⋮</div>
                </div>
              </div>
            """,
            unsafe_allow_html=True,
        )

        # Body
        def _render_thread(df: pd.DataFrame):
            if df is None or df.empty:
                st.markdown('<div class="wa-body">No messages yet.</div>', unsafe_allow_html=True)
                return

            # ensure datetime
            if "created_at" in df.columns:
                df2 = df.copy()
                df2["created_at"] = pd.to_datetime(df2["created_at"], errors="coerce")
            else:
                df2 = df.copy()
                df2["created_at"] = pd.NaT

            chunks = ['<div class="wa-body">']

            last_day = None
            for _, r in df2.iterrows():
                direction = _safe_str(r.get("direction")).strip().lower()
                row_cls = "out" if direction == "outbound" else "in"

                created_at = r.get("created_at")
                day_key = None
                try:
                    if pd.notna(created_at):
                        day_key = created_at.date()
                except Exception:
                    day_key = None

                if day_key and day_key != last_day:
                    last_day = day_key
                    chunks.append(f'<div class="wa-day"><span>{created_at.strftime("%d %b %Y")}</span></div>')

                body = _safe_str(r.get("body_text") or "")
                tpl = _safe_str(r.get("template_name") or "")
                mtype = _safe_str(r.get("message_type") or "text")
                status = _safe_str(r.get("status") or "")
                err = _safe_str(r.get("error_text") or "")
                verify_url = _safe_str(r.get("verify_url") or "")

                # What to show as message content
                content = body.strip()
                if not content and tpl:
                    content = f"📌 Template: {tpl}"
                if not content and mtype and mtype != "text":
                    content = f"[{mtype}]"
                if not content:
                    content = "—"

                # Escape minimal HTML (avoid breaking layout)
                def esc(s: str) -> str:
                    return (
                        s.replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;")
                    )

                content_html = esc(content)

                # Optional verify URL inline
                if verify_url:
                    content_html += f"<br/><span style='font-size:12px;color:#54656F'>🔗 {esc(verify_url)}</span>"

                if err:
                    content_html += f"<br/><span style='font-size:12px;color:#D63031'>⚠ {esc(err)}</span>"

                ts = ""
                try:
                    ts = created_at.strftime("%H:%M") if pd.notna(created_at) else ""
                except Exception:
                    ts = ""

                ticks = _status_checkmarks(status=status, direction=direction)

                chunks.append(
                    f"""
                    <div class="wa-row {row_cls}">
                      <div class="wa-bubble wa-{'out' if row_cls=='out' else 'in'}">
                        {content_html}
                        <div class="wa-meta">
                          <span>{ts}</span>
                          {ticks}
                        </div>
                      </div>
                    </div>
                    """
                )

            # Typing indicator (UI-only)
            if st.session_state.get("wa_show_typing"):
                chunks.append(
                    """
                    <div class="wa-typing">
                      <div class="wa-row in">
                        <div class="wa-bubble wa-in" style="border-radius:18px;">
                          <span class="dots">
                            <span class="dot"></span><span class="dot"></span><span class="dot"></span>
                          </span>
                        </div>
                      </div>
                    </div>
                    """
                )

            chunks.append("</div>")  # wa-body
            st.markdown("".join(chunks), unsafe_allow_html=True)

        _render_thread(df_thread)

        # Footer composer (Streamlit widgets)
        st.markdown('<div class="wa-composer">', unsafe_allow_html=True)

        c1, c2, c3 = st.columns([1.15, 0.45, 0.45])
        with c1:
            reply_key = f"wa_reply_{wa_number}"
            if reply_key not in st.session_state:
                st.session_state[reply_key] = ""

            reply = st.text_area(
                "Message",
                placeholder="Type a message…",
                key=reply_key,
                height=80,
                label_visibility="collapsed",
            )

        with c2:
            if st.button("✅ Typing", use_container_width=True):
                # toggle typing indicator; auto-expire after ~8 seconds (UI only)
                st.session_state.wa_show_typing = not bool(st.session_state.get("wa_show_typing"))
                st.session_state.wa_typing_until = (kenya_now().timestamp() + 8) if st.session_state.wa_show_typing else None
                st.rerun()

        with c3:
            send = st.button("📤 Send", use_container_width=True)

        # auto-clear typing indicator on expiry
        if st.session_state.get("wa_show_typing") and st.session_state.get("wa_typing_until"):
            if kenya_now().timestamp() > float(st.session_state.wa_typing_until):
                st.session_state.wa_show_typing = False
                st.session_state.wa_typing_until = None

        if send:
            if not reply.strip():
                st.error("Type a message first.")
            else:
                resp = db.send_whatsapp_notification(to=wa_number, message=reply.strip())
                if isinstance(resp, dict) and resp.get("error"):
                    st.error(f"Failed: {resp['error']}")
                else:
                    st.success("✅ Sent.")

                    # append synthetic row so it appears instantly
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
                            "status": "delivered",  # optimistic UX (shows ✓✓)
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
                                .drop_duplicates(subset=["id"])
                                .sort_values("id", ascending=True)
                                .reset_index(drop=True)
                            )
                    except Exception:
                        st.session_state.wa_msg_cache = None

                    st.session_state[reply_key] = ""
                    st.rerun()

        # export button under composer (clean)
        with st.expander("Export / Tools", expanded=False):
            cE1, cE2 = st.columns([1, 1])
            with cE1:
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
            with cE2:
                if st.button("🔄 Refresh thread", use_container_width=True):
                    st.session_state.wa_msg_cache = None
                    st.rerun()

        st.markdown("</div></div>", unsafe_allow_html=True)  # close composer + wa-right
