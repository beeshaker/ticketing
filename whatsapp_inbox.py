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

    # ---------------------------
    # Helpers
    # ---------------------------
    def _s(x) -> str:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return ""
        return str(x)

    def _strip_html_if_needed(s: str) -> str:
        s = _s(s)
        # If DB accidentally contains HTML layout, strip tags.
        if "<div" in s.lower() or "<span" in s.lower() or "</" in s.lower():
            s = re.sub(r"<[^>]+>", "", s)
            s = re.sub(r"\n{3,}", "\n\n", s)
            s = s.strip()
        return s

    def _dt_kenya(x) -> datetime | None:
        """
        DB timestamps are Kenya-local naive DATETIME.
        So: if naive => localize as Kenya (NOT UTC).
        """
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return None
        dt = pd.to_datetime(x, errors="coerce")
        if pd.isna(dt):
            return None
        if getattr(dt, "tzinfo", None) is None:
            return dt.to_pydatetime().replace(tzinfo=KENYA_TZ)
        return dt.to_pydatetime().astimezone(KENYA_TZ)

    def _avatar_color(seed: str) -> str:
        palette = ["#25D366", "#128C7E", "#34B7F1", "#6C5CE7", "#E17055", "#00B894", "#0984E3", "#D63031"]
        n = sum(ord(c) for c in (seed or ""))
        return palette[n % len(palette)]

    def _initials(wa: str) -> str:
        wa = _s(wa).strip()
        return wa[-2:] if len(wa) >= 2 else "WA"

    def _ticks(direction: str, status: str) -> str:
        if _s(direction).lower().strip() != "outbound":
            return ""
        s = _s(status).lower().strip()
        if not s:
            return ""
        if s in {"sent", "queued", "accepted"}:
            return '<span class="ticks grey">✓</span>'
        if s in {"delivered"}:
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
        .wa-grid { display:grid; grid-template-columns: 320px 1fr; gap:16px; align-items:start; }
        .wa-card { background:#fff; border:1px solid #d1d7db; border-radius:12px; overflow:hidden; }
        .wa-card-head { background:#f0f2f5; padding:12px 14px; font-weight:800; border-bottom:1px solid #d1d7db; }
        .chat-row { display:flex; gap:10px; align-items:center; padding:10px 12px; border-bottom:1px solid #f1f3f4; }
        .chat-row:hover { background:#f5f6f6; }
        .chat-row.active { background:#e9edef; }
        .av-sm { width:34px; height:34px; border-radius:50%; display:flex; align-items:center; justify-content:center; color:#fff; font-weight:900; }
        .chat-meta { min-width:0; }
        .chat-title { font-weight:800; color:#111b21; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .chat-snippet { font-size:12px; color:#667781; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
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

    # ---------------------------
    # Layout
    # ---------------------------
    left, right = st.columns([1, 2.6], gap="large")

    # ---------------------------
    # LEFT: Chat list
    # ---------------------------
    with left:
        st.markdown('<div class="wa-card"><div class="wa-card-head">Chats</div>', unsafe_allow_html=True)

        for _, row in conv_df.iterrows():
            wa = str(row["wa_number"])
            snippet = _strip_html_if_needed(_s(row.get("body_text")) or _s(row.get("template_name")) or "")
            if len(snippet) > 30:
                snippet = snippet[:30] + "…"

            active = "active" if wa == st.session_state.wa_selected_number else ""
            av_bg = _avatar_color(wa)
            av_txt = _initials(wa)

            # Visual row
            st.markdown(
                f"""
                <div class="chat-row {active}">
                    <div class="av-sm" style="background:{av_bg}">{html.escape(av_txt)}</div>
                    <div class="chat-meta">
                        <div class="chat-title">{html.escape(wa)}</div>
                        <div class="chat-snippet">{html.escape(snippet) if snippet else "&nbsp;"}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Click handler (button)
            if st.button(f"Open {wa}", key=f"open_{wa}", use_container_width=True):
                st.session_state.wa_selected_number = wa
                st.session_state.wa_msg_cache = None
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    # ---------------------------
    # RIGHT: WhatsApp clone chat pane (iframe)
    # ---------------------------
    with right:
        wa = st.session_state.wa_selected_number

        # Load thread
        if st.session_state.wa_msg_cache is None:
            st.session_state.wa_msg_cache = db.fetch_conversation_messages(wa, limit=200, before_id=None)

        df = st.session_state.wa_msg_cache
        if df is None or df.empty:
            st.info("No messages for this conversation yet.")
            return

        df = df.sort_values("id")

        # Build chat HTML inside an iframe (pixel-perfect + reliable)
        av_bg = _avatar_color(wa)
        av_txt = _initials(wa)

        msgs_html = ""
        last_date = None

        for _, msg in df.iterrows():
            direction = _s(msg.get("direction")).lower().strip()
            mtype = _s(msg.get("message_type")).lower().strip()
            status = _s(msg.get("status")).lower().strip()

            dt = _dt_kenya(msg.get("created_at"))
            if not dt:
                continue

            day = dt.strftime("%d %b %Y")
            if day != last_date:
                msgs_html += f'<div class="date"><span>{html.escape(day)}</span></div>'
                last_date = day

            # status rows (center chip)
            if mtype == "status":
                sys_txt = status or "status update"
                msgs_html += f'<div class="sys"><span>{html.escape(sys_txt)}</span></div>'
                continue

            side = "out" if direction == "outbound" else "in"

            body = _strip_html_if_needed(msg.get("body_text"))
            tpl = _s(msg.get("template_name"))
            meta_json = msg.get("meta_json") if "meta_json" in df.columns else None

            if body:
                content = body
            elif tpl:
                content = f"📌 Template: {tpl}"
            elif mtype == "interactive":
                content = _render_interactive(meta_json)
            else:
                # skip empty
                continue

            ticks = _ticks(direction, status)
            time_txt = dt.strftime("%H:%M")

            msgs_html += f"""
            <div class="row {side}">
              <div class="bubble {side}">
                {html.escape(content)}
                <div class="foot">{time_txt} {ticks}</div>
              </div>
            </div>
            """

        typing_html = ""
        if st.session_state.wa_show_typing:
            typing_html = """
            <div class="row in">
              <div class="bubble in typing">
                <span class="dots"><i></i><i></i><i></i></span>
              </div>
            </div>
            """

        chat_doc = f"""
        <!doctype html>
        <html>
        <head>
          <meta charset="utf-8" />
          <style>
            html, body {{ height: 100%; }}
            body{{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial;background:#efeae2;}}
            .wrap{{height:100%;display:flex;flex-direction:column;border:1px solid #d1d7db;border-radius:12px;overflow:hidden;background:#efeae2;}}
            .head{{background:#075e54;color:#fff;padding:10px 12px;display:flex;align-items:center;justify-content:space-between;gap:12px;}}
            .headL{{display:flex;align-items:center;gap:10px;min-width:0;}}
            .av{{width:38px;height:38px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:900;background:{av_bg};}}
            .title{{font-weight:900;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
            .sub{{font-size:12px;opacity:.85;}}
            .pill{{background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.2);padding:6px 10px;border-radius:999px;font-size:12px;}}
            .body{{flex:1;overflow-y:auto;padding:14px;background:#efeae2;}}
            .date{{display:flex;justify-content:center;margin:12px 0;}}
            .date span{{background:#fff;border:1px solid rgba(0,0,0,.08);padding:5px 12px;border-radius:8px;font-size:12px;color:#54656f;}}
            .sys{{display:flex;justify-content:center;margin:10px 0;}}
            .sys span{{background:rgba(255,255,255,.85);border:1px solid rgba(0,0,0,.08);color:#54656f;font-size:12px;padding:5px 10px;border-radius:999px;}}
            .row{{display:flex;margin:4px 0;width:100%;}}
            .row.out{{justify-content:flex-end;}}
            .row.in{{justify-content:flex-start;}}
            .bubble{{max-width:68%;padding:7px 10px 18px 10px;position:relative;border-radius:8px;box-shadow:0 1px .5px rgba(0,0,0,.13);border:1px solid rgba(0,0,0,.04);white-space:pre-wrap;word-wrap:break-word;color:#111b21;font-size:14px;}}
            .bubble.out{{background:#d9fdd3;border-top-right-radius:0;}}
            .bubble.in{{background:#fff;border-top-left-radius:0;}}
            .bubble.out:after{{content:"";position:absolute;right:-8px;top:0;width:0;height:0;border-left:10px solid #d9fdd3;border-bottom:10px solid transparent;}}
            .bubble.in:after{{content:"";position:absolute;left:-8px;top:0;width:0;height:0;border-right:10px solid #fff;border-bottom:10px solid transparent;}}
            .foot{{position:absolute;right:8px;bottom:4px;display:flex;gap:6px;align-items:center;font-size:11px;color:#667781;}}
            .ticks{{font-weight:900;letter-spacing:-1px;}}
            .grey{{color:#8696a0;}}
            .blue{{color:#53beec;}}
            .typing{{border-radius:18px;padding:10px 12px;}}
            .dots{{display:inline-flex;gap:4px;}}
            .dots i{{width:6px;height:6px;border-radius:50%;background:#8696a0;opacity:.55;display:inline-block;animation:dot 1.2s infinite ease-in-out;}}
            .dots i:nth-child(2){{animation-delay:.15s;}}
            .dots i:nth-child(3){{animation-delay:.30s;}}
            @keyframes dot{{0%,80%,100%{{transform:translateY(0);opacity:.45;}}40%{{transform:translateY(-3px);opacity:.95;}}}}
          </style>
        </head>
        <body>
          <div class="wrap">
            <div class="head">
              <div class="headL">
                <div class="av">{html.escape(av_txt)}</div>
                <div style="min-width:0">
                  <div class="title">{html.escape(wa)}</div>
                  <div class="sub">{'typing…' if st.session_state.wa_show_typing else 'online'}</div>
                </div>
              </div>
              <div style="display:flex;gap:8px">
                <div class="pill">🔍</div>
                <div class="pill">⋮</div>
              </div>
            </div>
            <div class="body" id="body">
              {msgs_html}
              {typing_html}
            </div>
          </div>
          <script>
            // auto-scroll to bottom
            const b = document.getElementById("body");
            b.scrollTop = b.scrollHeight;
          </script>
        </body>
        </html>
        """

        components.html(chat_doc, height=620, scrolling=False)

        # Controls + composer (Streamlit side)
        cA, cB = st.columns([1, 3])
        with cA:
            if st.button("Toggle typing…", use_container_width=True):
                st.session_state.wa_show_typing = not st.session_state.wa_show_typing
                st.rerun()
        with cB:
            if st.button("Refresh thread", use_container_width=True):
                st.session_state.wa_msg_cache = None
                st.rerun()

        with st.form("wa_send_form", clear_on_submit=True):
            c1, c2 = st.columns([5, 1])
            msg = c1.text_input("Message", placeholder="Message", label_visibility="collapsed")
            sent = c2.form_submit_button("Send", use_container_width=True)
            if sent and msg.strip():
                db.send_whatsapp_notification(to=wa, message=msg.strip())
                st.session_state.wa_msg_cache = None
                st.rerun()
