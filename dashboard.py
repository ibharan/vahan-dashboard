
"""
VAHAN 2-Wheeler Sales Dashboard — Amazon Automotive GL
Run: python -m streamlit run dashboard.py
"""
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from pathlib import Path
from datetime import datetime
import yaml

st.set_page_config(page_title="2-Wheeler Sales | Amazon Automotive GL",
                   page_icon="🏍️", layout="wide", initial_sidebar_state="expanded")

with open("config.yaml") as f:
    CFG = yaml.safe_load(f)

PROCESSED_FILE = CFG["data"]["processed_file"]
AMAZON_FILE    = CFG["data"].get("amazon_file", "data/amazon_online_sales.csv")
BRAND_FILE     = "data/amazon_brand_sales.csv"
VAHAN_BRAND    = "data/vahan_brand_raw.csv"

ORANGE = "#FF9900"
BLUE   = "#146EB4"
DARK   = "#232F3E"
GREEN  = "#00A36C"
GRAY   = "#8B8B8B"

# ── Number formatters ─────────────────────────────────────────────────────────
def fmt(n):
    if pd.isna(n): return "N/A"
    n = int(n)
    if n >= 10000000: return f"{n/10000000:.2f} Cr"
    if n >= 100000:   return f"{n/100000:.2f} L"
    return f"{n:,}"

def fmt_gms(n):
    if pd.isna(n): return "N/A"
    n = float(n)
    if n >= 10000000: return f"₹{n/10000000:.1f}Cr"
    if n >= 100000:   return f"₹{n/100000:.1f}L"
    return f"₹{n:,.0f}"

def fmt_cr(n):
    """Always show in Crores for GMS axis."""
    if pd.isna(n): return "N/A"
    return f"₹{float(n)/10000000:.2f}Cr"

def mom_pct(series):
    return series.pct_change().mul(100).round(1)

def sort_months(df, col="month_name"):
    df = df.copy()
    df["_s"] = pd.to_datetime(df[col], format="%b %Y", errors="coerce")
    return df.sort_values("_s").drop(columns=["_s"]).reset_index(drop=True)

# ── Data loaders ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_offline():
    p = Path(PROCESSED_FILE)
    if not p.exists():
        from processor import generate_sample_data
        return generate_sample_data()
    return pd.read_csv(p, parse_dates=["date"])

@st.cache_data(ttl=3600)
def load_amazon():
    from amazon_data import get_amazon_data
    return get_amazon_data()

@st.cache_data(ttl=3600)
def load_amazon_brands():
    """Amazon brand-level sales from InsightCrafter (merchant_brand_name, gl=263, cat=26320000)."""
    p = Path(BRAND_FILE)
    if p.exists():
        df = pd.read_csv(p, parse_dates=["date"])
        # Ensure fuel_type column exists with correct classification
        ev_brands = ["ola","ather","chetak","vida","revolt","okinawa","ampere",
                     "pure ev","bounce","bgauss","greaves","lectrix","amo","benling",
                     "jitendra","wardwizard","evtric","tork","oben electric","oben",
                     "simple energy","tvs iqube","iqube","eox","electric","ev",
                     "e-bike","hero electric","kinetic green","battre","euler"]
        df["fuel_type"] = df["brand_name"].apply(
            lambda b: "EV" if any(e in str(b).lower() for e in ev_brands) else "ICE"
        )
        return df
    # Synthetic brand split based on real market share data
    from amazon_data import get_amazon_data
    base = get_amazon_data()
    brands_ev  = ["Ola Electric","Ather Energy","TVS iQube","Bajaj Chetak","Hero Vida",
                  "Revolt","Okinawa","Ampere","Pure EV","Bounce Infinity"]
    brands_ice = ["Hero MotoCorp","Honda","TVS Motor","Bajaj Auto","Royal Enfield",
                  "Suzuki","Yamaha","KTM","Jawa","Triumph"]
    share_ev  = [0.28,0.18,0.15,0.12,0.08,0.06,0.05,0.04,0.02,0.02]
    share_ice = [0.30,0.22,0.16,0.12,0.07,0.04,0.04,0.02,0.02,0.01]
    rows = []
    for _, r in base.iterrows():
        total = r["amazon_online_units"]
        ev_units  = int(total * 0.35)
        ice_units = total - ev_units
        for b, s in zip(brands_ev,  share_ev):
            rows.append({"date": r["date"], "month_name": r["month_name"],
                         "year": r["year"], "month": r["month"],
                         "brand": b, "fuel_type": "EV",
                         "units": int(ev_units * s),
                         "gms":   int(r["amazon_online_gms"] * 0.35 * s)})
        for b, s in zip(brands_ice, share_ice):
            rows.append({"date": r["date"], "month_name": r["month_name"],
                         "year": r["year"], "month": r["month"],
                         "brand": b, "fuel_type": "ICE",
                         "units": int(ice_units * s),
                         "gms":   int(r["amazon_online_gms"] * 0.65 * s)})
    df = pd.DataFrame(rows)
    Path("data").mkdir(exist_ok=True)
    df.to_csv(BRAND_FILE, index=False)
    return df

