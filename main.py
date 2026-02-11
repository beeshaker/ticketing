import streamlit as st

# -----------------------------------------------------------------------------
# ✅ Page config MUST be first Streamlit call
# -----------------------------------------------------------------------------
st.set_page_config(page_title="CRM Admin Portal", layout="wide")

import pandas as pd
import bcrypt
from io import BytesIO
from sqlalchemy.sql import text

from job_cards import job_cards_page
from job_card_pdf import build_job_card_pdf  # ✅ needed for PDF export

from conn import Conn
from license import LicenseManager
from login import login
from user_registration import user_registration_page
from create_ticket import create_ticket
from edit_admins import edit_admins
from edit_properties import edit_properties
from edit_users import edit_user
from adminsignup import admin_signup
from kpi_dashboard import KPIDashboard

from streamlit_option_menu import option_menu

# -----------------------------------------------------------------------------
# ✅ Init DB
# -----------------------------------------------------------------------------
db = Conn()

# -----------------------------------------------------------------------------
# ✅ PUBLIC BYPASS (Job Card Verification)
# IMPORTANT:
# Streamlit Cloud often loads the main script first even when visiting /verify_job_card
# So we support BOTH URL styles:
#   A) https://ticketingapricot.streamlit.app/?page=verify_job_card&id=184&t=TOKEN
#   B) https://ticketingapricot.streamlit.app/verify_job_card?id=184&t=TOKEN
#
# We detect either case and switch to the public page BEFORE license/login.
# -----------------------------------------------------------------------------
params = st.query_params

# Case A (query param router)
is_public_query = (params.get("page") == "verify_job_card")

# Case B (path-based) - Streamlit sets page_script_hash for multipage routing
# NOTE: Not always available on all versions, so we guard it.
is_public_path = False
try:
    ctx = st.runtime.scriptrunner.get_script_run_ctx()
    if ctx is not None:
        # Best-effort: if current page is already verify_job_card, do nothing.
        # If main page is being hit, ctx.page_script_hash != pages/verify_job_card hash
        # so we still switch when we see id+t in the URL (strong signal).
        is_public_path = bool(params.get("id")) and bool(params.get("t")) and (params.get("page") is None)
except Exception:
    # If ctx isn't available, we can still use id+t as a strong signal
    is_public_path = bool(params.get("id")) and bool(params.get("t")) and (params.get("page") is None)

# If either style is detected, go to the public page
if is_public_query or is_public_path:
    st.switch_page("pages/verify_job_card.py")

# -----------------------------------------------------------------------------
# Session State for Authentication
# -----------------------------------------------------------------------------
st.session_state.setdefault("authenticated", False)
st.session_state.setdefault("admin_name", "")
st.session_state.setdefault("admin_role", "")
st.session_state.setdefault("admin_id", None)

# Ticket watcher/session flags
st.session_state.setdefault("last_hash", None)
st.session_state.setdefault("last_max_id", 0)
st.session_state.setdefault("tickets_cache", None)
st.session_state.setdefault("new_ticket_flag", False)
st.session_state.setdefault("new_ticket_msg", "")

# Stable ticket selection
st.session_state.setdefault("selected_ticket_id", None)

# Filter UI state
st.session_state.setdefault("filter_property", "All")
st.session_state.setdefault("filter_unit", "")
st.session_state.setdefault("filter_due_bucket", "All")

# -----------------------------------------------------------------------------
# License check (Admin portal only)
# -----------------------------------------------------------------------------
valid_license, license_message = LicenseManager.validate_license()
if not valid_license:
    st.error(license_message)
    st.stop()

# -----------------------------------------------------------------------------
# Force login if not authenticated (Admin portal only)
# -----------------------------------------------------------------------------
if not st.session_state.authenticated:
    login()
    st.stop()

# -----------------------------------------------------------------------------
# Sidebar Menu
# -----------------------------------------------------------------------------
st.sidebar.write("Current role:", st.session_state.get("admin_role", ""))

menu_options = ["Dashboard", "Create Ticket", "Logout"]
menu_icons = ["bar-chart", "file-earmark-plus", "box-arrow-right"]

# Role-based menu injection (stable ordering)
if st.session_state.admin_role == "Admin":
    role_items = [
        ("Admin User Creation", "person-gear"),
        ("Register User", "person-plus"),
        ("Create Property", "building"),
        ("Job Cards", "file-text"),
    ]
    for label, icon in reversed(role_items):
        menu_options.insert(1, label)
        menu_icons.insert(1, icon)

elif st.session_state.admin_role == "Super Admin":
    role_items = [
        ("Admin User Creation", "person-plus"),
        ("Edit/Delete Admin", "person-x"),
        ("Register User", "person-fill-add"),
        ("Edit/Delete User", "person-fill-x"),
        ("Create Property", "building-add"),
        ("Edit/Delete Property", "building-gear"),
        ("Send Bulk Message", "envelope-paper-fill"),
        ("Admin Reassignment History", "clock-history"),
        ("KPI Dashboard", "speedometer2"),
        ("Job Cards", "file-text"),
    ]
    for label, icon in reversed(role_items):
        menu_options.insert(1, label)
        menu_icons.insert(1, icon)

