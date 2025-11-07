# app.py
# -*- coding: utf-8 -*-
# Streamlit App — NOAA NWPS Gauge Network Map (Google Satellite base)

import streamlit as st
import requests
import folium
from streamlit_folium import st_folium
import pandas as pd
import time
import io
import re
import concurrent.futures
import plotly.express as px

# ---------------- Streamlit Setup ----------------
st.set_page_config(page_title="Kentucky River Gauge Map", layout="wide")
st.title("💧 Kentucky River & Stream Gauges — NOAA NWPS")
st.caption("Live stage and flow data for river gauges across Kentucky using NOAA's NWPS API.")

# ---------------- Refresh Button ----------------
refresh = st.button("🔄 Refresh Data")

# ---------------- Embedded Station Data ----------------
station_data_string = """site_no station_nm      lat     lon
03207965        GRAPEVINE CREEK NEAR PHYLLIS, KY        37.43260479     -82.3537563
03208000        LEVISA FORK BELOW FISHTRAP DAM NEAR MILLARD, KY 37.42593725     -82.4123701
03209325        ELKHORN CREEK AT BURDINE, KY    37.1878333      -82.6045694
03209410        RUSSELL FORK AT CEDARVILLE, KY  37.31295507     -82.3595549
... (paste your full list down through the final line)
371144082383401 ELKHORN CREEK AT BARNHILL RD NR DUNHAM, KY      37.19571667     -82.6428778
"""

# ---------------- Parse the Station Data ----------------
cleaned = re.sub(r'\s{2,}', '\t', station_data_string.strip())
stations_df = pd.read_csv(
    io.StringIO(cleaned),
    sep='\t',
    names=["site_no", "station_nm", "lat", "lon"],
    engine="python"
)

# Force numeric conversion for coordinates
stations_df["lat"] = pd.to_numeric(stations_df["lat"], errors="coerce")
stations_df["lon"] = pd.to_numeric(stations_df["lon"], errors="coerce")

# Drop any rows missing coordinates
stations_df = stations_df.dropna(subset=["lat", "lon"]).reset_index(drop=True)

# ---------------- Fetch NOAA NWPS Data ----------------
@st.cache_data(ttl=600)
def fetch_noaa_data(stations):
    base_url = "https://api.water.noaa.gov/nwps/v1/gauges/{id}/stageflow"
    responses = {}

    def get_data(site_id):
        url = base_url.format(id=site_id)
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            return site_id, r.json()
        except Exception as e:
            return site_id, {"error": str(e)}

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        for site_id, data in executor.map(get_data, stations):
            responses[site_id] = data

    return responses

if refresh or "noaa_data" not in st.session_state:
    with st.spinner("Fetching latest gauge data from NOAA..."):
        st.session_state["noaa_data"] = fetch_noaa_data(stations_df["site_no"].tolist())

responses = st.session_state["noaa_data"]

# ---------------- Map Setup (Google Satellite) ----------------
avg_lat = stations_df["lat"].mean()
avg_lon = stations_df["lon"].mean()

m = folium.Map(
    location=[avg_lat, avg_lon],
    zoom_start=7,
    control_scale=True,
    tiles=None
)
folium.TileLayer(
    tiles="https://mt1.google.com/vt/lyrs=s,h&x={x}&y={y}&z={z}",
    attr="Map data ©2025 Google",
    name="Google Satellite",
    overlay=False,
    control=True,
).add_to(m)

# ---------------- Add Markers ----------------
valid_count = 0

for _, row in stations_df.iterrows():
    site = str(row["site_no"])
    lat, lon = row["lat"], row["lon"]
    data = responses.get(site, {})
    color = "red"
    popup_html = f"<b>Station:</b> {site}<br><b>Name:</b> {row['station_nm']}<br>"

    if data and "error" not in data:
        valid_count += 1
        color = "blue"
        popup_html += f"<b>Valid Time:</b> {data.get('validTime','N/A')}<br>"
        popup_html += f"<b>Generated Time:</b> {data.get('generatedTime','N/A')}<br>"
        popup_html += f"<b>Primary:</b> {data.get('primary','N/A')}<br>"
        popup_html += f"<b>Secondary:</b> {data.get('secondary','N/A')}<br>"

        obs_data = data.get("observed", {}).get("data", [])
        if obs_data:
            obs = obs_data[-1]
            popup_html += f"<b>Most Recent Observation:</b> {obs}"
    else:
        popup_html += f"⚠️ No API data<br>{data.get('error','')}"

    folium.CircleMarker(
        location=[lat, lon],
        radius=6,
        color=color,
        fill=True,
        fill_opacity=0.9,
        popup=folium.Popup(popup_html, max_width=300),
        tooltip=f"{row['station_nm']} ({site})"
    ).add_to(m)

folium.LayerControl().add_to(m)

# ---------------- Map Display ----------------
st.markdown(
    f"**Total Stations:** {len(stations_df)} | ✅ Successful: {valid_count} | ⚠️ Failed: {len(stations_df) - valid_count}"
)
st.caption(f"Last updated: {time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
st_folium(m, width=1000, height=650)

# ---------------- Sidebar: Station Data Viewer ----------------
st.sidebar.header("📊 Station Data Viewer")
selected_station = st.sidebar.selectbox("Select a Station", stations_df["site_no"].tolist())

if selected_station:
    data = responses.get(str(selected_station))
    if (
        data
        and "error" not in data
        and isinstance(data, dict)
        and "observed" in data
        and "data" in data["observed"]
    ):
        obs_df = pd.DataFrame(data["observed"]["data"])
        if not obs_df.empty:
            obs_df["time"] = pd.to_datetime(obs_df.get("validTime"), errors="coerce")
            obs_df = obs_df.dropna(subset=["time"])
            y_col = "primary" if "primary" in obs_df.columns else obs_df.columns[1]
            fig = px.line(
                obs_df,
                x="time",
                y=y_col,
                title=f"Observed {y_col} — Station {selected_station}",
                labels={y_col: y_col.capitalize(), "time": "Time (UTC)"},
            )
            st.sidebar.plotly_chart(fig, use_container_width=True)
        else:
            st.sidebar.warning("No observation data available for this station.")
    else:
        st.sidebar.warning("No data available or fetch error for this station.")