@st.cache_data(ttl=3600)
def load_vahan_brands():
    """VAHAN maker-wise data. Falls back to synthetic split."""
    p = Path(VAHAN_BRAND)
    if p.exists():
        return pd.read_csv(p, parse_dates=["date"])
    # Synthetic VAHAN brand split
    offline = load_offline()
    brands_ev  = ["Ola Electric","Ather Energy","TVS iQube","Bajaj Chetak","Hero Vida",
                  "Okinawa","Ampere","Pure EV","Revolt","Bounce Infinity"]
    brands_ice = ["Hero MotoCorp","Honda","TVS Motor","Bajaj Auto","Royal Enfield",
                  "Suzuki","Yamaha","KTM","Jawa","Mahindra"]
    share_ev  = [0.32,0.20,0.14,0.11,0.08,0.05,0.04,0.03,0.02,0.01]
    share_ice = [0.32,0.20,0.15,0.13,0.06,0.04,0.04,0.03,0.02,0.01]
    rows = []
    for _, r in offline.iterrows():
        total = r["offline_registrations"]
        ev_u  = int(total * 0.08)
        ice_u = total - ev_u
        for b, s in zip(brands_ev,  share_ev):
            rows.append({"date": r["date"], "month_name": r["month_name"],
                         "year": r["year"], "month": r["month"],
                         "brand_name": b, "fuel_type": "EV", "registrations": int(ev_u * s)})
        for b, s in zip(brands_ice, share_ice):
            rows.append({"date": r["date"], "month_name": r["month_name"],
                         "year": r["year"], "month": r["month"],
                         "brand_name": b, "fuel_type": "ICE", "registrations": int(ice_u * s)})
    return pd.DataFrame(rows)

# ── Load ──────────────────────────────────────────────────────────────────────
df_off    = load_offline()
df_amz    = load_amazon()
df_abrand = load_amazon_brands()
df_vbrand = load_vahan_brands()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/a/a9/Amazon_logo.svg", width=110)
    st.markdown("### Filters")

    # Date range filter
    all_dates = sorted(pd.to_datetime(df_off["date"]).dt.date.unique()) if not df_off.empty else []
    min_date  = all_dates[0]  if all_dates else datetime(2025, 1, 1).date()
    max_date  = all_dates[-1] if all_dates else datetime.now().date()

    sel_start = st.date_input("From", value=min_date, min_value=min_date, max_value=max_date)
    sel_end   = st.date_input("To",   value=max_date, min_value=min_date, max_value=max_date)

    # Keep year filter for backward compat with other tabs
    all_years = sorted(df_off["year"].dropna().unique().astype(int)) if "year" in df_off.columns else []
    sel_years = st.multiselect("Year", options=all_years, default=all_years)

    st.markdown("---")
    st.caption(f"**Source:** VAHAN (MoRTH) + InsightCrafter")
    st.caption(f"**Refreshed:** {datetime.now().strftime('%d %b %Y %H:%M')} IST")
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear(); st.rerun()
    st.caption("EV/ICE Amazon split: pending fuel_type column rollout")

def yf(df):
    d = df.copy()
    if "date" in d.columns:
        d["date"] = pd.to_datetime(d["date"])
        d = d[(d["date"].dt.date >= sel_start) & (d["date"].dt.date <= sel_end)]
    if sel_years and "year" in d.columns:
        d = d[d["year"].isin(sel_years)]
    return d

