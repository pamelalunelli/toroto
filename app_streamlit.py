# ===========================
# app_streamlit.py
# CLEAN DASHBOARD VERSION
# ===========================

import os
import time

import streamlit as st
import requests
import pandas as pd
import pydeck as pdk

#BASE_URL = "http://host.docker.internal:8000/api/v1"
BASE_URL = os.getenv("BASE_URL")

st.set_page_config(
    page_title="Toroto Geospatial Explorer",
    layout="wide"
)

st.title("🌍 Toroto Geospatial Explorer")
st.caption("Interactive dashboard powered by FastAPI + PostGIS")

# -------------------------------------------------
# SIDEBAR
# -------------------------------------------------

query = st.sidebar.selectbox(
    "Choose Query",
    [
        "AI Query",
        "All Interventions",
        "Nearest Neighbor",
        "Within Radius",
        "Within Area",
        "Status Summary",
        "By Region",
        "By Subtype",
        "Timeline"
    ]
)

# -------------------------------------------------
# HELPERS
# -------------------------------------------------

def api_get(path, params=None, retries=5):
    url = f"{BASE_URL}{path}"

    for _ in range(retries):
        try:
            r = requests.get(url, params=params, timeout=10)
            if r.status_code == 200:
                return r.json()
        except:
            pass
        time.sleep(2)

    raise Exception("API down")


def make_map(points):
    if not points:
        st.warning("No points to display.")
        return

    rows = []
    for p in points:
        coords = p.get("coordinates")

        if coords and isinstance(coords, dict):
            lat = coords.get("lat")
            lon = coords.get("lon")
        else:
            lat = p.get("lat")
            lon = p.get("lon")

        if not lat or not lon:
            continue

        rows.append({
            "lat": lat,
            "lon": lon,
            "id": p.get("id", ""),
            "status": p.get("status", ""),
            "subtype": p.get("subtype", "")
        })

    df = pd.DataFrame(rows)

    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df = df.dropna(subset=["lat", "lon"])

    if df.empty:
        st.error("No valid coordinates.")
        return

    view_state = pdk.ViewState(
        latitude=float(df["lat"].mean()),
        longitude=float(df["lon"].mean()),
        zoom=11,
        pitch=0
    )

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=df,
        get_position="[lon, lat]",
        get_radius=120,
        radius_min_pixels=6,
        pickable=True
    )

    col1, col2 = st.columns([2, 1])

    with col1:
        st.pydeck_chart(
            pdk.Deck(
                map_style=None,
                initial_view_state=view_state,
                layers=[layer],
                tooltip={"text": "ID: {id}\n{subtype}\n{status}"}
            ),
            use_container_width=True
        )

    with col2:
        st.dataframe(df)

# -------------------------------------------------
# ALL INTERVENTIONS (AUTO-LOAD)
# -------------------------------------------------

if query == "All Interventions":

    st.subheader("All Interventions")

    status = st.sidebar.text_input("Status")
    subtype = st.sidebar.text_input("Subtype")
    limit = st.sidebar.number_input("Limit", 1, 1000, 200)

    params = {
        k: v
        for k, v in {
            "status": status,
            "subtype": subtype,
            "limit": limit
        }.items()
        if v not in [None, "", "null"]
    }

    data = api_get("/interventions", params)

    st.metric("Total Found", data["total_found"])

    make_map(data.get("items", []))


# -------------------------------------------------
# NEAREST
# -------------------------------------------------

elif query == "Nearest Neighbor":

    st.subheader("Nearest Neighbor")

    lat = st.sidebar.number_input("Latitude", value=20.701)
    lon = st.sidebar.number_input("Longitude", value=-103.321)

    if st.sidebar.button("Search"):

        data = api_get("/interventions/nearest", {
            "lat": lat,
            "lon": lon
        })

        st.metric("Distance (m)", round(data["distance_m"], 2))
        make_map([data["intervention"]])


# -------------------------------------------------
# WITHIN RADIUS
# -------------------------------------------------

