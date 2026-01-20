import streamlit as st
import pandas as pd
import numpy as np
import random
import json
import os
from urllib.request import urlopen, Request
import plotly.graph_objects as go
from scipy.spatial import KDTree

# --- CONFIG & SETUP ---
st.set_page_config(page_title="Madden Imperialism Engine", layout="wide")

# --- DATA SOURCE CONSTANTS ---
COUNTY_GEOJSON_URL = "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"
CENSUS_CENTER_URL = "https://www2.census.gov/geo/docs/reference/cenpop2020/county/CenPop2020_Mean_CO.txt"

# --- STATE MANAGEMENT ---
if 'game_active' not in st.session_state:
    st.session_state.game_active = False
if 'teams' not in st.session_state:
    st.session_state.teams = []
if 'county_assignments' not in st.session_state:
    st.session_state.county_assignments = {}

# --- DATA FETCHING & OPTIMIZATION ---
@st.cache_data
def load_map_resources():
    """
    Fetches and optimizes map data for high-speed rendering.
    """
    # 1. Load and Optimize GeoJSON
    try:
        req = Request(COUNTY_GEOJSON_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urlopen(req) as response:
            geojson = json.load(response)

        # Optimization: Reduce coordinate precision to 3 decimal places
        # This drastically reduces the JSON size sent to the client.
        for feature in geojson['features']:
            geom = feature['geometry']
            if geom['type'] == 'Polygon':
                geom['coordinates'] = [[[round(c, 3) for c in coord] for coord in ring] for ring in geom['coordinates']]
            elif geom['type'] == 'MultiPolygon':
                geom['coordinates'] = [[[[round(c, 3) for c in coord] for coord in ring] for ring in poly] for poly in geom['coordinates']]

    except Exception as e:
        st.error(f"Error loading GeoJSON: {e}")
        return None, None

    # 2. Load Census Data
    try:
        df = pd.read_csv(CENSUS_CENTER_URL, dtype={'STATEFP': str, 'COUNTYFP': str})
        df['STATEFP'] = df['STATEFP'].apply(lambda x: x.zfill(2))
        df['COUNTYFP'] = df['COUNTYFP'].apply(lambda x: x.zfill(3))
        df['fips'] = df['STATEFP'] + df['COUNTYFP']
        df = df.rename(columns={'LATITUDE': 'lat', 'LONGITUDE': 'lon', 'COUNAME': 'name'})
        return geojson, df[['fips', 'name', 'lat', 'lon']].dropna()
    except Exception as e:
        st.error(f"Error loading Census Data: {e}")
        return None, None

def get_team_color(index):
    colors = ["#E31837", "#002244", "#0B2265", "#0076B6", "#A71930", "#241773", "#0085CA", "#FB4F14", "#FFB612", "#101820"]
    return colors[index % len(colors)]

def process_teams_df(df):
    processed = []
    df.columns = [c.lower() for c in df.columns]
    if all(col in df.columns for col in ['team', 'latitude', 'longitude']):
        for i, row in df.iterrows():
            color = row['color'] if 'color' in row else get_team_color(i)
            processed.append({"name": row['team'], "lat": float(row['latitude']), "lon": float(row['longitude']), "color": color, "active": True})
    return processed

def assign_initial_territories(teams, counties_df):
    team_coords = np.array([[t['lat'], t['lon']] for t in teams])
    county_coords = counties_df[['lat', 'lon']].values
    tree = KDTree(team_coords)
    _, indices = tree.query(county_coords)
    return {counties_df.iloc[i]['fips']: teams[team_idx]['name'] for i, team_idx in enumerate(indices)}

# --- UI ---
st.title("🏟️ Madden Imperialism: Optimized Engine")

with st.sidebar:
    st.header("1. Roster Setup")
    input_method = st.radio("Input Method", ["Default NFL", "Upload CSV", "Manual Entry"])
    processed_teams = []

    if input_method == "Default NFL":
        found_path = next((p for p in ["inputs/nfl.csv", "nfl_teams.csv", "nfl.csv"] if os.path.exists(p)), None)
        if found_path:
            processed_teams = process_teams_df(pd.read_csv(found_path))
            st.success(f"Default data loaded!")
        else:
            st.warning("Default file not found.")
    elif input_method == "Upload CSV":
        uploaded_file = st.file_uploader("Upload Teams CSV", type=["csv"])
        if uploaded_file:
            processed_teams = process_teams_df(pd.read_csv(uploaded_file))
    else:
        team_input = st.text_area("Enter Teams (Name, Lat, Lon)", "Chicago Bears, 41.8623, -87.6167", height=200)
        for i, line in enumerate(team_input.split('\n')):
            if ',' in line:
                p = [x.strip() for x in line.split(',')]
                processed_teams.append({"name": p[0], "lat": float(p[1]), "lon": float(p[2]), "color": get_team_color(i), "active": True})

    if st.button("Generate Map"):
        with st.spinner("Processing..."):
            geojson, counties_df = load_map_resources()
            if geojson and processed_teams:
                st.session_state.teams = processed_teams
                st.session_state.county_assignments = assign_initial_territories(processed_teams, counties_df)
                st.session_state.game_active = True
                st.rerun()

if st.session_state.game_active:
    geojson, _ = load_map_resources()
    active_teams = [t for t in st.session_state.teams if t['active']]

    col_map, col_ctrl = st.columns([3, 1])

    with col_ctrl:
        st.subheader("War Room")
        if st.button("🔥 Simulate Battle", use_container_width=True):
            if len(active_teams) > 1:
                att = random.choice(active_teams)
                dfn = random.choice([t for t in active_teams if t['name'] != att['name']])
                st.session_state.current_battle = {"att": att['name'], "def": dfn['name']}

        if 'current_battle' in st.session_state:
            b = st.session_state.current_battle
            winner = st.radio(f"Winner of {b['att']} vs {b['def']}:", [b['att'], b['def']])
            if st.button("Confirm Conquest"):
                loser = b['def'] if winner == b['att'] else b['att']
                st.session_state.county_assignments = {f: (winner if o == loser else o) for f, o in st.session_state.county_assignments.items()}
                for t in st.session_state.teams:
                    if t['name'] == loser: t['active'] = False
                del st.session_state.current_battle
                st.rerun()

    with col_map:
        # Optimization: Map names to IDs for categorical plotting
        team_to_id = {t['name']: i for i, t in enumerate(st.session_state.teams)}
        fips_list = list(st.session_state.county_assignments.keys())
        owners_list = list(st.session_state.county_assignments.values())

        # Build the Figure using Graph Objects (faster than PX for large GeoJSON)
        fig = go.Figure(go.Choropleth(
            geojson=geojson,
            locations=fips_list,
            z=[team_to_id[name] for name in owners_list],
            colorscale=[[i/(len(st.session_state.teams)-1), t['color']] for i, t in enumerate(st.session_state.teams)],
            showscale=False,
            marker_line_width=0, # Remove lines for speed
            hovertext=owners_list,
            hoverinfo="text"
        ))

        # Add a custom legend using invisible traces
        for t in st.session_state.teams:
            if t['active']:
                fig.add_trace(go.Scattergeo(
                    lat=[None], lon=[None],
                    mode='markers',
                    marker=dict(size=10, color=t['color']),
                    legendgroup=t['name'],
                    name=t['name'],
                    showlegend=True
                ))

        fig.update_layout(
            margin={"r":0,"t":0,"l":0,"b":0},
            height=600,
            geo=dict(scope='usa', projection_type='albers usa', showlakes=True, lakecolor='rgb(255, 255, 255)'),
            legend=dict(orientation="h", yanchor="top", y=-0.05, xanchor="center", x=0.5)
        )

        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