foff    = yf(df_off)
fabrand = yf(df_abrand)
fvbrand = yf(df_vbrand)
# Apply date filter to Amazon data too
famz = yf(df_amz)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(f"<h1 style='color:{DARK};margin-bottom:2px'>🏍️ 2-Wheeler Sales Dashboard</h1>"
            f"<p style='color:gray;margin-top:0'>Amazon Automotive GL &nbsp;|&nbsp; "
            f"Offline (VAHAN) vs Online (Amazon) &nbsp;|&nbsp; EV & ICE &nbsp;|&nbsp; Brand View</p>",
            unsafe_allow_html=True)
st.markdown("---")

# ── KPIs ──────────────────────────────────────────────────────────────────────
tot_off   = int(foff["offline_registrations"].sum()) if not foff.empty else 0
last_row  = foff.sort_values("date").iloc[-1] if not foff.empty else None
last_off  = int(last_row["offline_registrations"]) if last_row is not None else 0
daily_avg = int(last_row["daily_avg_offline"])      if last_row is not None else 0
last_lbl  = last_row["month_name"]                  if last_row is not None else "N/A"
tot_amz   = int(famz["amazon_online_units"].sum())
tot_gms   = float(famz["amazon_online_gms"].sum())
mkt_share = round(tot_amz / (tot_off + tot_amz) * 100, 2) if (tot_off + tot_amz) else 0

# EV/ICE from brand data
ev_off  = int(fvbrand[fvbrand["fuel_type"]=="EV"]["registrations"].sum())
ice_off = int(fvbrand[fvbrand["fuel_type"]=="ICE"]["registrations"].sum())
ev_pct  = round(ev_off / (ev_off + ice_off) * 100, 1) if (ev_off + ice_off) else 0

# Date range label for KPIs
date_range_str = f"{sel_start.strftime('%b %Y')} – {sel_end.strftime('%b %Y')}"
amz_range = date_range_str

def kpi_card(title, value, bg, icon="", subtitle=""):
    sub_html = f"<div style='font-size:10px;color:rgba(255,255,255,0.75);margin-top:4px;'>{subtitle}</div>" if subtitle else ""
    return f"""
    <div style="background:{bg};border-radius:12px;padding:16px 14px 12px 14px;
                text-align:center;min-height:115px;display:flex;flex-direction:column;
                justify-content:center;box-shadow:0 2px 8px rgba(0,0,0,0.12);">
        <div style="font-size:12px;font-weight:600;color:rgba(255,255,255,0.88);
                    margin-bottom:5px;line-height:1.3;">{icon} {title}</div>
        <div style="font-size:24px;font-weight:700;color:#ffffff;line-height:1.2;">{value}</div>
        {sub_html}
    </div>"""

kpis = [
    ("Total Offline Registrations",  fmt(tot_off),     "#FF9900", "🏍️", date_range_str),
    (f"Latest Month",                fmt(last_off),    "#E68A00", "📅", last_lbl),
    ("Daily Avg (Latest Month)",     fmt(daily_avg),   "#CC7A00", "📊", f"{last_lbl} ÷ 26 days"),
    ("Amazon Online Units",          fmt(tot_amz),     "#146EB4", "🛒", amz_range),
    ("Amazon GMS",                   fmt_gms(tot_gms), "#0F5A9C", "💰", amz_range),
    ("Amazon Market Share",          f"{mkt_share}%",  "#0A4A80", "📈", "Online ÷ (Online + Offline)"),
    ("Offline EV Registrations",     fmt(ev_off),      "#00A36C", "⚡", date_range_str),
    ("Offline ICE Registrations",    fmt(ice_off),     "#5A6A5A", "🔧", date_range_str),
    ("EV Share of Offline Market",   f"{ev_pct}%",     "#007A50", "🌱", date_range_str),
]

for row_start in range(0, 9, 3):
    cols = st.columns(3)
    for i, col in enumerate(cols):
        title, value, bg, icon, subtitle = kpis[row_start + i]
        col.markdown(kpi_card(title, value, bg, icon, subtitle), unsafe_allow_html=True)
    st.markdown("<div style='margin-bottom:8px'></div>", unsafe_allow_html=True)

st.markdown("---")

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1,tab2,tab3,tab4,tab5,tab6 = st.tabs([
    "📈 Trends","🏷️ Brand View","⚡ EV vs ICE","🔄 MoM","📅 YoY","📋 Data"
])

