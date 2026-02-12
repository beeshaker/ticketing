import json
import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

KENYA_TZ = ZoneInfo("Africa/Nairobi")

def whatsapp_inbox_page(db):
    # --- Auth & Session State ---
    if "authenticated" not in st.session_state or not st.session_state["authenticated"]:
        st.error("Please login first.")
        st.stop()

    st.session_state.setdefault("wa_selected_number", None)
    st.session_state.setdefault("wa_msg_cache", None)

    # --- Inject Improved WhatsApp CSS ---
    st.markdown(
        """
        <style>
        /* Global Page Adjustments */
        [data-testid="stAppViewContainer"] {
            background-color: #f0f2f5;
        }
        .main .block-container {
            padding: 0;
            max-width: 95%;
        }

        /* Sidebar/Left Column Styling */
        [data-testid="stVerticalBlock"] > div:has(div.wa-left-container) {
            background: white;
            border-right: 1px solid #d1d7db;
            height: 100vh;
        }

        /* Chat Container (Right) */
        .chat-container {
            display: flex;
            flex-direction: column;
            height: 85vh;
            background-color: #efeae2; /* WhatsApp Wallpaper Color */
            position: relative;
            border: 1px solid #d1d7db;
            border-radius: 8px;
            overflow: hidden;
        }

        /* Sticky Header */
        .chat-header {
            background: #f0f2f5;
            padding: 10px 16px;
            display: flex;
            align-items: center;
            border-bottom: 1px solid #d1d7db;
            z-index: 10;
        }

        /* Scrollable Message Area */
        .message-area {
            flex-grow: 1;
            overflow-y: auto;
            padding: 20px 7%;
            display: flex;
            flex-direction: column;
        }

        /* Date Separator */
        .date-divider {
            text-align: center;
            margin: 12px 0;
        }
        .date-divider span {
            background: #ffffff;
            padding: 5px 12px;
            border-radius: 7px;
            font-size: 12.5px;
            color: #54656f;
            box-shadow: 0 1px 0.5px rgba(11,20,26,.13);
        }

        /* Message Bubbles */
        .msg-row {
            display: flex;
            margin-bottom: 2px;
            width: 100%;
        }
        .msg-row.out { justify-content: flex-end; }
        .msg-row.in { justify-content: flex-start; }

        .bubble {
            padding: 6px 7px 8px 9px;
            max-width: 65%;
            font-size: 14.2px;
            position: relative;
            border-radius: 7.5px;
            box-shadow: 0 1px 0.5px rgba(11,20,26,.13);
        }
        .bubble.out {
            background-color: #d9fdd3;
            border-top-right-radius: 0;
        }
        .bubble.in {
            background-color: #ffffff;
            border-top-left-radius: 0;
        }

        /* Tail effect (Simplified) */
        .bubble.out::after {
            content: "";
            position: absolute;
            right: -8px; top: 0;
            width: 0; height: 0;
            border-left: 10px solid #d9fdd3;
            border-bottom: 10px solid transparent;
        }
        .bubble.in::after {
            content: "";
            position: absolute;
            left: -8px; top: 0;
            width: 0; height: 0;
            border-right: 10px solid #ffffff;
            border-bottom: 10px solid transparent;
        }

        .msg-footer {
            display: flex;
            justify-content: flex-end;
            align-items: center;
            gap: 4px;
            margin-top: -4px;
            font-size: 11px;
            color: #667781;
        }

        /* Input Area */
        .input-bar {
            background: #f0f2f5;
            padding: 10px 16px;
            border-top: 1px solid #d1d7db;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # --- Data Fetching ---
    conv_df = db.fetch_inbox_conversations(q_search=st.session_state.get("wa_inbox_search", ""), limit=50)
    
    # --- UI Layout ---
    left, right = st.columns([1, 2.5])

    with left:
        st.subheader("Chats")
        search = st.text_input("Search", placeholder="Search or start new chat", label_visibility="collapsed")
        
        if conv_df is not None and not conv_df.empty:
            for _, row in conv_df.iterrows():
                wa = str(row['wa_number'])
                # Clickable chat row
                if st.button(f"👤 {wa[:12]}...", key=f"btn_{wa}", use_container_width=True):
                    st.session_state.wa_selected_number = wa
                    st.session_state.wa_msg_cache = None
                    st.rerun()

    with right:
        if not st.session_state.wa_selected_number:
            st.info("Select a conversation to start messaging")
        else:
            wa_num = st.session_state.wa_selected_number
            
            # Load messages
            if st.session_state.wa_msg_cache is None:
                st.session_state.wa_msg_cache = db.fetch_conversation_messages(wa_num, limit=50, before_id=None)
            
            df = st.session_state.wa_msg_cache

            # 1. Header
            st.markdown(f"""
                <div class="chat-header">
                    <div style="width: 40px; height: 40px; background: #00a884; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; margin-right: 15px;">
                        {wa_num[-2:]}
                    </div>
                    <div>
                        <div style="font-weight: 500; color: #111b21;">{wa_num}</div>
                        <div style="font-size: 12px; color: #667781;">online</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

            # 2. Message Area (The "Tape")
            chat_html = '<div class="message-area">'
            if df is not None and not df.empty:
                df = df.sort_values("id")
                last_date = None
                
                for _, msg in df.iterrows():
                    curr_date = pd.to_datetime(msg['created_at']).strftime("%d %b %Y")
                    if curr_date != last_date:
                        chat_html += f'<div class="date-divider"><span>{curr_date}</span></div>'
                        last_date = curr_date
                    
                    direction = str(msg['direction']).lower()
                    side = "out" if direction == "outbound" else "in"
                    time_str = pd.to_datetime(msg['created_at']).strftime("%H:%M")
                    
                    # Tick logic
                    ticks = ""
                    if side == "out":
                        status = str(msg.get('status', '')).lower()
                        if status in ['read', 'seen']: ticks = '<span style="color: #53beec;">✓✓</span>'
                        elif status == 'delivered': ticks = '<span style="color: #8696a0;">✓✓</span>'
                        else: ticks = '<span style="color: #8696a0;">✓</span>'

                    chat_html += f"""
                        <div class="msg-row {side}">
                            <div class="bubble {side}">
                                {msg['body_text']}
                                <div class="msg-footer">
                                    <span>{time_str}</span>
                                    <span style="margin-left:3px;">{ticks}</span>
                                </div>
                            </div>
                        </div>
                    """
            chat_html += "</div>"
            st.markdown(chat_html, unsafe_allow_html=True)

            # 3. Footer (Input)
            with st.container():
                with st.form("msg_form", clear_on_submit=True):
                    c1, c2 = st.columns([5, 1])
                    reply_text = c1.text_input("Type a message", placeholder="Type a message", label_visibility="collapsed")
                    submit = c2.form_submit_button("Send")
                    
                    if submit and reply_text:
                        db.send_whatsapp_notification(to=wa_num, message=reply_text)
                        st.session_state.wa_msg_cache = None # Force reload
                        st.rerun()

    # --- Auto-refresh Button ---
    if st.button("🔄 Refresh Messages"):
        st.session_state.wa_msg_cache = None
        st.rerun()