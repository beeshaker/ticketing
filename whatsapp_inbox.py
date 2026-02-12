# whatsapp_inbox.py
# PRIVATE MODULE (not in /pages)
# Call it from main.py like: whatsapp_inbox_page(db)

from __future__ import annotations

import re
import json
import html
import streamlit as st
import pandas as pd
import streamlit.components.v1 as components
from datetime import datetime
from zoneinfo import ZoneInfo

KENYA_TZ = ZoneInfo("Africa/Nairobi")


def whatsapp_inbox_page(db):
    if "authenticated" not in st.session_state or not st.session_state["authenticated"]:
        st.error("Please login first.")
        st.stop()

    # ---------------------------
    # Session state
    # ---------------------------
    st.session_state.setdefault("wa_selected_number", None)
    st.session_state.setdefault("wa_msg_cache", None)
    st.session_state.setdefault("wa_inbox_search", "")
    st.session_state.setdefault("wa_show_typing", False)
    st.session_state.setdefault("wa_compose_text", "")

    # ---------------------------
    # Helpers
    # ---------------------------
    def _s(x) -> str:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return ""
        return str(x)

    def _strip_html_if_needed(s: str) -> str:
        s = _s(s)
        if "<div" in s.lower() or "<span" in s.lower() or "</" in s.lower():
            s = re.sub(r"<[^>]+>", "", s)
            s = re.sub(r"\n{3,}", "\n\n", s)
            s = s.strip()
        return s

    def _dt_kenya(x) -> datetime | None:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return None
        dt = pd.to_datetime(x, errors="coerce")
        if pd.isna(dt):
            return None
        py = dt.to_pydatetime()
        if getattr(py, "tzinfo", None) is None:
            return py.replace(tzinfo=KENYA_TZ)
        return py.astimezone(KENYA_TZ)

    def _avatar_color(seed: str) -> str:
        palette = ["#25D366", "#128C7E", "#34B7F1", "#6C5CE7",
                   "#E17055", "#00B894", "#0984E3", "#D63031"]
        n = sum(ord(c) for c in (seed or ""))
        return palette[n % len(palette)]

    def _initials(wa: str) -> str:
        wa = _s(wa).strip()
        return wa[-2:] if len(wa) >= 2 else "WA"

    def _ticks(direction: str, status: str) -> str:
        if _s(direction).lower().strip() != "outbound":
            return ""
        s = _s(status).lower().strip()
        if s in {"sent", "queued", "accepted"}:
            return '<span class="ticks grey">✓</span>'
        if s == "delivered":
            return '<span class="ticks grey">✓✓</span>'
        if s in {"read", "seen"}:
            return '<span class="ticks blue">✓✓</span>'
        return '<span class="ticks grey">✓✓</span>'

    def _render_interactive(meta_json_val) -> str:
        if meta_json_val is None or (isinstance(meta_json_val, float) and pd.isna(meta_json_val)):
            return "[interactive]"
        try:
            obj = meta_json_val if isinstance(meta_json_val, dict) else json.loads(str(meta_json_val))
        except Exception:
            return "[interactive]"
        if isinstance(obj, dict) and obj.get("type"):
            return f"[{obj.get('type')}]"
        return "[interactive]"

    # ---------------------------
    # Page styling (outside iframe)
    # ---------------------------
    st.markdown(
        """
        <style>
        [data-testid="stAppViewContainer"] { background:#f0f2f5 !important; }
        div[data-testid="stVerticalBlock"] { gap: 0.65rem; }

        .wa-card { background:#fff; border:1px solid #d1d7db; border-radius:12px; overflow:hidden; }
        .wa-card-head { background:#f0f2f5; padding:12px 14px; font-weight:800; border-bottom:1px solid #d1d7db; }

        .chat-row { display:flex; gap:10px; align-items:center; padding:10px 12px; border-bottom:1px solid #f1f3f4; }
        .chat-row:hover { background:#f5f6f6; }
        .chat-row.active { background:#e9edef; }

        .av-sm { width:34px; height:34px; border-radius:50%; display:flex; align-items:center; justify-content:center; color:#fff; font-weight:900; }

        .chat-title { font-weight:800; color:#111b21; }
        .chat-snippet { font-size:12px; color:#667781; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("💬 WhatsApp Inbox")

    # ---------------------------
    # Load conversations
    # ---------------------------
    st.session_state.wa_inbox_search = st.text_input(
        "Search",
        value=st.session_state.wa_inbox_search,
        placeholder="Search by number or text…",
        label_visibility="collapsed",
    )

    conv_df = db.fetch_inbox_conversations(q_search=st.session_state.wa_inbox_search, limit=80)
    if conv_df is None or conv_df.empty:
        st.info("No conversations found.")
        return

    wa_list = conv_df["wa_number"].astype(str).tolist()
    if st.session_state.wa_selected_number is None or st.session_state.wa_selected_number not in wa_list:
        st.session_state.wa_selected_number = wa_list[0]
        st.session_state.wa_msg_cache = None

    left, right = st.columns([1, 2.6], gap="large")

    # ---------------------------
    # LEFT: Chat list
    # ---------------------------
    with left:
        st.markdown('<div class="wa-card"><div class="wa-card-head">Chats</div>', unsafe_allow_html=True)

        for _, row in conv_df.iterrows():
            wa = str(row["wa_number"])
            snippet = _strip_html_if_needed(_s(row.get("body_text")) or "")
            av_bg = _avatar_color(wa)
            av_txt = _initials(wa)

            st.markdown(
                f"""
                <div class="chat-row">
                    <div class="av-sm" style="background:{av_bg}">{html.escape(av_txt)}</div>
                    <div>
                        <div class="chat-title">{html.escape(wa)}</div>
                        <div class="chat-snippet">{html.escape(snippet)}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if st.button(f"Open {wa}", key=f"open_{wa}", use_container_width=True):
                st.session_state.wa_selected_number = wa
                st.session_state.wa_msg_cache = None
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    # ---------------------------
    # RIGHT: Chat Pane
    # ---------------------------
    with right:
        wa = st.session_state.wa_selected_number

        if st.session_state.wa_msg_cache is None:
            st.session_state.wa_msg_cache = db.fetch_conversation_messages(wa, limit=200, before_id=None)

        df = st.session_state.wa_msg_cache
        if df is None or df.empty:
            st.info("No messages yet.")
            return

        df = df.sort_values("id")

        msgs_html = ""
        for _, msg in df.iterrows():
            direction = _s(msg.get("direction")).lower()
            dt = _dt_kenya(msg.get("created_at"))
            if not dt:
                continue
            side = "out" if direction == "outbound" else "in"
            body = _strip_html_if_needed(msg.get("body_text"))
            time_txt = dt.strftime("%H:%M")

            msgs_html += f"""
            <div class="row {side}">
              <div class="bubble {side}">
                {html.escape(body)}
                <div class="foot">{time_txt}</div>
              </div>
            </div>
            """

        chat_doc = f"""
        <!doctype html>
        <html>
        <head>
          <meta charset="utf-8" />
          <style>
            html, body {{ height:100%; margin:0; }}

            body {{
              font-family:system-ui;
              background:#efeae2;
            }}

            .wrap {{
              height:100%;
              display:flex;
              flex-direction:column;
              border:1px solid #d1d7db;
              border-radius:12px;
              overflow:hidden;
            }}

            .body {{
              flex:1;
              overflow-y:auto;
              padding:14px;

              background-color:#efeae2;
              background-image:url("https://user-images.githubusercontent.com/15075759/28719144-86dc0f70-73b1-11e7-911d-60d70fcded21.png");
              background-repeat:repeat;
              background-size:420px auto;
            }}

            .row {{ display:flex; margin:4px 0; }}
            .row.out {{ justify-content:flex-end; }}
            .row.in {{ justify-content:flex-start; }}

            .bubble {{
              max-width:68%;
              padding:8px 10px;
              border-radius:8px;
              font-size:14px;
            }}

            .bubble.out {{ background:#d9fdd3; }}
            .bubble.in {{ background:#fff; }}

            .foot {{
              font-size:11px;
              color:#667781;
              text-align:right;
            }}
          </style>
        </head>
        <body>
          <div class="wrap">
            <div class="body" id="body">
              {msgs_html}
            </div>
          </div>
          <script>
            const b = document.getElementById("body");
            b.scrollTop = b.scrollHeight;
          </script>
        </body>
        </html>
        """

        components.html(chat_doc, height=620, scrolling=False)