# ═══ TAB 1 — TRENDS ══════════════════════════════════════════════════════════
with tab1:
    c1,c2 = st.columns([2,1])
    with c1:
        st.subheader("Monthly Offline Registrations")
        m = foff.groupby("month_name")["offline_registrations"].sum().reset_index()
        m = sort_months(m)
        fig = px.bar(m, x="month_name", y="offline_registrations",
                     color_discrete_sequence=[ORANGE], text="offline_registrations",
                     labels={"offline_registrations":"Registrations","month_name":"Month"})
        fig.update_traces(texttemplate="%{text:,}", textposition="outside")
        fig.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                          xaxis_tickangle=-45, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        st.subheader("Monthly Amazon Units")
        am = sort_months(df_amz[df_amz["year"].isin(sel_years)] if sel_years else df_amz)
        fig2 = px.bar(am, x="month_name", y="amazon_online_units",
                      color_discrete_sequence=[BLUE], text="amazon_online_units",
                      labels={"amazon_online_units":"Units","month_name":"Month"})
        fig2.update_traces(texttemplate="%{text:,}", textposition="outside")
        fig2.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                           xaxis_tickangle=-45, showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)

    st.markdown("---")
    st.subheader("Offline vs Online — Monthly Comparison")
    m2 = sort_months(m).rename(columns={"offline_registrations":"Offline (VAHAN)"})
    cmp = m2.merge(df_amz[["month_name","amazon_online_units","amazon_online_gms"]]
                   .rename(columns={"amazon_online_units":"Online (Amazon)"}),
                   on="month_name", how="left")
    fig3 = go.Figure()
    fig3.add_trace(go.Bar(x=cmp["month_name"], y=cmp["Offline (VAHAN)"],
                          name="Offline (VAHAN)", marker_color=ORANGE,
                          text=cmp["Offline (VAHAN)"].apply(lambda x: f"{int(x):,}"),
                          textposition="outside"))
    fig3.add_trace(go.Bar(x=cmp["month_name"], y=cmp["Online (Amazon)"],
                          name="Online (Amazon)", marker_color=BLUE,
                          text=cmp["Online (Amazon)"].apply(lambda x: f"{int(x):,}" if pd.notna(x) else ""),
                          textposition="outside"))
    fig3.update_layout(barmode="group", plot_bgcolor="rgba(0,0,0,0)",
                       paper_bgcolor="rgba(0,0,0,0)", xaxis_tickangle=-45,
                       legend=dict(orientation="h",y=1.05,x=1,xanchor="right"),
                       yaxis_title="Units")
    st.plotly_chart(fig3, use_container_width=True)

    p1,p2 = st.columns(2)
    with p1:
        st.subheader("Market Share")
        fig_pie = px.pie(values=[cmp["Offline (VAHAN)"].sum(), cmp["Online (Amazon)"].dropna().sum()],
                         names=["Offline (VAHAN)","Online (Amazon)"],
                         color_discrete_sequence=[ORANGE,BLUE], hole=0.45)
        fig_pie.update_traces(texttemplate="%{label}<br>%{percent:.1%}<br>%{value:,} units")
        st.plotly_chart(fig_pie, use_container_width=True)

    with p2:
        st.subheader("Amazon GMS Trend")
        gms_df = sort_months(df_amz[df_amz["year"].isin(sel_years)] if sel_years else df_amz)
        # Convert to Crores for clean display
        gms_df = gms_df.copy()
        gms_df["gms_cr"] = (gms_df["amazon_online_gms"] / 10000000).round(2)
        fig_gms = px.line(gms_df, x="month_name", y="gms_cr",
                          markers=True, color_discrete_sequence=[BLUE],
                          labels={"gms_cr":"GMS (₹ Cr)","month_name":"Month"},
                          text="gms_cr")
        fig_gms.update_traces(texttemplate="₹%{text:.2f} Cr", textposition="top center")
        fig_gms.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                               xaxis_tickangle=-45, yaxis_tickprefix="₹", yaxis_ticksuffix=" Cr")
        st.plotly_chart(fig_gms, use_container_width=True)

