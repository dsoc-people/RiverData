# app.py
# -*- coding: utf-8 -*-
# Streamlit App — NOAA NWPS Gauge Network Map (Google Satellite base)

import streamlit as st
import requests
import folium
from streamlit_folium import st_folium
import pandas as pd
import time
import plotly.express as px

# ---------------- Streamlit Setup ----------------
st.set_page_config(page_title="Kentucky River Gauge Map", layout="wide")
st.title("💧 Kentucky River & Stream Gauges — NOAA NWPS")
st.caption("Live stage and flow data for river gauges across Kentucky using NOAA's NWPS API.")

# ---------------- Refresh Button ----------------
refresh = st.button("🔄 Refresh Data")

# ---------------- Embedded Station Data ----------------
station_data_string = """site_no station_nm lat lon
03207965 GRAPEVINE_CREEK_NEAR_PHYLLIS 37.43260479 -82.3537563
03208000 LEVISA_FORK_BELOW_FISHTRAP_DAM 37.42593725 -82.4123701
03209500 LEVISA_FORK_AT_PIKEVILLE 37.4642676 -82.5262632
03314500 BARREN_RIVER_AT_BOWLING_GREEN 37.0028201 -86.432768
03320000 GREEN_RIVER_AT_CALHOUN 37.533935 -87.2638873
03321500 GREEN_RIVER_AT_SPOTTSVILLE 37.8583774 -87.4097294
03322190 OHIO_RIVER_AT_HENDERSON 37.84559817 -87.5922359
03611000 OHIO_RIVER_AT_PADUCAH 37.0895004 -88.594492
"""  # (You can paste your full dataset here)

stations_df = pd.read_csv(pd.io.common.StringIO(station_data_string), delim_whitespace=True)

# ---------------- Fetch NOAA NWPS Data ----------------
@st.cache_data(ttl=600)
def fetch_noaa_data(stations):
    base_url = "https://api.water.noaa.gov/nwps/v1/gauges/{id}/stageflow"
    responses = {}
    for s in stations:
        url = base_url.format(id=s)
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            responses[s] = r.json()
            time.sleep(0.1)
        except requests.exceptions.RequestException:
            responses[s] = None
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
    attr="Google Satellite",
    name="Google Satellite",
    overlay=False,
    control=True,
).add_to(m)

valid_count = 0

# ---------------- Add Markers ----------------
for _, row in stations_df.iterrows():
    site = row["site_no"]
    lat, lon = row["lat"], row["lon"]
    data = responses.get(site, None)
    color = "red"
    popup_html = f"<b>Station:</b> {site}<br><b>Name:</b> {row['station_nm']}<br>"

    if data and isinstance(data, dict):
        valid_count += 1
        color = "blue"
        popup_html += f"<b>Valid Time:</b> {data.get('validTime','N/A')}<br>"
        popup_html += f"<b>Generated Time:</b> {data.get('generatedTime','N/A')}<br>"
        popup_html += f"<b>Primary:</b> {data.get('primary','N/A')}<br>"
        popup_html += f"<b>Secondary:</b> {data.get('secondary','N/A')}"

        # Add observed data if present
        if "observed" in data and "data" in data["observed"]:
            obs = data["observed"]["data"][-1] if data["observed"]["data"] else {}
            if obs:
                popup_html += f"<br><b>Most Recent Observation:</b> {obs}"
    else:
        popup_html += "⚠️ No API data"

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
st.markdown(f"**Total Stations:** {len(stations_df)} | ✅ Successful: {valid_count} | ⚠️ Failed: {len(stations_df)-valid_count}")
st_map = st_folium(m, width=1000, height=650)

# ---------------- Sidebar: Station Details ----------------
st.sidebar.header("📊 Station Data Viewer")
selected_station = st.sidebar.selectbox("Select a Station", stations_df["site_no"].tolist())

if selected_station:
    data = responses.get(selected_station)
    if data and isinstance(data, dict) and "observed" in data and "data" in data["observed"]:
        obs_df = pd.DataFrame(data["observed"]["data"])
        if not obs_df.empty:
            obs_df["time"] = pd.to_datetime(obs_df["validTime"], errors="coerce")
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
        st.sidebar.warning("No data available for this station.")