with st.sidebar:
    selected = option_menu(
        menu_title="Main Menu",
        options=menu_options,
        icons=menu_icons,
        menu_icon="cast",
        default_index=0,
        orientation="vertical",
        styles={
            "container": {"padding": "5px", "background-color": "#1e1e1e"},
            "icon": {"color": "#91cfff", "font-size": "20px"},
            "nav-link": {
                "font-size": "16px",
                "text-align": "left",
                "margin": "5px 0",
                "--hover-color": "#2a2a2a",
                "color": "#dddddd",
            },
            "nav-link-selected": {
                "background-color": "#0a84ff",
                "color": "white",
                "font-weight": "bold",
            },
        },
        key="main_sidebar_menu",
    )

# -----------------------------------------------------------------------------
# Logout
# -----------------------------------------------------------------------------
if selected == "Logout":
    st.session_state.authenticated = False
    st.session_state.admin_name = ""
    st.session_state.admin_id = None
    st.session_state.admin_role = ""
    st.success("Logged out successfully.")
    st.rerun()

# -----------------------------------------------------------------------------
# Dashboard
# -----------------------------------------------------------------------------
elif selected == "Dashboard":
    st.title("📊 Operations CRM Dashboard")

    new_ticket_banner = st.empty()

    # ---- NEW TICKET WATCHER ----
    if hasattr(st, "fragment"):

        @st.fragment(run_every="15s")
        def ticket_watcher():
            current_hash = db.get_tickets_hash()

            if st.session_state.last_hash is None:
                st.session_state.last_hash = current_hash
                try:
                    st.session_state.last_max_id = int(str(current_hash).split("-")[1])
                except Exception:
                    st.session_state.last_max_id = 0
                return

            if current_hash != st.session_state.last_hash:
                try:
                    new_max_id = int(str(current_hash).split("-")[1])
                except Exception:
                    new_max_id = st.session_state.last_max_id

                if new_max_id > st.session_state.last_max_id:
                    st.session_state.new_ticket_flag = True
                    st.session_state.new_ticket_msg = f"🔔 New ticket received! Latest Ticket ID: #{new_max_id}"
                    st.session_state.tickets_cache = None

                    st.session_state.last_max_id = new_max_id
                    st.session_state.last_hash = current_hash

                    st.toast("🔔 New Ticket Received!", icon="🎫")
                    st.rerun()

                st.session_state.last_hash = current_hash

        ticket_watcher()

    else:
        st.warning(
            "Your Streamlit version does not support st.fragment(run_every=...). "
            "Upgrade Streamlit to enable refresh-only-on-new-ticket behavior."
        )

    if st.session_state.new_ticket_flag:
        new_ticket_banner.success(st.session_state.new_ticket_msg)
        st.sidebar.markdown("### 🔴 New ticket")

    # ---- SMART DATA FETCHING ----
    current_hash = db.get_tickets_hash()

    if st.session_state.last_hash is None:
        st.session_state.last_hash = current_hash
        st.session_state.tickets_cache = None
        try:
            st.session_state.last_max_id = int(str(current_hash).split("-")[1])
        except Exception:
            st.session_state.last_max_id = 0

    if st.session_state.tickets_cache is None or current_hash != st.session_state.last_hash:
        if st.session_state.admin_role in ("Admin", "Super Admin"):
            st.session_state.tickets_cache = db.fetch_tickets("All")
        else:
            st.session_state.tickets_cache = db.fetch_open_tickets(st.session_state.admin_id)

        st.session_state.last_hash = current_hash

    tickets_df_all = st.session_state.tickets_cache

    if tickets_df_all is None or tickets_df_all.empty:
        st.info("✅ No open tickets found.")
        st.stop()

    # -------------------------------------------------------------------------
    # Due date buckets
    # -------------------------------------------------------------------------
    DUE_COL = "Due_Date"
    tickets_df_all[DUE_COL] = pd.to_datetime(tickets_df_all.get(DUE_COL), errors="coerce")
    tickets_df_all["_due_date_only"] = tickets_df_all[DUE_COL].dt.date

    today = pd.Timestamp.today().date()

    tickets_df_all["days_to_due"] = tickets_df_all["_due_date_only"].apply(
        lambda d: (d - today).days if pd.notna(d) else None
    )

    tickets_df_all["_due_bucket"] = "No due date"
    tickets_df_all.loc[tickets_df_all["days_to_due"] < 0, "_due_bucket"] = "Overdue"
    tickets_df_all.loc[tickets_df_all["days_to_due"] == 0, "_due_bucket"] = "Due today"
    tickets_df_all.loc[tickets_df_all["days_to_due"].between(1, 3), "_due_bucket"] = "Upcoming"

    ICON_MAP = {"Overdue": "🔴", "Due today": "🟡", "Upcoming": "🟢", "No due date": "⚪"}

    DUE_COLORS = {
        "Overdue": "background-color: rgba(244, 67, 54, 0.12);",
        "Due today": "background-color: rgba(255, 193, 7, 0.14);",
        "Upcoming": "background-color: rgba(76, 175, 80, 0.12);",
        "No due date": "background-color: rgba(158, 158, 158, 0.10);",
    }

    def style_due_rows(row):
        bucket = row.get("_due_bucket", "No due date")
        return [DUE_COLORS.get(bucket, "")] * len(row)

    # -------------------------------------------------------------------------
    # Stats CSS (theme-aware)
    # -------------------------------------------------------------------------
    st.markdown(
        """
        <style>
        .stApp[data-theme="light"],
        [data-testid="stAppViewContainer"][data-theme="light"],
        body.streamlit-light {
          --stat-bg: rgba(255,255,255,0.92);
          --stat-border: rgba(0,0,0,0.12);
          --stat-title: rgba(0,0,0,0.78);
          --stat-value: rgba(0,0,0,0.92);
          --stat-sub: rgba(0,0,0,0.58);
          --stat-shadow: 0 8px 22px rgba(0,0,0,0.08);
        }

        .stApp[data-theme="dark"],
        [data-testid="stAppViewContainer"][data-theme="dark"],
        body.streamlit-dark {
          --stat-bg: rgba(255,255,255,0.06);
          --stat-border: rgba(255,255,255,0.12);
          --stat-title: rgba(255,255,255,0.80);
          --stat-value: rgba(255,255,255,0.96);
          --stat-sub: rgba(255,255,255,0.62);
          --stat-shadow: 0 10px 26px rgba(0,0,0,0.35);
        }

        :root{
          --stat-bg: rgba(255,255,255,0.92);
          --stat-border: rgba(0,0,0,0.12);
          --stat-title: rgba(0,0,0,0.78);
          --stat-value: rgba(0,0,0,0.92);
          --stat-sub: rgba(0,0,0,0.58);
          --stat-shadow: 0 8px 22px rgba(0,0,0,0.08);
        }

        .stat-wrap {display:flex; gap:16px; margin: 10px 0 6px 0; flex-wrap:wrap;}
        .stat-card{
          flex:1; min-width: 220px;
          padding:18px 18px 14px 18px;
          border-radius:14px;
          background: var(--stat-bg);
          border: 1px solid var(--stat-border);
          box-shadow: var(--stat-shadow);
          backdrop-filter: blur(6px);
        }
        .stat-title{font-size:14px;color: var(--stat-title);margin-bottom:6px;font-weight:650;}
        .stat-value{font-size:44px;font-weight:850;line-height:1.0;color: var(--stat-value);}
        .stat-sub{margin-top:10px;font-size:12px;color: var(--stat-sub);}
        </style>
        """,
        unsafe_allow_html=True,
    )

    open_count_all = int(len(tickets_df_all))
    unread_count_all = int((tickets_df_all["is_read"] == False).sum()) if "is_read" in tickets_df_all.columns else 0

    due_upcoming = int((tickets_df_all["_due_bucket"] == "Upcoming").sum())
    due_today = int((tickets_df_all["_due_bucket"] == "Due today").sum())
    due_overdue = int((tickets_df_all["_due_bucket"] == "Overdue").sum())
    due_none = int((tickets_df_all["_due_bucket"] == "No due date").sum())

    st.markdown(
        f"""
        <div class="stat-wrap">
          <div class="stat-card">
            <div class="stat-title">Open tickets</div>
            <div class="stat-value">{open_count_all}</div>
            <div class="stat-sub">Currently active</div>
          </div>
          <div class="stat-card">
            <div class="stat-title">Unread tickets</div>
            <div class="stat-value">{unread_count_all}</div>
            <div class="stat-sub">Not yet opened</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="stat-wrap">
          <div class="stat-card">
            <div class="stat-title">Upcoming due</div>
            <div class="stat-value">{due_upcoming}</div>
            <div class="stat-sub">3 days to Due Date</div>
          </div>
          <div class="stat-card">
            <div class="stat-title">Due today</div>
            <div class="stat-value">{due_today}</div>
            <div class="stat-sub">{today.strftime('%Y-%m-%d')}</div>
          </div>
          <div class="stat-card">
            <div class="stat-title">Overdue</div>
            <div class="stat-value">{due_overdue}</div>
            <div class="stat-sub">Past due date</div>
          </div>
          <div class="stat-card">
            <div class="stat-title">No due date</div>
            <div class="stat-value">{due_none}</div>
            <div class="stat-sub">Unset</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # -------------------------------------------------------------------------
    # Open Tickets + Filters
    # -------------------------------------------------------------------------
    st.subheader("🎟️ Open Tickets")

    def clear_filters():
        st.session_state["filter_property"] = "All"
        st.session_state["filter_unit"] = ""
        st.session_state["filter_due_bucket"] = "All"

    f1, f2, f3, f4 = st.columns([1, 1, 0.6, 0.9])

    with f1:
        prop_vals = sorted([p for p in tickets_df_all["property"].dropna().unique().tolist()])
        prop_options = ["All"] + prop_vals
        st.selectbox(
            "Property",
            options=prop_options,
            index=prop_options.index(st.session_state.filter_property)
            if st.session_state.filter_property in prop_options
            else 0,
            key="filter_property",
        )
        selected_prop = st.session_state.filter_property

    with f2:
        st.text_input(
            "Unit number",
            value=st.session_state.filter_unit,
            key="filter_unit",
            placeholder="e.g. A1 / 445",
        )
        unit_q = st.session_state.filter_unit

    with f3:
        st.button("Clear filters", width="stretch", on_click=clear_filters)

    with f4:
        options = ["All", "Upcoming", "Due today", "Overdue", "No due date"]
        st.selectbox(
            "Due date",
            options,
            index=options.index(st.session_state.filter_due_bucket) if st.session_state.filter_due_bucket in options else 0,
            key="filter_due_bucket",
        )
        due_filter = st.session_state.filter_due_bucket

    tickets_df = tickets_df_all.copy()

    if selected_prop and selected_prop != "All":
        tickets_df = tickets_df[tickets_df["property"] == selected_prop]

    if unit_q.strip():
        q = unit_q.strip().lower()
        tickets_df = tickets_df[tickets_df["unit_number"].astype(str).str.lower().str.contains(q, na=False)]

    if due_filter and due_filter != "All":
        tickets_df = tickets_df[tickets_df["_due_bucket"] == due_filter]

    if tickets_df.empty:
        st.warning("No tickets match your filters.")
        st.stop()

    display_df = tickets_df.drop(columns=["is_read"], errors="ignore")
    if "_due_bucket" in display_df.columns:
        display_df.insert(0, "Due", display_df["_due_bucket"].map(ICON_MAP).fillna("⚪"))
    display_df = display_df.drop(columns=["_due_date_only"], errors="ignore")

    styled_df = display_df.style.apply(style_due_rows, axis=1)

    st.dataframe(styled_df, width="stretch", hide_index=True)

    # ---- Ticket Selection ----
    ticket_ids = tickets_df["id"].tolist()

    def ticket_format_func(tid: int) -> str:
        row = tickets_df.loc[tickets_df["id"] == tid].iloc[0]
        is_read = bool(row.get("is_read", True))
        status_icon = "👁️ READ" if is_read else "🔴 NEW"
        desc_snippet = str(row.get("issue_description", "No Description"))[:40]
        return f"{status_icon} | #{tid} - {desc_snippet}..."

    if st.session_state.selected_ticket_id is None or st.session_state.selected_ticket_id not in ticket_ids:
        st.session_state.selected_ticket_id = ticket_ids[0]

    ticket_id = st.selectbox(
        "Select Ticket to View",
        options=ticket_ids,
        index=ticket_ids.index(st.session_state.selected_ticket_id),
        format_func=ticket_format_func,
        key="ticket_select_id",
    )
    st.session_state.selected_ticket_id = ticket_id
    selected_ticket = tickets_df[tickets_df["id"] == ticket_id].iloc[0]

    st.session_state.new_ticket_flag = False
    st.session_state.new_ticket_msg = ""

    # Mark as read (no rerun)
    if "is_read" in tickets_df.columns and not bool(selected_ticket.get("is_read", True)):
        db.mark_ticket_as_read(ticket_id)
        try:
            tickets_df.loc[tickets_df["id"] == ticket_id, "is_read"] = True
            full_df = st.session_state.tickets_cache
            if isinstance(full_df, pd.DataFrame) and "is_read" in full_df.columns:
                full_df.loc[full_df["id"] == ticket_id, "is_read"] = True
                st.session_state.tickets_cache = full_df
        except Exception:
            st.session_state.tickets_cache = None

        st.session_state.last_hash = db.get_tickets_hash()
        selected_ticket = tickets_df[tickets_df["id"] == ticket_id].iloc[0]

    st.divider()
    st.markdown(f"### 🎫 Ticket #{ticket_id}")

    c1, c2 = st.columns([1.3, 1])
    with c1:
        st.write(f"**Issue:** {selected_ticket['issue_description']}")
        st.write(f"**Category:** {selected_ticket['category']}")
        st.write(f"**Property:** {selected_ticket['property']}")
    with c2:
        st.write(f"**Unit Number:** {selected_ticket['unit_number']}")
        st.write(f"**Status:** {selected_ticket['status']}")
        st.write(f"**Assigned Admin:** {selected_ticket['assigned_admin']}")

    tab_actions, tab_attachments, tab_activity = st.tabs(["⚙️ Actions", "📎 Attachments", "📜 Activity"])

    # -------------------------------------------------------------------------
    # ACTIONS
    # -------------------------------------------------------------------------
    with tab_actions:
        st.markdown("### ✅ Update Status")
        new_status = st.selectbox(
            "Status",
            ["Open", "In Progress", "Resolved"],
            index=["Open", "In Progress", "Resolved"].index(selected_ticket["status"]),
            key=f"status_select_{ticket_id}",
        )
        if st.button("Update Status", key=f"btn_update_status_{ticket_id}", width="stretch"):
            db.update_ticket_status(ticket_id, new_status)
            st.session_state.tickets_cache = None
            st.session_state.last_hash = db.get_tickets_hash()
            st.success(f"✅ Ticket #{ticket_id} updated to {new_status}!")
            st.rerun()

        st.divider()

        st.markdown("### ✍️ Add Ticket Update")
        update_text = st.text_area("Update text", key=f"update_text_{ticket_id}")
        if st.button("Submit Update", key=f"btn_submit_update_{ticket_id}", width="stretch"):
            if not update_text.strip():
                st.error("⚠️ Please provide update text.")
            else:
                db.add_ticket_update(ticket_id, update_text.strip(), st.session_state.admin_name)
                st.session_state.tickets_cache = None
                st.session_state.last_hash = db.get_tickets_hash()
                st.success("✅ Update added successfully!")
                st.rerun()

        st.divider()

        if st.session_state.admin_role != "Caretaker":
            st.markdown("### 🔄 Reassign Admin")

            admin_users = db.fetch_admin_users()
            admin_options = {admin["id"]: admin["name"] for admin in admin_users}

            current_assigned_name = selected_ticket["assigned_admin"]
            current_assigned_id = next(
                (aid for aid, aname in admin_options.items() if aname == current_assigned_name),
                None,
            )
            available_admins = {k: v for k, v in admin_options.items() if v != current_assigned_name}

            if not available_admins:
                st.info("No other admins available.")
            else:
                new_admin_id = st.selectbox(
                    "Select New Admin",
                    list(available_admins.keys()),
                    format_func=lambda x: available_admins[x],
                    key=f"reassign_sel_{ticket_id}",
                )
                reassign_reason = st.text_area("Reason for Reassignment", key=f"reassign_reason_{ticket_id}")

                if st.button("Reassign Ticket", key=f"btn_reassign_{ticket_id}", width="stretch"):
                    if not reassign_reason.strip():
                        st.error("⚠️ Please provide a reason.")
                    elif current_assigned_id is None:
                        st.error("⚠️ Could not resolve current admin ID.")
                    else:
                        ok, msg = db.reassign_ticket_admin(
                            ticket_id,
                            new_admin_id,
                            current_assigned_id,
                            st.session_state.admin_name,
                            reassign_reason.strip(),
                            (st.session_state.admin_role == "Super Admin"),
                        )
                        if ok:
                            st.session_state.tickets_cache = None
                            st.session_state.last_hash = db.get_tickets_hash()
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)

        st.divider()

        st.markdown("### 📅 Set Due Date")

        current_due = selected_ticket.get("Due_Date")
        parsed_due = pd.to_datetime(current_due, errors="coerce")
        default_due = pd.Timestamp.today().date() if pd.isna(parsed_due) else parsed_due.date()

        due_date = st.date_input("Select Due Date", value=default_due, key=f"due_date_in_{ticket_id}")

        if st.button("Update Due Date", key=f"btn_due_date_{ticket_id}", width="stretch"):
            db.update_ticket_due_date(ticket_id, due_date)
            st.session_state.tickets_cache = None
            st.session_state.last_hash = db.get_tickets_hash()
            st.success(f"✅ Due date updated to {due_date.strftime('%Y-%m-%d')}")
            st.rerun()

        # ---------------------------------------------------------------------
        # JOB CARD (INLINE inside Actions tab)
        # ---------------------------------------------------------------------
        st.divider()
        st.markdown("### 🧾 Job Card")

        jc = db.get_job_card_by_ticket(ticket_id)

        JOB_STATUS_LIST = ["Open", "In Progress", "Completed", "Signed Off", "Cancelled"]

        if not jc:
            st.info("No job card linked to this ticket yet.")

            title = st.text_input("Job card title (optional)", key=f"jc_title_{ticket_id}")
            est_cost = st.number_input("Estimated cost (optional)", min_value=0.0, step=100.0, key=f"jc_est_{ticket_id}")
            copy_media = st.checkbox("Copy ticket attachments", value=True, key=f"jc_copy_{ticket_id}")

            if st.button("Create Job Card from this Ticket", key=f"create_jc_{ticket_id}", width="stretch"):
                jc_id = db.create_job_card_from_ticket(
                    ticket_id=ticket_id,
                    created_by_admin_id=st.session_state.get("admin_id"),
                    assigned_admin_id=None,
                    title=title.strip() if title.strip() else None,
                    estimated_cost=float(est_cost) if est_cost > 0 else None,
                    copy_media=copy_media,
                )
                st.success(f"✅ Created Job Card #{jc_id}")
                st.session_state["open_job_card_id"] = int(jc_id)
                st.rerun()

        else:
            jc_id = int(jc["id"])
            st.success(f"✅ Job Card linked: #{jc_id}")

            # lock UI if signed off
            is_signed_off = (str(jc.get("status") or "").strip().lower() == "signed off")

            colA, colB = st.columns([1.2, 0.8])

            with colA:
                jc_title = st.text_input(
                    "Title",
                    value=jc.get("title") or "",
                    key=f"edit_jc_title_{jc_id}",
                    disabled=is_signed_off,
                )
                jc_desc = st.text_area(
                    "Description",
                    value=jc.get("description") or "",
                    height=100,
                    key=f"edit_jc_desc_{jc_id}",
                    disabled=is_signed_off,
                )
                jc_acts = st.text_area(
                    "Activities / Work Log",
                    value=jc.get("activities") or "",
                    height=160,
                    key=f"edit_jc_acts_{jc_id}",
                    disabled=is_signed_off,
                )

            with colB:
                current_status = (jc.get("status") or "Open").strip()
                if current_status not in JOB_STATUS_LIST:
                    current_status = "Open"

                jc_status = st.selectbox(
                    "Job Card Status",
                    JOB_STATUS_LIST,
                    index=JOB_STATUS_LIST.index(current_status),
                    key=f"edit_jc_status_{jc_id}",
                    disabled=is_signed_off,
                )

                est_cost_val = st.number_input(
                    "Estimated cost",
                    min_value=0.0,
                    step=100.0,
                    value=float(jc.get("estimated_cost") or 0.0),
                    key=f"edit_jc_est_{jc_id}",
                    disabled=is_signed_off,
                )
                act_cost_val = st.number_input(
                    "Actual cost",
                    min_value=0.0,
                    step=100.0,
                    value=float(jc.get("actual_cost") or 0.0),
                    key=f"edit_jc_act_{jc_id}",
                    disabled=is_signed_off,
                )

                admin_users = db.fetch_admin_users()
                admin_map = {0: "— Unassigned —"}
                admin_map.update({int(a["id"]): a["name"] for a in admin_users})

                current_assigned = int(jc.get("assigned_admin_id") or 0)
                if current_assigned not in admin_map:
                    current_assigned = 0

                assigned_admin_id = st.selectbox(
                    "Assigned to",
                    options=list(admin_map.keys()),
                    index=list(admin_map.keys()).index(current_assigned),
                    format_func=lambda x: admin_map[x],
                    key=f"edit_jc_assign_{jc_id}",
                    disabled=is_signed_off,
                )

            csave, copen = st.columns([1, 1])

            with csave:
                if st.button(
                    "💾 Save Job Card Changes",
                    width="stretch",
                    key=f"save_jc_{jc_id}",
                    disabled=is_signed_off,
                ):
                    db.update_job_card(
                        job_card_id=jc_id,
                        title=jc_title.strip() or None,
                        description=jc_desc.strip() or None,
                        activities=jc_acts.strip() or None,
                        status=jc_status,
                        estimated_cost=float(est_cost_val) if est_cost_val > 0 else None,
                        actual_cost=float(act_cost_val) if act_cost_val > 0 else None,
                        assigned_admin_id=None if assigned_admin_id == 0 else int(assigned_admin_id),
                    )
                    st.success("✅ Job card updated.")
                    st.session_state.tickets_cache = None
                    st.rerun()

            with copen:
                if st.button("📂 Open in Job Cards Page", width="stretch", key=f"open_jc_{jc_id}"):
                    st.session_state["job_card_view_id"] = jc_id
                    st.session_state["open_job_card_id"] = jc_id
                    st.info("Go to Job Cards → Manage tab to view it.")

            # ---------- PDF DOWNLOAD ----------
            st.divider()
            st.markdown("### 📄 Download Job Card PDF")

            signoff = None
            try:
                signoff = db.get_job_card_signoff(jc_id)
            except Exception:
                signoff = None

            # attachments list for pdf (names only)
            ticket_media_df = None
            try:
                ticket_media_df = db.fetch_job_card_media(jc_id)
            except Exception:
                ticket_media_df = None

            attachments = []
            if ticket_media_df is not None and not ticket_media_df.empty:
                for _, r in ticket_media_df.iterrows():
                    attachments.append(
                        {
                            "filename": r.get("filename", "attachment"),
                            "media_type": r.get("media_type", "file"),
                        }
                    )

            pdf_bytes = build_job_card_pdf(
                job_card=jc,
                signoff=signoff,
                attachments=attachments,
                brand_title="Apricot Property Solutions",
                logo_path="logo1.png",
            )

            st.download_button(
                "⬇️ Download PDF",
                data=pdf_bytes,
                file_name=f"job_card_{jc_id}.pdf",
                mime="application/pdf",
                width="stretch",
                key=f"dl_jobcard_pdf_{jc_id}",
            )

            # ---------- SIGN-OFF ----------
            st.divider()
            st.markdown("### ✍️ Sign-Off")

            existing_signoff = None
            try:
                existing_signoff = db.get_job_card_signoff(jc_id)
            except Exception:
                existing_signoff = None

            if existing_signoff:
                st.success(
                    f"Signed by {existing_signoff.get('signed_by_name')} ({existing_signoff.get('signed_by_role')}) "
                    f"at {existing_signoff.get('signed_at')}"
                )
                if existing_signoff.get("signoff_notes"):
                    st.caption(existing_signoff["signoff_notes"])
                st.info("This job card is locked because it is Signed Off.")
            else:
                s1, s2 = st.columns([1, 1])
                with s1:
                    signed_by_name = st.text_input(
                        "Signed by",
                        value=st.session_state.get("admin_name", ""),
                        key=f"jc_sig_name_{jc_id}",
                    )
                with s2:
                    signed_by_role = st.text_input(
                        "Role",
                        value=st.session_state.get("admin_role", ""),
                        key=f"jc_sig_role_{jc_id}",
                    )
                notes = st.text_area("Sign-off notes (optional)", key=f"jc_sig_notes_{jc_id}")

                if st.button("✅ Sign Off Job Card", key=f"jc_signoff_btn_{jc_id}", width="stretch"):
                    if not signed_by_name.strip():
                        st.error("Please enter who is signing off.")
                    else:
                        db.signoff_job_card(
                            job_card_id=jc_id,
                            signed_by_name=signed_by_name.strip(),
                            signed_by_role=signed_by_role.strip() or "—",
                            signoff_notes=notes.strip() or None,
                        )
                        # set status to Signed Off
                        db.update_job_card(
                            job_card_id=jc_id,
                            title=jc_title.strip() or None,
                            description=jc_desc.strip() or None,
                            activities=jc_acts.strip() or None,
                            status="Signed Off",
                            estimated_cost=float(est_cost_val) if est_cost_val > 0 else None,
                            actual_cost=float(act_cost_val) if act_cost_val > 0 else None,
                            assigned_admin_id=None if assigned_admin_id == 0 else int(assigned_admin_id),
                        )
                        st.success("✅ Signed off.")
                        st.rerun()

    # -------------------------------------------------------------------------
    # ATTACHMENTS TAB
    # -------------------------------------------------------------------------
    with tab_attachments:
        media_df = db.fetch_ticket_media(ticket_id)
        if media_df is None or media_df.empty:
            st.info("No media files attached to this ticket.")
        else:
            st.caption(f"{len(media_df)} attachment(s)")
            cols = st.columns(3)
            for idx, row in media_df.reset_index(drop=True).iterrows():
                with cols[idx % 3]:
                    m_type = row["media_type"]
                    m_blob = row["media_blob"]
                    f_name = row.get("filename", "attachment")

                    st.markdown(
                        f"""
                        <div style="
                            border:1px solid rgba(255,255,255,0.12);
                            border-radius:14px;
                            padding:12px;
                            background:rgba(255,255,255,0.03);
                            margin-bottom:10px;
                        ">
                            <div style="font-weight:700;">{f_name}</div>
                            <div style="opacity:0.85; font-size:12px;">Type: {m_type}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    if m_type == "image":
                        st.image(BytesIO(m_blob), width="stretch")
                    elif m_type == "video":
                        st.video(BytesIO(m_blob))
                    else:
                        st.download_button(
                            label="📥 Download",
                            data=m_blob,
                            file_name=f_name,
                            key=f"dl_{ticket_id}_{idx}",
                            width="stretch",
                        )

    # -------------------------------------------------------------------------
    # ACTIVITY TAB
    # -------------------------------------------------------------------------
    with tab_activity:
        history_df = db.fetch_ticket_history(ticket_id)
        if history_df is None or history_df.empty:
            st.info("No ticket activity available.")
        else:
            history_df = history_df.sort_values("performed_at", ascending=False)
            for _, row in history_df.iterrows():
                action = str(row.get("action", "Update"))
                who = str(row.get("performed_by", "System"))
                details = str(row.get("details", ""))
                dt = row.get("performed_at")

                header = f"**{action}** • {who}"
                ts = dt.strftime("%Y-%m-%d %H:%M") if hasattr(dt, "strftime") else str(dt)

                with st.chat_message("assistant"):
                    st.markdown(header)
                    st.caption(ts)
                    st.write(details)


# -----------------------------------------------------------------------------
# Create Ticket
# -----------------------------------------------------------------------------
elif selected == "Create Ticket":
    create_ticket(st.session_state.admin_id)

# -----------------------------------------------------------------------------
# Send Bulk Message
# -----------------------------------------------------------------------------
elif selected == "Send Bulk Message":
    st.title("📨 Send 'Notice' Template Message to Property Users")

    property_list = db.get_all_properties()
    if not property_list:
        st.warning("No properties found.")
        st.stop()

    property_options = {f"{p['name']} (ID {p['id']})": p["id"] for p in property_list}
    selected_property_label = st.selectbox("Select Property", list(property_options.keys()))
    selected_property_id = property_options[selected_property_label]
    property_name = selected_property_label.split(" (ID")[0]

    notice_text = st.text_area("Notice Text", placeholder="Write your notice content here")

    if st.button("Send Notice Template", width="stretch"):
        if not notice_text.strip():
            st.error("⚠️ Please enter the notice text.")
            st.stop()

        users = db.get_users_by_property(selected_property_id)
        if not users:
            st.warning("⚠️ No users found for this property.")
            st.stop()

        sent_results = []
        audit_entries = []
        progress = st.progress(0)
        total_users = len(users)

        for idx, user in enumerate(users):
            params = [notice_text.strip(), property_name]
            response = db.send_template_notification(
                to=user["whatsapp_number"],
                template_name="notice",
                template_parameters=params,
            )

            status_text = "✅ Success" if "error" not in response else f"❌ Failed - {response['error']}"

            sent_results.append(
                {
                    "name": user.get("name", "N/A"),
                    "status": status_text,
                    "whatsapp_number": user["whatsapp_number"],
                }
            )

            audit_entries.append(
                {
                    "property_id": selected_property_id,
                    "property_name": property_name,
                    "user_name": user.get("name", "N/A"),
                    "whatsapp_number": user["whatsapp_number"],
                    "status": status_text,
                    "template_name": "notice",
                    "notice_text": notice_text.strip(),
                }
            )

            progress.progress((idx + 1) / total_users)

        db.save_bulk_audit(audit_entries)

        st.subheader("📋 Send Status Report")
        report_df = pd.DataFrame(sent_results)

        cols = report_df.columns.tolist()
        if "status" in cols and "whatsapp_number" in cols:
            i_status = cols.index("status")
            i_wa = cols.index("whatsapp_number")
            cols[i_status], cols[i_wa] = cols[i_wa], cols[i_status]
            report_df = report_df[cols]

        st.dataframe(report_df, width="stretch", hide_index=True)

        csv_data = report_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="⬇ Download Report as CSV",
            data=csv_data,
            file_name=f"notice_send_report_{property_name.replace(' ', '_')}.csv",
            mime="text/csv",
            width="stretch",
        )