# ═══ TAB 2 — BRAND VIEW ══════════════════════════════════════════════════════
with tab2:
    st.subheader("🏷️ Top 10 Brands — Amazon Online vs VAHAN Offline")
    st.caption("Note: Amazon brand split is synthetic pending Midway refresh for InsightCrafter SQL. VAHAN brand split based on market share estimates.")

    b1,b2 = st.columns(2)

    with b1:
        st.markdown("#### Amazon Online — Top 10 EV Brands")
        ev_amz = (fabrand[fabrand["fuel_type"]=="EV"]
                  .groupby("brand_name")["units"].sum()
                  .sort_values(ascending=False).head(10).reset_index())
        fig_aev = px.bar(ev_amz, x="units", y="brand_name", orientation="h",
                         color_discrete_sequence=[GREEN], text="units",
                         labels={"units":"Units","brand_name":""})
        fig_aev.update_traces(texttemplate="%{text:,}", textposition="outside")
        fig_aev.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                               yaxis={"categoryorder":"total ascending"})
        st.plotly_chart(fig_aev, use_container_width=True)

        st.markdown("#### Amazon Online — Top 10 ICE Brands")
        ice_amz = (fabrand[fabrand["fuel_type"]=="ICE"]
                   .groupby("brand_name")["units"].sum()
                   .sort_values(ascending=False).head(10).reset_index())
        fig_aice = px.bar(ice_amz, x="units", y="brand_name", orientation="h",
                          color_discrete_sequence=[ORANGE], text="units",
                          labels={"units":"Units","brand_name":""})
        fig_aice.update_traces(texttemplate="%{text:,}", textposition="outside")
        fig_aice.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                                yaxis={"categoryorder":"total ascending"})
        st.plotly_chart(fig_aice, use_container_width=True)

    with b2:
        st.markdown("#### VAHAN Offline — Top 10 EV Brands")
        ev_vah = (fvbrand[fvbrand["fuel_type"]=="EV"]
                  .groupby("brand_name")["registrations"].sum()
                  .sort_values(ascending=False).head(10).reset_index())
        fig_vev = px.bar(ev_vah, x="registrations", y="brand_name", orientation="h",
                         color_discrete_sequence=[GREEN], text="registrations",
                         labels={"registrations":"Registrations","brand_name":""})
        fig_vev.update_traces(texttemplate="%{text:,}", textposition="outside")
        fig_vev.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                               yaxis={"categoryorder":"total ascending"})
        st.plotly_chart(fig_vev, use_container_width=True)

        st.markdown("#### VAHAN Offline — Top 10 ICE Brands")
        ice_vah = (fvbrand[fvbrand["fuel_type"]=="ICE"]
                   .groupby("brand_name")["registrations"].sum()
                   .sort_values(ascending=False).head(10).reset_index())
        fig_vice = px.bar(ice_vah, x="registrations", y="brand_name", orientation="h",
                          color_discrete_sequence=[GRAY], text="registrations",
                          labels={"registrations":"Registrations","brand_name":""})
        fig_vice.update_traces(texttemplate="%{text:,}", textposition="outside")
        fig_vice.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                                yaxis={"categoryorder":"total ascending"})
        st.plotly_chart(fig_vice, use_container_width=True)

    st.markdown("---")
    st.subheader("Brand Comparison — Amazon Online vs VAHAN Offline (EV)")
    ev_cmp = ev_amz.rename(columns={"units":"Amazon Online"}).merge(
        ev_vah.rename(columns={"registrations":"VAHAN Offline"}), on="brand_name", how="outer"
    ).fillna(0)
    fig_bcmp = go.Figure()
    fig_bcmp.add_trace(go.Bar(x=ev_cmp["brand_name"], y=ev_cmp["Amazon Online"],
                               name="Amazon Online", marker_color=BLUE,
                               text=ev_cmp["Amazon Online"].apply(lambda x: f"{int(x):,}"),
                               textposition="outside"))
    fig_bcmp.add_trace(go.Bar(x=ev_cmp["brand_name"], y=ev_cmp["VAHAN Offline"],
                               name="VAHAN Offline", marker_color=GREEN,
                               text=ev_cmp["VAHAN Offline"].apply(lambda x: f"{int(x):,}"),
                               textposition="outside"))
    fig_bcmp.update_layout(barmode="group", plot_bgcolor="rgba(0,0,0,0)",
                            paper_bgcolor="rgba(0,0,0,0)", xaxis_tickangle=-45,
                            legend=dict(orientation="h",y=1.05,x=1,xanchor="right"),
                            yaxis_title="Units / Registrations",
                            title="EV Brand: Amazon Online vs VAHAN Offline")
    st.plotly_chart(fig_bcmp, use_container_width=True)

