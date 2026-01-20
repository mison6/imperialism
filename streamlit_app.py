import streamlit as st
import pandas as pd
import numpy as np
import random
import json
import os
from urllib.request import urlopen, Request
import plotly.express as px
from scipy.spatial import KDTree

# --- CONFIG & SETUP ---
st.set_page_config(page_title="Madden Imperialism Engine", layout="wide")

# --- DATA SOURCE CONSTANTS ---
# 1. GeoJSON for drawing the county lines (Plotly's standard dataset)
COUNTY_GEOJSON_URL = "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"

# 2. Centroids for calculating ownership (Official US Census 2020 Data)
# This is a .txt file but formatted as CSV. It is the authoritative source.
CENSUS_CENTER_URL = "https://www2.census.gov/geo/docs/reference/cenpop2020/county/CenPop2020_Mean_CO.txt"

# --- STATE MANAGEMENT ---
if 'game_active' not in st.session_state:
    st.session_state.game_active = False
if 'teams' not in st.session_state:
    st.session_state.teams = []
if 'county_assignments' not in st.session_state:
    st.session_state.county_assignments = {}

# --- DATA FETCHING & PROCESSING ---
@st.cache_data
def load_map_resources():
    """
    Fetches map data from authoritative sources to avoid 404s.
    """
    # 1. Load GeoJSON
    try:
        req = Request(COUNTY_GEOJSON_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urlopen(req) as response:
            geojson = json.load(response)
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
    colors = [
        "#E31837", "#002244", "#0B2265", "#0076B6", "#A71930",
        "#241773", "#0085CA", "#FB4F14", "#FFB612", "#101820"
    ]
    return colors[index % len(colors)]

def process_teams_df(df):
    """Helper to process a dataframe into the teams list format."""
    processed = []
    # Standardize column names
    df.columns = [c.lower() for c in df.columns]

    # Check for required columns
    if all(col in df.columns for col in ['team', 'latitude', 'longitude']):
        for i, row in df.iterrows():
            color = row['color'] if 'color' in row else get_team_color(i)
            processed.append({
                "name": row['team'],
                "lat": float(row['latitude']),
                "lon": float(row['longitude']),
                "color": color,
                "active": True
            })
    return processed

# --- GAME LOGIC ---
def assign_initial_territories(teams, counties_df):
    team_coords = np.array([[t['lat'], t['lon']] for t in teams])
    county_coords = counties_df[['lat', 'lon']].values
    tree = KDTree(team_coords)
    _, indices = tree.query(county_coords)
    assignments = {counties_df.iloc[i]['fips']: teams[team_idx]['name'] for i, team_idx in enumerate(indices)}
    return assignments

# --- UI ---
st.title("🏟️ Madden Imperialism: The Professional Engine")
st.markdown("Replicating the viral map style using official US Census data.")

with st.sidebar:
    st.header("1. Roster Setup")

    # Input Method Selection - Default is now "Default NFL"
    input_method = st.radio("Input Method", ["Default NFL", "Upload CSV", "Manual Entry"])

    processed_teams = []

    if input_method == "Default NFL":
        # Look for the file in priority order
        possible_paths = ["inputs/nfl.csv"]
        found_path = None
        for p in possible_paths:
            if os.path.exists(p):
                found_path = p
                break

        if found_path:
            try:
                df_default = pd.read_csv(found_path)
                processed_teams = process_teams_df(df_default)
                if processed_teams:
                    st.success(f"Loaded {len(processed_teams)} teams from {found_path}!")
                else:
                    st.error("Default file found but columns missing.")
            except Exception as e:
                st.error(f"Error reading default file: {e}")
        else:
            st.warning("Default file (inputs/nfl.csv or nfl_teams.csv) not found. Please upload a CSV.")

    elif input_method == "Upload CSV":
        uploaded_file = st.file_uploader("Upload Teams CSV", type=["csv"], help="Columns required: Team, Latitude, Longitude. Optional: Color")
        if uploaded_file is not None:
            try:
                df_upload = pd.read_csv(uploaded_file)
                processed_teams = process_teams_df(df_upload)
                if processed_teams:
                    st.success(f"Loaded {len(processed_teams)} teams from CSV!")
                else:
                    st.error("CSV must contain columns: 'Team', 'Latitude', 'Longitude'")
            except Exception as e:
                st.error(f"Error parsing CSV: {e}")

    else:
        st.info("Input Format: Team Name, Latitude, Longitude")
        default_teams = (
            "Chicago Bears, 41.8623, -87.6167\n"
            "Green Bay Packers, 44.5013, -88.0622\n"
            "Detroit Lions, 42.3400, -83.0456\n"
            "Minnesota Vikings, 44.9735, -93.2575\n"
            "Kansas City Chiefs, 39.0489, -94.4839\n"
            "Dallas Cowboys, 32.7473, -97.0945"
        )
        team_input = st.text_area("Enter Teams", default_teams, height=200)

        for i, line in enumerate(team_input.split('\n')):
            if ',' in line:
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 3:
                    processed_teams.append({
                        "name": parts[0],
                        "lat": float(parts[1]),
                        "lon": float(parts[2]),
                        "color": get_team_color(i),
                        "active": True
                    })

    if st.button("Generate Imperialism Map"):
        with st.spinner("Fetching Census data & Calculating territories..."):
            geojson, counties_df = load_map_resources()

            if geojson and not counties_df.empty:
                if processed_teams:
                    st.session_state.teams = processed_teams
                    st.session_state.county_assignments = assign_initial_territories(processed_teams, counties_df)
                    st.session_state.game_active = True
                    st.rerun()
                else:
                    st.warning("No valid teams found. Please check your input.")
            else:
                st.error("Failed to load map resources. Please check connection.")

if st.session_state.game_active:
    geojson, counties_df = load_map_resources()
    active_teams = [t for t in st.session_state.teams if t['active']]

    col_map, col_ctrl = st.columns([3, 1])

    with col_ctrl:
        st.subheader("War Room")
        st.metric("Active Empires", len(active_teams))

        if st.button("🔥 Simulate Battle", use_container_width=True):
            if len(active_teams) > 1:
                # 1. Pick Attacker
                attacker = random.choice(active_teams)

                # 2. Pick Defender (Simplified Logic: Pick random other active team)
                potential_defenders = [t for t in active_teams if t['name'] != attacker['name']]
                if potential_defenders:
                    defender = random.choice(potential_defenders)
                    st.session_state.current_battle = {"att": attacker['name'], "def": defender['name']}

        if 'current_battle' in st.session_state:
            battle = st.session_state.current_battle
            st.divider()
            st.markdown(f"### ⚔️ {battle['att']} vs {battle['def']}")

            winner = st.radio("Battle Outcome:", [battle['att'], battle['def']])

            if st.button("Confirm Conquest"):
                loser_name = battle['def'] if winner == battle['att'] else battle['att']
                winner_name = winner

                # Update Map: Winner takes ALL of Loser's land
                new_map = st.session_state.county_assignments.copy()
                conquered_count = 0
                for fips, owner in new_map.items():
                    if owner == loser_name:
                        new_map[fips] = winner_name
                        conquered_count += 1
                st.session_state.county_assignments = new_map

                # Deactivate Loser
                for t in st.session_state.teams:
                    if t['name'] == loser_name:
                        t['active'] = False

                st.toast(f"{winner_name} annexed {conquered_count} counties from {loser_name}!")
                del st.session_state.current_battle
                st.rerun()

    with col_map:
        plot_df = pd.DataFrame(list(st.session_state.county_assignments.items()), columns=['fips', 'Team'])
        color_map = {t['name']: t['color'] for t in st.session_state.teams}

        fig = px.choropleth(
            plot_df,
            geojson=geojson,
            locations='fips',
            color='Team',
            color_discrete_map=color_map,
            scope="usa",
            title="Territorial Control",
            hover_data={'fips': False, 'Team': True}
        )

        fig.update_layout(
            margin={"r":0,"t":30,"l":0,"b":50}, # Added bottom margin for legend space
            height=650,
            dragmode=False,
            showlegend=True,
            # Legend moved below the map
            legend=dict(
                orientation="h",
                yanchor="top",
                y=-0.05,
                xanchor="center",
                x=0.5
            ),
            geo=dict(
                lakecolor='lightblue',
                projection_type='albers usa'
            )
        )
        fig.update_traces(marker_line_width=0.1, marker_line_color='white')
        st.plotly_chart(fig, use_container_width=True)

else:
    st.info("👈 Upload the provided NFL CSV or enter teams manually to generate the map.")