elif query == "Within Radius":

    st.subheader("Within Radius")

    lat = st.sidebar.number_input("Latitude", value=20.700)
    lon = st.sidebar.number_input("Longitude", value=-103.320)
    radius = st.sidebar.slider("Radius KM", 1, 100, 5)

    if st.sidebar.button("Search"):

        data = api_get("/interventions/within-radius", {
            "lat": lat,
            "lon": lon,
            "radius_km": radius
        })

        st.metric("Total Found", data["total_found"])
        make_map(data.get("interventions", []))


# -------------------------------------------------
# WITHIN AREA
# -------------------------------------------------

elif query == "Within Area":

    st.subheader("Within Area")

    area_id = st.sidebar.selectbox(
        "Area ID",
        ["zone_a", "zone_b", "zone_c"]
    )

    if st.sidebar.button("Search"):

        data = api_get(f"/interventions/within-area/{area_id}")

        st.metric("Total Found", data["total_found"])
        make_map(data.get("interventions", []))


# -------------------------------------------------
# STATUS SUMMARY
# -------------------------------------------------

elif query == "Status Summary":

    data = api_get("/status-summary")
    df = pd.DataFrame(list(data.items()), columns=["status", "total"])

    st.bar_chart(df.set_index("status"))
    st.dataframe(df)


# -------------------------------------------------
# BY REGION
# -------------------------------------------------

elif query == "By Region":

    data = api_get("/analytics/by-region")
    df = pd.DataFrame(data)

    st.bar_chart(df.set_index("region"))
    st.dataframe(df)


# -------------------------------------------------
# BY SUBTYPE
# -------------------------------------------------

elif query == "By Subtype":

    data = api_get("/analytics/by-subtype")
    df = pd.DataFrame(data)

    st.bar_chart(df.set_index("subtype"))
    st.dataframe(df)


# -------------------------------------------------
# TIMELINE
# -------------------------------------------------

elif query == "Timeline":

    data = api_get("/analytics/timeline")
    df = pd.DataFrame(data)

    st.line_chart(df.set_index("month"))
    st.dataframe(df)

# -------------------------------------------------
# AI QUERY
# -------------------------------------------------

elif query == "AI Query":

    st.subheader("🤖 AI Natural Language Query")
    st.caption("Powered by Groq + Llama 3.3 70B — routes to PostGIS via structured intent")

    question = st.text_area(
        "Ask a question in natural language",
        placeholder="e.g. Which validated interventions are within 5km of 20.7, -103.3?\nHow many interventions are in zone_a?\nWhat is the closest reforestacion to 20.65, -103.4?",
        height=100
    )

    if st.button("Ask"):
        if not question.strip():
            st.warning("Please enter a question.")
        else:
            with st.spinner("Interpreting and querying..."):
                try:
                    r = requests.post(
                        f"{BASE_URL}/query",
                        json={"question": question}
                    )
                    r.raise_for_status()
                    data = r.json()

                    query_type = data.get("query_type", "")
                    intent = data.get("intent", {})

                    st.success(f"Query type detected: `{query_type}`")

                    with st.expander("Intent extracted by LLM"):
                        st.json(intent)

                    if query_type == "nearest_neighbor":
                        result = data.get("result")
                        if result:
                            st.metric("Closest intervention", result["id"])
                            st.metric("Distance (m)", round(result["distance_m"], 2))
                            make_map([result])
                        else:
                            st.warning("No result found.")

                    elif query_type in ("within_radius", "within_area"):
                        results = data.get("results") or data.get("interventions") or []
                        st.metric("Total found", data.get("total", 0))
                        if results:
                            make_map(results)

                    elif query_type == "status_summary":
                        result = data.get("result", {})
                        df = pd.DataFrame(list(result.items()), columns=["status", "total"])
                        st.bar_chart(df.set_index("status"))
                        st.dataframe(df)

                    elif query_type == "subtype_by_region":
                        result = data.get("result", [])
                        df = pd.DataFrame(result)
                        st.dataframe(df)

                except requests.exceptions.HTTPError as e:
                    st.error(f"API error: {e.response.json().get('detail', str(e))}")
                except Exception as e:
                    st.error(f"Unexpected error: {str(e)}")