# ═══ TAB 3 — EV vs ICE ═══════════════════════════════════════════════════════
with tab3:
    st.subheader("⚡ EV vs ICE — Monthly Trend (VAHAN Offline)")

    ev_m = (fvbrand.groupby(["month_name","fuel_type"])["registrations"]
            .sum().reset_index())
    ev_m = sort_months(ev_m)
    fig_ev = px.bar(ev_m, x="month_name", y="registrations", color="fuel_type",
                    color_discrete_map={"EV":GREEN,"ICE":GRAY}, barmode="stack",
                    text="registrations",
                    labels={"registrations":"Registrations","month_name":"Month","fuel_type":"Type"})
    fig_ev.update_traces(texttemplate="%{text:,}", textposition="inside")
    fig_ev.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                         xaxis_tickangle=-45,
                         legend=dict(orientation="h",y=1.05,x=1,xanchor="right"))
    st.plotly_chart(fig_ev, use_container_width=True)

    ev_piv = ev_m.pivot_table(index="month_name", columns="fuel_type",
                               values="registrations", aggfunc="sum").reset_index()
    if "EV" in ev_piv.columns and "ICE" in ev_piv.columns:
        ev_piv["EV_share"] = (ev_piv["EV"] / (ev_piv["EV"]+ev_piv["ICE"]) * 100).round(1)
        ev_piv = sort_months(ev_piv)

        c1,c2 = st.columns(2)
        with c1:
            st.subheader("EV Share % Trend")
            fig_sh = px.line(ev_piv, x="month_name", y="EV_share",
                             markers=True, color_discrete_sequence=[GREEN],
                             text="EV_share",
                             labels={"EV_share":"EV Share (%)","month_name":"Month"})
            fig_sh.update_traces(texttemplate="%{text:.1f}%", textposition="top center")
            fig_sh.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                                  xaxis_tickangle=-45, yaxis_ticksuffix="%")
            st.plotly_chart(fig_sh, use_container_width=True)

        with c2:
            st.subheader("EV vs ICE Total Split")
            fig_dn = px.pie(values=[int(ev_piv["EV"].sum()), int(ev_piv["ICE"].sum())],
                            names=["EV","ICE"],
                            color_discrete_sequence=[GREEN,GRAY], hole=0.5)
            fig_dn.update_traces(texttemplate="%{label}<br>%{percent:.1%}<br>%{value:,} units")
            st.plotly_chart(fig_dn, use_container_width=True)

    st.info("Amazon EV/ICE split: pending fuel_type column rollout in served_gms pipeline.", icon="ℹ️")

