import streamlit as st
import pandas as pd
import numpy as np
import random
import json
import time
import os
from urllib.request import urlopen, Request
import plotly.graph_objects as go
from scipy.spatial import KDTree

# --- CONFIG & SETUP ---
st.set_page_config(page_title="Madden Imperialism Engine", layout="wide")

# --- DATA SOURCE CONSTANTS ---
COUNTY_GEOJSON_URL = "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"
CENSUS_CENTER_URL = "https://www2.census.gov/geo/docs/reference/cenpop2020/county/CenPop2020_Mean_CO.txt"
ADJACENCY_URL = "https://www2.census.gov/geo/docs/reference/county_adjacency.txt"

# --- STATE MANAGEMENT ---
if 'game_active' not in st.session_state:
    st.session_state.game_active = False
if 'teams' not in st.session_state:
    st.session_state.teams = []
if 'county_assignments' not in st.session_state:
    st.session_state.county_assignments = {}
if 'adjacencies' not in st.session_state:
    st.session_state.adjacencies = {}

# --- DATA FETCHING & ADJACENCY LOGIC ---
@st.cache_data
def load_map_resources():
    # 1. Load GeoJSON
    try:
        req = Request(COUNTY_GEOJSON_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urlopen(req) as response:
            geojson = json.load(response)
        # Optimization: Coordinate precision
        for feature in geojson['features']:
            geom = feature['geometry']
            if geom['type'] == 'Polygon':
                geom['coordinates'] = [[[round(c, 3) for c in coord] for coord in ring] for ring in geom['coordinates']]
            elif geom['type'] == 'MultiPolygon':
                geom['coordinates'] = [[[[round(c, 3) for c in coord] for coord in ring] for ring in poly] for poly in geom['coordinates']]
    except: return None, None, None

    # 2. Load Census Centers
    try:
        df = pd.read_csv(CENSUS_CENTER_URL, dtype={'STATEFP': str, 'COUNTYFP': str})
        df['fips'] = df['STATEFP'].str.zfill(2) + df['COUNTYFP'].str.zfill(3)
        counties_df = df[['fips', 'COUNAME', 'LATITUDE', 'LONGITUDE']].rename(columns={'LATITUDE':'lat', 'LONGITUDE':'lon', 'COUNAME':'name'})
    except: return None, None, None

    # 3. Load Adjacency Data
    adj_dict = {}
    try:
        response = urlopen(ADJACENCY_URL)
        current_county = None
        for line in response:
            line = line.decode('latin-1').strip().split('\t')
            if len(line) >= 4:
                if line[1]:
                    current_county = line[1].zfill(5)
                    adj_dict[current_county] = []
                neighbor_fips = line[3].zfill(5)
                if neighbor_fips != current_county:
                    adj_dict[current_county].append(neighbor_fips)
    except: pass

    return geojson, counties_df.dropna(), adj_dict

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

def get_neighbors(team_name):
    team_counties = [fips for fips, owner in st.session_state.county_assignments.items() if owner == team_name]
    neighbors = set()
    for fips in team_counties:
        if fips in st.session_state.adjacencies:
            for adj_fips in st.session_state.adjacencies[fips]:
                neighbor_owner = st.session_state.county_assignments.get(adj_fips)
                if neighbor_owner and neighbor_owner != team_name:
                    neighbors.add(neighbor_owner)
    return list(neighbors)

# --- UI ---
st.title("🏟️ Madden Imperialism: Neighbor Battle Engine")

with st.sidebar:
    st.header("1. Roster Setup")
    input_method = st.radio("Input Method", ["Default NFL", "Upload CSV", "Manual Entry"])

    processed_teams = []

    if input_method == "Default NFL":
        found_path = next((p for p in ["inputs/nfl.csv", "nfl_teams.csv", "nfl.csv"] if os.path.exists(p)), None)
        if found_path:
            processed_teams = process_teams_df(pd.read_csv(found_path))
            st.success(f"Default NFL data loaded!")
        else:
            st.warning("No default CSV found. Please use Upload or Manual.")

    elif input_method == "Upload CSV":
        uploaded_file = st.file_uploader("Upload Teams CSV", type=["csv"])
        if uploaded_file:
            processed_teams = process_teams_df(pd.read_csv(uploaded_file))

    else:
        team_input = st.text_area("Enter Teams (Name, Lat, Lon)", "Chicago Bears, 41.8, -87.6", height=200)
        for i, line in enumerate(team_input.split('\n')):
            if ',' in line:
                p = [x.strip() for x in line.split(',')]
                processed_teams.append({"name": p[0], "lat": float(p[1]), "lon": float(p[2]), "color": get_team_color(i), "active": True})

    if st.button("Generate Map"):
        with st.spinner("Analyzing borders..."):
            geojson, counties_df, adj_dict = load_map_resources()
            if geojson and processed_teams:
                st.session_state.teams = processed_teams
                st.session_state.adjacencies = adj_dict
                st.session_state.county_assignments = assign_initial_territories(processed_teams, counties_df)
                st.session_state.game_active = True
                st.rerun()

if st.session_state.game_active:
    geojson, _ , _ = load_map_resources()
    active_teams = [t for t in st.session_state.teams if t['active']]

    col_map, col_ctrl = st.columns([2, 1])

    with col_ctrl:
        st.subheader("🎡 The Battle Wheel")

        if st.button("🎰 SPIN FOR ATTACKER", use_container_width=True):
            placeholder = st.empty()
            for _ in range(12):
                temp_team = random.choice(active_teams)
                placeholder.markdown(f"<h2 style='text-align:center;'>🌀 Picking Team...</h2><h1 style='text-align:center; color:{temp_team['color']};'>{temp_team['name']}</h1>", unsafe_allow_html=True)
                time.sleep(0.1)

            attacker = random.choice(active_teams)
            st.session_state.attacker = attacker['name']
            placeholder.markdown(f"<h2 style='text-align:center;'>⚔️ ATTACKER</h2><h1 style='text-align:center; color:{attacker['color']};'>{attacker['name']}</h1>", unsafe_allow_html=True)

        if 'attacker' in st.session_state:
            st.divider()
            if st.button("🧭 SPIN FOR DIRECTION", use_container_width=True):
                directions = [("NORTH ⬆️", "N"), ("SOUTH ⬇️", "S"), ("EAST ➡️", "E"), ("WEST ⬅️", "W")]
                placeholder = st.empty()
                for _ in range(12):
                    label, icon = random.choice(directions)
                    placeholder.markdown(f"<h1 style='text-align:center;'>{label}</h1>", unsafe_allow_html=True)
                    time.sleep(0.1)

                neighbors = get_neighbors(st.session_state.attacker)
                if neighbors:
                    target = random.choice(neighbors)
                    st.session_state.current_battle = {"att": st.session_state.attacker, "def": target}
                    placeholder.markdown(f"<h2 style='text-align:center;'>🎯 TARGET ACQUIRED</h2><h1 style='text-align:center;'>{target}</h1>", unsafe_allow_html=True)
                else:
                    placeholder.error("No neighbors found! Choose a different team.")

        if 'current_battle' in st.session_state:
            b = st.session_state.current_battle
            st.divider()
            st.markdown(f"### 🏟️ Matchup: **{b['att']}** vs **{b['def']}**")
            winner = st.radio("Who won the game?", [b['att'], b['def']], horizontal=True)

            if st.button("🏆 Record Result", use_container_width=True):
                loser = b['def'] if winner == b['att'] else b['att']
                st.session_state.county_assignments = {f: (winner if o == loser else o) for f, o in st.session_state.county_assignments.items()}
                for t in st.session_state.teams:
                    if t['name'] == loser: t['active'] = False

                del st.session_state.current_battle
                if 'attacker' in st.session_state: del st.session_state.attacker
                st.balloons()
                st.rerun()

    with col_map:
        team_to_id = {t['name']: i for i, t in enumerate(st.session_state.teams)}
        fips_list = list(st.session_state.county_assignments.keys())
        owners_list = list(st.session_state.county_assignments.values())
        z_vals = [team_to_id[name] for name in owners_list]

        fig = go.Figure(go.Choropleth(
            geojson=geojson,
            locations=fips_list,
            z=z_vals,
            colorscale=[[i/(len(st.session_state.teams)-1), t['color']] for i, t in enumerate(st.session_state.teams)],
            showscale=False,
            marker_line_width=0,
            text=owners_list,  # Add team names back to the hover data
            hoverinfo="text"   # Ensure only the team name shows on hover
        ))
        fig.update_layout(
            margin={"r":0,"t":0,"l":0,"b":0},
            height=600,
            geo=dict(scope='usa', projection_type='albers usa', showlakes=True, lakecolor='rgb(255, 255, 255)')
        )
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        # Legend
        st.write("### Active Teams")
        legend_cols = st.columns(3)
        for i, t in enumerate(active_teams):
            legend_cols[i % 3].markdown(f"<span style='color:{t['color']}; font-size: 20px;'>●</span> **{t['name']}**", unsafe_allow_html=True)

# Unlocking potential once the sludge of friction is removed!
