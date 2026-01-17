# kpi_dashboard.py
import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime, timedelta, date


class KPIDashboard:
    """
    Usage:
        from kpi_dashboard import KPIDashboard
        KPIDashboard(db).render()
    """

    def __init__(self, db):
        self.db = db

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    @staticmethod
    def _fmt_duration(seconds):
        if seconds is None or pd.isna(seconds):
            return "—"
        seconds = int(seconds)
        h = seconds // 3600
        m = (seconds % 3600) // 60
        if h <= 0:
            return f"{m}m"
        return f"{h}h {m}m"

    @staticmethod
    def _inject_css():
        st.markdown(
            """
            <style>
            .kpi-row {display:flex; gap:16px; flex-wrap:wrap; margin: 8px 0 18px 0;}
            .kpi-card{
              flex:1; min-width: 260px;
              padding:18px;
              border-radius:16px;
              background: rgba(255,255,255,0.65);
              border: 1px solid rgba(0,0,0,0.10);
              backdrop-filter: blur(6px);
            }
            @media (prefers-color-scheme: dark){
              .kpi-card{
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.12);
              }
            }
            .kpi-title{font-weight:700; font-size:18px; opacity:0.9; margin-bottom:10px;}
            .kpi-big{font-weight:900; font-size:54px; line-height:1;}
            .kpi-mid{font-weight:900; font-size:44px; line-height:1;}
            .kpi-sub{opacity:0.75; margin-top:6px;}

            .bar-wrap{
              margin-top:12px;
              border-radius:12px;
              overflow:hidden;
              background: rgba(0,0,0,0.08);
            }
            .bar-fill{
              height:18px;
              background: #56b39c;
            }

            .section-gap{margin-top: 12px;}
            </style>
            """,
            unsafe_allow_html=True,
        )

    # -------------------------------------------------------------------------
    # Date Range UI
    # -------------------------------------------------------------------------
    @staticmethod
    def _date_range_ui():
        c1, c2, c3 = st.columns([1.2, 1.2, 1])

        with c3:
            preset = st.selectbox("Range", ["This Month", "This Week", "Today", "Custom"], index=0)

        today = date.today()

        if preset == "This Month":
            start_d = today.replace(day=1)
            end_d = today + timedelta(days=1)
        elif preset == "This Week":
            start_d = today - timedelta(days=today.weekday())
            end_d = today + timedelta(days=1)
        elif preset == "Today":
            start_d = today
            end_d = today + timedelta(days=1)
        else:
            start_d = None
            end_d = None

        with c1:
            start_date = st.date_input("Start", value=start_d or today.replace(day=1))
        with c2:
            end_date = st.date_input("End (inclusive)", value=(end_d - timedelta(days=1)) if end_d else today)

        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date + timedelta(days=1), datetime.min.time())
        return start_dt, end_dt

    # -------------------------------------------------------------------------
    # KPI Cards
    # -------------------------------------------------------------------------
    def _render_top_cards(self, start_dt, end_dt):
        kpi = self.db.kpi_summary(start_dt, end_dt)

        open_count = int(kpi.get("open_count") or 0)
        closed_count = int(kpi.get("closed_count") or 0)
        pct_closed = float(kpi.get("pct_closed") or 0)

        avg_resp = self._fmt_duration(kpi.get("avg_first_response_seconds"))
        avg_res = self._fmt_duration(kpi.get("avg_resolution_seconds"))

        unread_count = int(kpi.get("unread_count") or 0)
        overdue_count = int(kpi.get("overdue_count") or 0)
        upcoming_due_count = int(kpi.get("upcoming_due_count") or 0)

        st.markdown(
            f"""
            <div class="kpi-row">
              <div class="kpi-card">
                <div class="kpi-title">Open vs Closed Tickets</div>
                <div style="display:flex; justify-content:space-between; align-items:flex-end;">
                  <div>
                    <div class="kpi-big">{open_count}</div>
                    <div class="kpi-sub">Open</div>
                  </div>
                  <div style="text-align:right;">
                    <div class="kpi-big">{closed_count}</div>
                    <div class="kpi-sub">Closed</div>
                  </div>
                </div>
                <div class="bar-wrap">
                  <div class="bar-fill" style="width:{pct_closed}%;"></div>
                </div>
                <div class="kpi-sub" style="margin-top:8px;">{int(pct_closed)}% Closed</div>
              </div>

              <div class="kpi-card">
                <div class="kpi-title">Avg Response Time</div>
                <div class="kpi-big" style="color:#1f7a7a;">{avg_resp}</div>
                <div class="kpi-sub">First admin update</div>
              </div>

              <div class="kpi-card">
                <div class="kpi-title">Avg Resolution Time</div>
                <div class="kpi-big" style="color:#c77a2a;">{avg_res}</div>
                <div class="kpi-sub">Created → Resolved</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            f"""
            <div class="kpi-row">
              <div class="kpi-card">
                <div class="kpi-title">Unread / New Tickets</div>
                <div class="kpi-mid">{unread_count}</div>
                <div class="kpi-sub">Not opened yet</div>
              </div>

              <div class="kpi-card">
                <div class="kpi-title">Overdue Tickets</div>
                <div class="kpi-mid" style="color:#b71c1c;">{overdue_count}</div>
                <div class="kpi-sub">Past due date</div>
              </div>

              <div class="kpi-card">
                <div class="kpi-title">Upcoming Due</div>
                <div class="kpi-mid" style="color:#1b5e20;">{upcoming_due_count}</div>
                <div class="kpi-sub">Due in next 3 days</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # -------------------------------------------------------------------------
    # Second Row: Tickets per day + Performance
    # -------------------------------------------------------------------------
    def _render_second_row(self, start_dt, end_dt):
        left, right = st.columns([1.6, 1])

        with left:
            st.subheader("🗓️ Tickets Per Day")

            df_day = self.db.tickets_per_day(start_dt, end_dt)
            if df_day is None or df_day.empty:
                st.info("No tickets in this period.")
            else:
                df_day["day"] = pd.to_datetime(df_day["day"])

                chart_data = df_day.melt(
                    id_vars=["day"],
                    value_vars=["open_count", "closed_count"],
                    var_name="type",
                    value_name="tickets",
                )
                chart_data["type"] = chart_data["type"].map(
                    {"open_count": "Open", "closed_count": "Closed"}
                )

                chart = (
                    alt.Chart(chart_data)
                    .mark_bar()
                    .encode(
                        x=alt.X("day:T", title=None, axis=alt.Axis(labelAngle=0)),
                        y=alt.Y("tickets:Q", title="Tickets"),
                        color="type:N",
                        xOffset="type:N",
                        tooltip=["day:T", "type:N", "tickets:Q"],
                    )
                    .properties(height=260)
                )

                st.altair_chart(chart, use_container_width=True)

        with right:
            st.subheader("✅ Performance")

            perf = self.db.caretaker_performance(start_dt, end_dt)
            if perf is None or perf.empty:
                st.info("No performance data in this period.")
            else:
                # Nice labels
                if "caretaker" in perf.columns:
                    perf = perf.rename(columns={"caretaker": "Agent"})
                if "tickets" in perf.columns:
                    perf = perf.rename(columns={"tickets": "Tickets Handled"})

                max_t = int(perf["Tickets Handled"].max()) if "Tickets Handled" in perf.columns else 0

                st.dataframe(
                    perf,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Tickets Handled": st.column_config.ProgressColumn(
                            "Tickets",
                            min_value=0,
                            max_value=max_t if max_t > 0 else 1,
                            format="%d",
                        )
                    },
                )

    # -------------------------------------------------------------------------
    # NEW: Category pie + property report
    # -------------------------------------------------------------------------
    def _render_category_and_property_reports(self, start_dt, end_dt):
        st.markdown('<div class="section-gap"></div>', unsafe_allow_html=True)

        left, right = st.columns([1.2, 1.4])

        # ----------------------------
        # Categories (Donut Chart)
        # ----------------------------
        with left:
            st.subheader("🧩 Tickets by Category")

            df_cat = self.db.tickets_by_category(start_dt, end_dt)
            if df_cat is None or df_cat.empty:
                st.info("No category data in this period.")
            else:
                # Ensure columns
                # expected: category, tickets
                if "category" not in df_cat.columns:
                    # try common fallbacks
                    for c in df_cat.columns:
                        if str(c).lower() in ("cat", "ticket_category"):
                            df_cat = df_cat.rename(columns={c: "category"})
                            break
                if "tickets" not in df_cat.columns:
                    # fallback: first numeric col
                    num_cols = [c for c in df_cat.columns if pd.api.types.is_numeric_dtype(df_cat[c])]
                    if num_cols:
                        df_cat = df_cat.rename(columns={num_cols[0]: "tickets"})

                df_cat["tickets"] = pd.to_numeric(df_cat["tickets"], errors="coerce").fillna(0).astype(int)
                df_cat["category"] = df_cat["category"].fillna("Unspecified").astype(str)

                # Donut chart
                donut = (
                    alt.Chart(df_cat)
                    .mark_arc(innerRadius=70)
                    .encode(
                        theta=alt.Theta("tickets:Q"),
                        color=alt.Color("category:N", legend=alt.Legend(title="Category")),
                        tooltip=["category:N", "tickets:Q"],
                    )
                    .properties(height=320)
                )

                st.altair_chart(donut, use_container_width=True)

                # Small table under (optional)
                st.dataframe(
                    df_cat.sort_values("tickets", ascending=False),
                    use_container_width=True,
                    hide_index=True,
                )

        # ----------------------------
        # Tickets by Property (Table + optional Bar)
        # ----------------------------
        with right:
            st.subheader("🏘️ Tickets by Property")

            df_prop = self.db.tickets_by_property(start_dt, end_dt)
            if df_prop is None or df_prop.empty:
                st.info("No property data in this period.")
            else:
                # expected: property, tickets
                if "property" not in df_prop.columns:
                    for c in df_prop.columns:
                        if str(c).lower() in ("property_name", "building", "site"):
                            df_prop = df_prop.rename(columns={c: "property"})
                            break
                if "tickets" not in df_prop.columns:
                    num_cols = [c for c in df_prop.columns if pd.api.types.is_numeric_dtype(df_prop[c])]
                    if num_cols:
                        df_prop = df_prop.rename(columns={num_cols[0]: "tickets"})

                df_prop["tickets"] = pd.to_numeric(df_prop["tickets"], errors="coerce").fillna(0).astype(int)
                df_prop["property"] = df_prop["property"].fillna("Unspecified").astype(str)

                df_prop = df_prop.sort_values("tickets", ascending=False)

                # Quick bar chart (top 15)
                top_n = 15
                df_top = df_prop.head(top_n)

                bar = (
                    alt.Chart(df_top)
                    .mark_bar()
                    .encode(
                        y=alt.Y("property:N", sort="-x", title=None),
                        x=alt.X("tickets:Q", title="Tickets"),
                        tooltip=["property:N", "tickets:Q"],
                    )
                    .properties(height=340)
                )
                st.altair_chart(bar, use_container_width=True)

                # Full table
                st.dataframe(df_prop, use_container_width=True, hide_index=True)

    # -------------------------------------------------------------------------
    # Public entry
    # -------------------------------------------------------------------------
    def render(self):
        st.title("📊 Operations CRM Dashboard")
        start_dt, end_dt = self._date_range_ui()
        self._inject_css()

        self._render_top_cards(start_dt, end_dt)
        self._render_second_row(start_dt, end_dt)

        # ✅ new section
        self._render_category_and_property_reports(start_dt, end_dt)