# ═══ TAB 4 — MoM ═════════════════════════════════════════════════════════════
with tab4:
    st.subheader("🔄 Month-over-Month Change")

    m_off = sort_months(foff.groupby("month_name")["offline_registrations"].sum().reset_index())
    m_off["mom"] = mom_pct(m_off["offline_registrations"])
    m_off["mom_lbl"] = m_off["mom"].apply(lambda x: f"{x:+.1f}%" if pd.notna(x) else "")

    m_amz = sort_months(df_amz[df_amz["year"].isin(sel_years)] if sel_years else df_amz)
    m_amz = m_amz.groupby("month_name")[["amazon_online_units","amazon_online_gms"]].sum().reset_index()
    m_amz = sort_months(m_amz)
    m_amz["mom"] = mom_pct(m_amz["amazon_online_units"])
    m_amz["mom_lbl"] = m_amz["mom"].apply(lambda x: f"{x:+.1f}%" if pd.notna(x) else "")

    c1,c2 = st.columns(2)
    with c1:
        st.markdown("**Offline (VAHAN) — MoM**")
        fig_m1 = go.Figure()
        fig_m1.add_trace(go.Bar(x=m_off["month_name"], y=m_off["offline_registrations"],
                                name="Registrations", marker_color=ORANGE,
                                text=m_off["offline_registrations"].apply(lambda x: f"{int(x):,}"),
                                textposition="outside", yaxis="y1"))
        fig_m1.add_trace(go.Scatter(x=m_off["month_name"], y=m_off["mom"],
                                    name="MoM %", mode="lines+markers+text",
                                    line=dict(color=BLUE,width=2),
                                    text=m_off["mom_lbl"], textposition="top center",
                                    yaxis="y2"))
        fig_m1.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                              xaxis_tickangle=-45,
                              yaxis=dict(title="Registrations"),
                              yaxis2=dict(title="MoM %",overlaying="y",side="right",ticksuffix="%"),
                              legend=dict(orientation="h",y=1.05,x=1,xanchor="right"))
        st.plotly_chart(fig_m1, use_container_width=True)

    with c2:
        st.markdown("**Amazon Online — MoM**")
        fig_m2 = go.Figure()
        fig_m2.add_trace(go.Bar(x=m_amz["month_name"], y=m_amz["amazon_online_units"],
                                name="Units", marker_color=BLUE,
                                text=m_amz["amazon_online_units"].apply(lambda x: f"{int(x):,}"),
                                textposition="outside", yaxis="y1"))
        fig_m2.add_trace(go.Scatter(x=m_amz["month_name"], y=m_amz["mom"],
                                    name="MoM %", mode="lines+markers+text",
                                    line=dict(color=ORANGE,width=2),
                                    text=m_amz["mom_lbl"], textposition="top center",
                                    yaxis="y2"))
        fig_m2.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                              xaxis_tickangle=-45,
                              yaxis=dict(title="Units"),
                              yaxis2=dict(title="MoM %",overlaying="y",side="right",ticksuffix="%"),
                              legend=dict(orientation="h",y=1.05,x=1,xanchor="right"))
        st.plotly_chart(fig_m2, use_container_width=True)

    st.subheader("MoM Summary Table")
    tbl = m_off[["month_name","offline_registrations","mom"]].merge(
        m_amz[["month_name","amazon_online_units","mom"]].rename(columns={"mom":"amz_mom"}),
        on="month_name", how="outer")
    tbl.columns = ["Month","Offline Units","Offline MoM %","Amazon Units","Amazon MoM %"]
    tbl["Offline Units"]  = tbl["Offline Units"].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "-")
    tbl["Amazon Units"]   = tbl["Amazon Units"].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "-")
    tbl["Offline MoM %"]  = tbl["Offline MoM %"].apply(lambda x: f"{x:+.1f}%" if pd.notna(x) else "-")
    tbl["Amazon MoM %"]   = tbl["Amazon MoM %"].apply(lambda x: f"{x:+.1f}%" if pd.notna(x) else "-")
    st.dataframe(tbl, use_container_width=True, hide_index=True)

