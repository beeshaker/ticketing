# whatsapp_inbox.py
# PRIVATE MODULE (not in /pages)
# Call it from main.py like: whatsapp_inbox_page(db)
#
# Requires Conn methods:
#   - fetch_inbox_conversations(q_search: str|None, limit: int) -> pd.DataFrame
#   - fetch_conversation_messages(wa_number: str, limit: int, before_id: int|None) -> pd.DataFrame
#   - send_whatsapp_notification(to: str, message: str) -> dict

from __future__ import annotations

import re
import json
import html
import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

# Timezone: Kenya (Africa/Nairobi)
KENYA_TZ = ZoneInfo("Africa/Nairobi")


def whatsapp_inbox_page(db):
    if "authenticated" not in st.session_state or not st.session_state["authenticated"]:
        st.error("Please login first.")
        st.stop()

    # ---------------------------
    # Session State
    # ---------------------------
    st.session_state.setdefault("wa_selected_number", None)
    st.session_state.setdefault("wa_msg_cache", None)
    st.session_state.setdefault("wa_inbox_search", "")
    st.session_state.setdefault("wa_show_typing", False)

    # ---------------------------
    # Helpers
    # ---------------------------
    def safe_text(x) -> str:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return ""
        return str(x)

    def strip_html_if_needed(s: str) -> str:
        """
        If body_text accidentally contains HTML (e.g. "<div class='msg-row'>..."),
        strip tags so it doesn't show as a giant code block in bubbles.
        """
        s = safe_text(s)
        if "<div" in s.lower() or "<span" in s.lower() or "<br" in s.lower() or "</" in s:
            s = re.sub(r"<[^>]+>", "", s)  # remove tags
            s = re.sub(r"\s+\n", "\n", s)
            s = re.sub(r"\n{3,}", "\n\n", s)
            s = s.strip()
        return s

    def dt_to_kenya(x) -> datetime | None:
        """
        Your DB stores Kenya-local naive timestamps (DATETIME).
        So:
          - if naive: localize as Kenya (DO NOT treat as UTC)
          - if tz-aware: convert to Kenya
        """
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return None
        dt = pd.to_datetime(x, errors="coerce")
        if pd.isna(dt):
            return None
        if getattr(dt, "tzinfo", None) is None:
            return dt.tz_localize(KENYA_TZ)
        return dt.tz_convert(KENYA_TZ)

    def avatar_seed_color(seed: str) -> str:
        palette = ["#25D366", "#128C7E", "#34B7F1", "#6C5CE7", "#E17055", "#00B894", "#0984E3", "#D63031"]
        n = sum(ord(c) for c in (seed or ""))
        return palette[n % len(palette)]

    def initials_from_number(wa: str) -> str:
        wa = safe_text(wa).strip()
        if len(wa) >= 2:
            return wa[-2:]
        return "WA"

    def status_ticks(direction: str, status: str) -> str:
        """
        WhatsApp-ish:
          sent -> ✓
          delivered -> ✓✓ (grey)
          read/seen -> ✓✓ (blue)
        """
        if (safe_text(direction).lower() != "outbound"):
            return ""

        s = safe_text(status).lower().strip()
        if not s:
            return ""
        if s in {"sent", "queued", "accepted"}:
            return '<span class="ticks ticks-grey">✓</span>'
        if s in {"delivered"}:
            return '<span class="ticks ticks-grey">✓✓</span>'
        if s in {"read", "seen"}:
            return '<span class="ticks ticks-blue">✓✓</span>'
        return '<span class="ticks ticks-grey">✓✓</span>'

    def parse_interactive(meta_json_val) -> str:
        """
        Best-effort render for interactive messages if body_text is NULL.
        Your table has meta_json like {"type":"interactive", ...}.
        """
        if meta_json_val is None or (isinstance(meta_json_val, float) and pd.isna(meta_json_val)):
            return "[interactive]"
        try:
            obj = meta_json_val if isinstance(meta_json_val, dict) else json.loads(str(meta_json_val))
        except Exception:
            return "[interactive]"

        # common: list buttons in order if present
        # We'll just dump something readable.
        if isinstance(obj, dict):
            t = obj.get("type")
            if t:
                return f"[{t}]"
        return "[interactive]"

    # ---------------------------
    # CSS: WhatsApp clone look
    # ---------------------------
    st.markdown(
        """
        <style>
        /* overall */
        [data-testid="stAppViewContainer"] { background:#f0f2f5 !important; }
        [data-testid="stHeader"] { background:transparent; }

        /* WhatsApp split panels */
        .wa-wrap{display:flex; gap:16px; align-items:stretch;}
        .wa-left{background:#fff;border:1px solid #d1d7db;border-radius:10px;overflow:hidden;}
        .wa-right{background:#efeae2;border:1px solid #d1d7db;border-radius:10px;overflow:hidden;}

        /* left header */
        .wa-left-head{
            background:#f0f2f5;
            padding:12px 14px;
            border-bottom:1px solid #d1d7db;
            font-weight:800;
            color:#111b21;
        }

        /* chat list item */
        .chat-item{
            display:flex;
            gap:10px;
            align-items:center;
            padding:10px 12px;
            border-bottom:1px solid #f1f3f4;
            cursor:pointer;
        }
        .chat-item:hover{background:#f5f6f6;}
        .chat-item.active{background:#e9edef;}
        .av-sm{
            width:34px;height:34px;border-radius:50%;
            display:flex;align-items:center;justify-content:center;
            color:#fff;font-weight:800;flex:0 0 auto;
        }
        .chat-meta{min-width:0;}
        .chat-title{font-weight:700;color:#111b21;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
        .chat-snippet{font-size:12px;color:#667781;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}

        /* right header bar */
        .wa-head{
            background:#075e54;
            color:#fff;
            padding:10px 12px;
            display:flex;
            align-items:center;
            justify-content:space-between;
            gap:12px;
        }
        .wa-head-left{display:flex;align-items:center;gap:10px;min-width:0;}
        .av{
            width:38px;height:38px;border-radius:50%;
            display:flex;align-items:center;justify-content:center;
            color:#fff;font-weight:900;flex:0 0 auto;
        }
        .wa-head-title{font-weight:800;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
        .wa-head-sub{font-size:12px;opacity:0.85;}
        .wa-head-actions{display:flex;gap:8px;opacity:0.95;}
        .wa-pill{background:rgba(255,255,255,0.15);border:1px solid rgba(255,255,255,0.2);padding:6px 10px;border-radius:999px;font-size:12px;}

        /* chat body (NO wallpaper image) */
        .chat-container{
            height:68vh;
            overflow-y:auto;
            padding:14px 14px 10px 14px;
            background:#efeae2;   /* clean background */
            background-image:none !important; /* REMOVE WALLPAPER */
        }

        /* date separator */
        .date-divider{display:flex;justify-content:center;margin:12px 0;}
        .date-divider span{
            background:#fff;
            border:1px solid rgba(0,0,0,0.08);
            padding:5px 12px;
            border-radius:8px;
            font-size:12px;
            color:#54656f;
            box-shadow:0 1px 0.5px rgba(0,0,0,0.08);
        }

        /* system status chip */
        .sys{display:flex;justify-content:center;margin:10px 0;}
        .sys span{
            background:rgba(255,255,255,0.85);
            border:1px solid rgba(0,0,0,0.08);
            color:#54656f;
            font-size:12px;
            padding:5px 10px;
            border-radius:999px;
        }

        /* bubbles */
        .msg-row{display:flex;margin:4px 0;width:100%;}
        .msg-row.out{justify-content:flex-end;}
        .msg-row.in{justify-content:flex-start;}
        .bubble{
            padding:7px 10px 18px 10px;
            max-width:68%;
            font-size:14px;
            position:relative;
            border-radius:8px;
            box-shadow:0 1px 0.5px rgba(0,0,0,0.13);
            border:1px solid rgba(0,0,0,0.04);
            white-space:pre-wrap;
            word-wrap:break-word;
            color:#111b21;
        }
        .bubble.out{background:#d9fdd3;border-top-right-radius:0;}
        .bubble.in{background:#fff;border-top-left-radius:0;}
        .bubble.out::after{
            content:"";position:absolute;right:-8px;top:0;
            width:0;height:0;border-left:10px solid #d9fdd3;border-bottom:10px solid transparent;
        }
        .bubble.in::after{
            content:"";position:absolute;left:-8px;top:0;
            width:0;height:0;border-right:10px solid #fff;border-bottom:10px solid transparent;
        }
        .msg-footer{
            position:absolute;right:8px;bottom:4px;
            display:flex;gap:6px;align-items:center;
            font-size:11px;color:#667781;
        }
        .ticks{font-weight:900;letter-spacing:-1px;}
        .ticks-grey{color:#8696a0;}
        .ticks-blue{color:#53beec;}

        /* typing indicator */
        .typing{display:flex;justify-content:flex-start;margin:6px 0;}
        .typing .bubble{border-radius:18px;padding:10px 12px;}
        .dots{display:inline-flex;gap:4px;}
        .dot{width:6px;height:6px;border-radius:50%;background:#8696a0;opacity:0.55;animation:dot 1.2s infinite ease-in-out;}
        .dot:nth-child(2){animation-delay:0.15s;}
        .dot:nth-child(3){animation-delay:0.30s;}
        @keyframes dot{0%,80%,100%{transform:translateY(0);opacity:0.45;}40%{transform:translateY(-3px);opacity:0.95;}}

        /* composer */
        .composer{
            background:#f0f2f5;
            border-top:1px solid #d1d7db;
            padding:10px 12px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ---------------------------
    # Data: conversations
    # ---------------------------
    conv_df = db.fetch_inbox_conversations(q_search=st.session_state.wa_inbox_search, limit=80)

    left, right = st.columns([1, 2.8], gap="large")

    # ---------------------------
    # LEFT PANE
    # ---------------------------
    with left:
        st.markdown('<div class="wa-left"><div class="wa-left-head">Chats</div></div>', unsafe_allow_html=True)

        st.session_state.wa_inbox_search = st.text_input(
            "Search",
            value=st.session_state.wa_inbox_search,
            placeholder="Search…",
            label_visibility="collapsed",
        )

        if conv_df is None or conv_df.empty:
            st.info("No conversations found.")
            return

        # choose a default chat if none selected
        wa_list = conv_df["wa_number"].astype(str).tolist()
        if st.session_state.wa_selected_number is None or st.session_state.wa_selected_number not in wa_list:
            st.session_state.wa_selected_number = wa_list[0]

        # Render chat list as clickable rows (buttons)
        for _, row in conv_df.iterrows():
            wa = str(row["wa_number"])
            snippet = safe_text(row.get("body_text")) or safe_text(row.get("template_name")) or ""
            snippet = strip_html_if_needed(snippet)
            if len(snippet) > 30:
                snippet = snippet[:30] + "…"

            active = "active" if wa == st.session_state.wa_selected_number else ""
            av_bg = avatar_seed_color(wa)
            av_txt = initials_from_number(wa)

            # Use a button but style visually like a list row
            clicked = st.button(f"{wa}", key=f"chat_{wa}", use_container_width=True)
            # We also show a little "fake" row above the button using HTML
            st.markdown(
                f"""
                <div class="chat-item {active}">
                  <div class="av-sm" style="background:{av_bg}">{html.escape(av_txt)}</div>
                  <div class="chat-meta">
                    <div class="chat-title">{html.escape(wa)}</div>
                    <div class="chat-snippet">{html.escape(snippet) if snippet else " "}</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if clicked:
                st.session_state.wa_selected_number = wa
                st.session_state.wa_msg_cache = None
                st.rerun()

    # ---------------------------
    # RIGHT PANE (Chat)
    # ---------------------------
    with right:
        wa_num = st.session_state.wa_selected_number
        if not wa_num:
            st.info("Select a conversation")
            return

        av_bg = avatar_seed_color(wa_num)
        av_txt = initials_from_number(wa_num)

        # Header bar
        st.markdown(
            f"""
            <div class="wa-right">
              <div class="wa-head">
                <div class="wa-head-left">
                  <div class="av" style="background:{av_bg}">{html.escape(av_txt)}</div>
                  <div style="min-width:0;">
                    <div class="wa-head-title">{html.escape(wa_num)}</div>
                    <div class="wa-head-sub">{'typing…' if st.session_state.wa_show_typing else 'online'}</div>
                  </div>
                </div>
                <div class="wa-head-actions">
                  <div class="wa-pill">🔍</div>
                  <div class="wa-pill">⋮</div>
                </div>
              </div>
            """,
            unsafe_allow_html=True,
        )

        # Load messages
        if st.session_state.wa_msg_cache is None:
            st.session_state.wa_msg_cache = db.fetch_conversation_messages(wa_num, limit=150, before_id=None)

        df = st.session_state.wa_msg_cache

        chat_html = '<div class="chat-container">'

        if df is not None and not df.empty:
            df = df.sort_values("id")

            last_date = None
            for _, msg in df.iterrows():
                direction = safe_text(msg.get("direction")).lower().strip()
                mtype = safe_text(msg.get("message_type")).lower().strip()
                status = safe_text(msg.get("status")).lower().strip()

                # timestamp
                dt_obj = dt_to_kenya(msg.get("created_at"))
                if dt_obj is None:
                    continue

                curr_date = dt_obj.strftime("%d %b %Y")
                if curr_date != last_date:
                    chat_html += f'<div class="date-divider"><span>{html.escape(curr_date)}</span></div>'
                    last_date = curr_date

                side = "out" if direction == "outbound" else "in"

                # Content selection (NO "None")
                body = strip_html_if_needed(msg.get("body_text"))
                tpl = safe_text(msg.get("template_name"))
                meta_json_val = msg.get("meta_json") if "meta_json" in df.columns else None

                content = ""
                if body:
                    content = body
                elif tpl:
                    content = f"📌 Template: {tpl}"
                elif mtype == "interactive":
                    content = parse_interactive(meta_json_val)
                elif mtype == "status":
                    # render as system chip instead of bubble
                    sys_txt = status or "status update"
                    chat_html += f'<div class="sys"><span>{html.escape(sys_txt)}</span></div>'
                    continue
                else:
                    # If it's not a status and still empty, skip silently
                    continue

                # Escape content to avoid HTML injection in UI
                content_html = html.escape(content)

                ticks = status_ticks(direction=direction, status=status)
                time_txt = dt_obj.strftime("%H:%M")

                chat_html += f"""
                    <div class="msg-row {side}">
                        <div class="bubble {side}">
                            {content_html}
                            <div class="msg-footer">{time_txt} {ticks}</div>
                        </div>
                    </div>
                """

        # Typing indicator (UI-only)
        if st.session_state.wa_show_typing:
            chat_html += """
                <div class="typing">
                  <div class="bubble in">
                    <span class="dots">
                      <span class="dot"></span><span class="dot"></span><span class="dot"></span>
                    </span>
                  </div>
                </div>
            """

        chat_html += "</div>"
        st.markdown(chat_html, unsafe_allow_html=True)

        # Composer
        st.markdown('<div class="composer">', unsafe_allow_html=True)

        c0, c1, c2 = st.columns([0.9, 5, 1.2])
        with c0:
            if st.button("💬 Typing", use_container_width=True):
                st.session_state.wa_show_typing = not st.session_state.wa_show_typing
                st.rerun()

        with c1:
            reply = st.text_input("Type a message", placeholder="Message", label_visibility="collapsed")

        with c2:
            if st.button("Send", use_container_width=True) and reply.strip():
                db.send_whatsapp_notification(to=wa_num, message=reply.strip())
                st.session_state.wa_msg_cache = None
                st.rerun()

        st.markdown("</div></div>", unsafe_allow_html=True)  # close composer + wa-right