# -----------------------------------------------------------------------------
# Admin Reassignment History
# -----------------------------------------------------------------------------
elif selected == "Admin Reassignment History":
    st.title("📜 Admin Reassignment History")
    reassign_log_df = db.fetch_admin_reassignment_log()
    if reassign_log_df is not None and not reassign_log_df.empty:
        st.dataframe(reassign_log_df, width="stretch", hide_index=True)
    else:
        st.warning("⚠️ No reassignments have been logged yet.")

# -----------------------------------------------------------------------------
# Create Property
# -----------------------------------------------------------------------------
elif selected == "Create Property":
    st.title("🏘️ Create New Property")

    supervisors = db.get_available_property_managers()
    if not supervisors:
        st.warning("No Property Supervisors found. Create one first.")
        st.stop()

    supervisor_options = {f"{s['name']} (ID: {s['id']})": s["id"] for s in supervisors}

    with st.form("create_property_form"):
        name = st.text_input("Property Name", placeholder="e.g., Westview Apartments")
        selected_supervisor = st.selectbox("Assign Property Supervisor", options=list(supervisor_options.keys()))
        submit = st.form_submit_button("Create Property")

    if submit:
        if not name.strip():
            st.error("Please enter a property name.")
        else:
            success, msg = db.create_property(name.strip(), supervisor_options[selected_supervisor])
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

# -----------------------------------------------------------------------------
# Edit/Delete User
# -----------------------------------------------------------------------------
elif selected == "Edit/Delete User":
    edit_user()

# -----------------------------------------------------------------------------
# Edit/Delete Property
# -----------------------------------------------------------------------------
elif selected == "Edit/Delete Property":
    edit_properties()

# -----------------------------------------------------------------------------
# Edit/Delete Admin
# -----------------------------------------------------------------------------
elif selected == "Edit/Delete Admin":
    edit_admins()

# -----------------------------------------------------------------------------
# Admin User Creation
# -----------------------------------------------------------------------------
elif selected == "Admin User Creation":
    admin_signup()

# -----------------------------------------------------------------------------
# KPI Dashboard
# -----------------------------------------------------------------------------
elif selected == "KPI Dashboard":
    if st.session_state.get("admin_role") != "Super Admin":
        st.error("⛔ You do not have permission to access this page.")
        st.stop()

    KPIDashboard(db).render()

# -----------------------------------------------------------------------------
# Job Cards page
# -----------------------------------------------------------------------------
elif selected == "Job Cards":
    job_cards_page(db)