# ═══ TAB 5 — YoY ═════════════════════════════════════════════════════════════
with tab5:
    st.subheader("📅 Year-over-Year Analysis")
    if len(sel_years) < 2:
        st.info("Select 2 or more years in the sidebar to see YoY comparison.", icon="ℹ️")
    else:
        ann = (foff.groupby("year")["offline_registrations"].sum().reset_index()
               .rename(columns={"offline_registrations":"total"}))
        ann["yoy"] = ann["total"].pct_change().mul(100).round(1)
        ann["lbl"] = ann["yoy"].apply(lambda x: f"{x:+.1f}%" if pd.notna(x) else "")

        amz_ann = (df_amz[df_amz["year"].isin(sel_years)]
                   .groupby("year")["amazon_online_units"].sum().reset_index())
        amz_ann["yoy"] = amz_ann["amazon_online_units"].pct_change().mul(100).round(1)
        amz_ann["lbl"] = amz_ann["yoy"].apply(lambda x: f"{x:+.1f}%" if pd.notna(x) else "")

        c1,c2 = st.columns(2)
        with c1:
            st.markdown("**Annual Offline Registrations**")
            fig_a1 = go.Figure()
            fig_a1.add_trace(go.Bar(x=ann["year"].astype(str), y=ann["total"],
                                    marker_color=ORANGE, name="Total",
                                    text=ann["total"].apply(lambda x: f"{int(x):,}"),
                                    textposition="outside"))
            fig_a1.add_trace(go.Scatter(x=ann["year"].astype(str), y=ann["yoy"],
                                        name="YoY %", mode="lines+markers+text",
                                        line=dict(color=BLUE,width=2),
                                        text=ann["lbl"], textposition="top center",
                                        yaxis="y2"))
            fig_a1.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                                  yaxis=dict(title="Registrations"),
                                  yaxis2=dict(title="YoY %",overlaying="y",side="right",ticksuffix="%"),
                                  legend=dict(orientation="h",y=1.05,x=1,xanchor="right"))
            st.plotly_chart(fig_a1, use_container_width=True)

        with c2:
            st.markdown("**Annual Amazon Units**")
            fig_a2 = go.Figure()
            fig_a2.add_trace(go.Bar(x=amz_ann["year"].astype(str), y=amz_ann["amazon_online_units"],
                                    marker_color=BLUE, name="Units",
                                    text=amz_ann["amazon_online_units"].apply(lambda x: f"{int(x):,}"),
                                    textposition="outside"))
            fig_a2.add_trace(go.Scatter(x=amz_ann["year"].astype(str), y=amz_ann["yoy"],
                                        name="YoY %", mode="lines+markers+text",
                                        line=dict(color=ORANGE,width=2),
                                        text=amz_ann["lbl"], textposition="top center",
                                        yaxis="y2"))
            fig_a2.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                                  yaxis=dict(title="Units"),
                                  yaxis2=dict(title="YoY %",overlaying="y",side="right",ticksuffix="%"),
                                  legend=dict(orientation="h",y=1.05,x=1,xanchor="right"))
            st.plotly_chart(fig_a2, use_container_width=True)

        st.subheader("Same-Month YoY — Offline")
        sm = foff.groupby(["year","month","month_name"])["offline_registrations"].sum().reset_index()
        fig_sm = px.line(sm, x="month", y="offline_registrations", color="year",
                         markers=True, text="offline_registrations",
                         color_discrete_sequence=px.colors.qualitative.Set2,
                         labels={"offline_registrations":"Registrations","month":"Month"})
        fig_sm.update_traces(texttemplate="%{text:,}", textposition="top center")
        fig_sm.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                              xaxis=dict(tickmode="array", tickvals=list(range(1,13)),
                                         ticktext=["Jan","Feb","Mar","Apr","May","Jun",
                                                   "Jul","Aug","Sep","Oct","Nov","Dec"]),
                              legend=dict(orientation="h",y=1.05,x=1,xanchor="right"))
        st.plotly_chart(fig_sm, use_container_width=True)

        st.subheader("YoY Summary Table")
        yt = ann[["year","total","yoy"]].copy()
        yt["total"] = yt["total"].apply(lambda x: f"{int(x):,}")
        yt["yoy"]   = yt["yoy"].apply(lambda x: f"{x:+.1f}%" if pd.notna(x) else "-")
        yt.columns  = ["Year","Total Offline Registrations","YoY Growth"]
        st.dataframe(yt, use_container_width=True, hide_index=True)

# ═══ TAB 6 — DATA ════════════════════════════════════════════════════════════
with tab6:
    with st.expander("📋 VAHAN Offline Data"):
        d = foff.copy()
        d["offline_registrations"] = d["offline_registrations"].apply(lambda x: f"{int(x):,}")
        d["daily_avg_offline"]     = d["daily_avg_offline"].apply(lambda x: f"{int(x):,}")
        st.dataframe(d.sort_values("date", ascending=False), use_container_width=True)
        st.download_button("⬇️ Download", foff.to_csv(index=False).encode(),
                           f"vahan_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv")

    with st.expander("📋 Amazon Online Data"):
        ad = df_amz.copy()
        ad["amazon_online_units"] = ad["amazon_online_units"].apply(lambda x: f"{int(x):,}")
        ad["amazon_online_gms"]   = ad["amazon_online_gms"].apply(fmt_gms)
        st.dataframe(ad.sort_values("date", ascending=False), use_container_width=True)
        st.download_button("⬇️ Download", df_amz.to_csv(index=False).encode(),
                           f"amazon_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv")

    with st.expander("📋 Brand Data"):
        st.dataframe(fabrand.sort_values(["date","brand"], ascending=[False,True]),
                     use_container_width=True)

st.markdown("---")
st.caption("Offline: VAHAN Portal (MoRTH) | Amazon: InsightCrafter (gl=263, cat=26320000) | "
           "Brand split: synthetic (real brand SQL pending Midway refresh) | "
           "EV/ICE: VAHAN fuel-wise scrape + Amazon fuel_type pending")
