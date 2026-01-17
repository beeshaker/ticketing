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
            .kpi-sub{opacity:0.75; margin-top:6px;}
            .bar-wrap{margin-top:12px; border-radius:12px; overflow:hidden; background: rgba(0,0,0,0.08);}
            .bar-fill{height:18px; background: #56b39c;}
            </style>
            """,
            unsafe_allow_html=True,
        )

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

    def _render_top_cards(self, start_dt, end_dt):
        kpi = self.db.kpi_summary(start_dt, end_dt)
        open_count = int(kpi.get("open_count") or 0)
        closed_count = int(kpi.get("closed_count") or 0)
        pct_closed = float(kpi.get("pct_closed") or 0)

        avg_resp = self._fmt_duration(kpi.get("avg_first_response_seconds"))
        avg_res = self._fmt_duration(kpi.get("avg_resolution_seconds"))

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
            st.subheader("✅ Caretaker Performance")

            perf = self.db.caretaker_performance(start_dt, end_dt)
            if perf is None or perf.empty:
                st.info("No caretaker data in this period.")
            else:
                max_t = int(perf["tickets"].max()) if "tickets" in perf.columns else 0
                st.dataframe(
                    perf,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "tickets": st.column_config.ProgressColumn(
                            "Tickets",
                            min_value=0,
                            max_value=max_t if max_t > 0 else 1,
                            format="%d",
                        )
                    },
                )

    def render(self):
        st.title("📊 Operations CRM Dashboard")
        start_dt, end_dt = self._date_range_ui()
        self._inject_css()
        self._render_top_cards(start_dt, end_dt)
        self._render_second_row(start_dt, end_dt)
