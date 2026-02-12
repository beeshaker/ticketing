import json
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

    # Session State
    st.session_state.setdefault("wa_selected_number", None)
    st.session_state.setdefault("wa_msg_cache", None)
    st.session_state.setdefault("wa_inbox_search", "")

    # WhatsApp Modern CSS
    st.markdown("""
        <style>
        [data-testid="stAppViewContainer"] { background-color: #f0f2f5 !important; }
        .chat-container {
            display: flex; flex-direction: column; height: 75vh;
            background-color: #efeae2;
            background-image: url("https://user-images.githubusercontent.com/15075759/28719144-86dc0f70-73b1-11e7-911d-60d70fcded21.png");
            background-repeat: repeat; border: 1px solid #d1d7db;
            border-radius: 0 0 8px 8px; overflow-y: auto; padding: 20px 5%;
        }
        .chat-header {
            background: #f0f2f5; padding: 10px 16px; display: flex; align-items: center;
            border: 1px solid #d1d7db; border-bottom: none; border-radius: 8px 8px 0 0;
        }
        .msg-row { display: flex; margin-bottom: 4px; width: 100%; }
        .msg-row.out { justify-content: flex-end; }
        .msg-row.in { justify-content: flex-start; }
        .bubble {
            padding: 6px 12px 8px 12px; max-width: 65%; font-size: 14px;
            position: relative; border-radius: 8px; box-shadow: 0 1px 0.5px rgba(0,0,0,0.13);
        }
        .bubble.out { background-color: #d9fdd3; border-top-right-radius: 0; }
        .bubble.in { background-color: #ffffff; border-top-left-radius: 0; }
        .bubble.out::after {
            content: ""; position: absolute; right: -8px; top: 0;
            width: 0; height: 0; border-left: 10px solid #d9fdd3; border-bottom: 10px solid transparent;
        }
        .bubble.in::after {
            content: ""; position: absolute; left: -8px; top: 0;
            width: 0; height: 0; border-right: 10px solid #ffffff; border-bottom: 10px solid transparent;
        }
        .msg-footer { display: flex; justify-content: flex-end; align-items: center; font-size: 11px; color: #667781; margin-top: 2px; }
        .date-divider { text-align: center; margin: 20px 0; }
        .date-divider span { background: #ffffff; padding: 5px 15px; border-radius: 8px; font-size: 12px; color: #54656f; box-shadow: 0 1px 0.5px rgba(0,0,0,0.1); }
        </style>
    """, unsafe_allow_html=True)

    conv_df = db.fetch_inbox_conversations(q_search=st.session_state.wa_inbox_search, limit=50)
    left, right = st.columns([1, 2.8])

    with left:
        st.subheader("Chats")
        st.session_state.wa_inbox_search = st.text_input("Search", value=st.session_state.wa_inbox_search, placeholder="Search...", label_visibility="collapsed")
        if conv_df is not None and not conv_df.empty:
            for _, row in conv_df.iterrows():
                wa = str(row['wa_number'])
                if st.button(f"👤 {wa}", key=f"btn_{wa}", use_container_width=True):
                    st.session_state.wa_selected_number = wa
                    st.session_state.wa_msg_cache = None
                    st.rerun()

    with right:
        if not st.session_state.wa_selected_number:
            st.info("Select a conversation")
        else:
            wa_num = st.session_state.wa_selected_number
            st.markdown(f'<div class="chat-header"><strong>{wa_num}</strong></div>', unsafe_allow_html=True)

            if st.session_state.wa_msg_cache is None:
                st.session_state.wa_msg_cache = db.fetch_conversation_messages(wa_num, limit=100, before_id=None)
            
            df = st.session_state.wa_msg_cache
            chat_html = '<div class="chat-container">'
            
            if df is not None and not df.empty:
                df = df.sort_values("id")
                last_date = None
                for _, msg in df.iterrows():
                    # --- TZ FIX APPLIED HERE ---
                    raw_ts = pd.to_datetime(msg['created_at'])
                    dt_obj = raw_ts.tz_localize('UTC').tz_convert(KENYA_TZ) if raw_ts.tz is None else raw_ts.tz_convert(KENYA_TZ)
                    
                    curr_date = dt_obj.strftime("%d %b %Y")
                    if curr_date != last_date:
                        chat_html += f'<div class="date-divider"><span>{curr_date}</span></div>'
                        last_date = curr_date
                    
                    side = "out" if str(msg['direction']).lower() == "outbound" else "in"
                    ticks = '<span style="color:#53beec; margin-left:4px;">✓✓</span>' if side == "out" else ""
                    
                    chat_html += f"""
                        <div class="msg-row {side}">
                            <div class="bubble {side}">{msg['body_text']}
                                <div class="msg-footer">{dt_obj.strftime("%H:%M")} {ticks}</div>
                            </div>
                        </div>
                    """
            chat_html += "</div>"
            st.markdown(chat_html, unsafe_allow_html=True)

            with st.form("msg_input_form", clear_on_submit=True):
                c1, c2 = st.columns([5, 1])
                reply = c1.text_input("Type a message", label_visibility="collapsed")
                if c2.form_submit_button("Send", use_container_width=True) and reply:
                    db.send_whatsapp_notification(to=wa_num, message=reply)
                    st.session_state.wa_msg_cache = None
                    st.rerun()