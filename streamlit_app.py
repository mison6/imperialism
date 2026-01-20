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
if 'battle_log' not in st.session_state:
    st.session_state.battle_log = []
if 'is_replaying' not in st.session_state:
    st.session_state.is_replaying = False
if 'trigger_replay' not in st.session_state:
    st.session_state.trigger_replay = False
if 'last_loaded_file_id' not in st.session_state:
    st.session_state.last_loaded_file_id = None

# --- DATA FETCHING & LOGIC ---
@st.cache_data
def load_map_resources():
    try:
        req = Request(COUNTY_GEOJSON_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urlopen(req) as response:
            geojson = json.load(response)
        # Simplify geometry for performance
        for feature in geojson['features']:
            geom = feature['geometry']
            if geom['type'] == 'Polygon':
                geom['coordinates'] = [[[round(c, 3) for c in coord] for coord in ring] for ring in geom['coordinates']]
            elif geom['type'] == 'MultiPolygon':
                geom['coordinates'] = [[[[round(c, 3) for c in coord] for coord in ring] for ring in poly] for poly in geom['coordinates']]
    except: return None, None, None

    try:
        df = pd.read_csv(CENSUS_CENTER_URL, dtype={'STATEFP': str, 'COUNTYFP': str})
        df['fips'] = df['STATEFP'].str.zfill(2) + df['COUNTYFP'].str.zfill(3)
        counties_df = df[['fips', 'COUNAME', 'LATITUDE', 'LONGITUDE']].rename(columns={'LATITUDE':'lat', 'LONGITUDE':'lon', 'COUNAME':'name'})
    except: return None, None, None

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

def render_map(geojson, county_assignments, teams_list):
    team_to_id = {t['name']: i for i, t in enumerate(teams_list)}
    fips_list = list(county_assignments.keys())
    owners_list = list(county_assignments.values())
    z_vals = [team_to_id[name] for name in owners_list]

    fig = go.Figure(go.Choropleth(
        geojson=geojson,
        locations=fips_list,
        z=z_vals,
        colorscale=[[i/(max(1, len(teams_list)-1)), t['color']] for i, t in enumerate(teams_list)],
        showscale=False,
        marker_line_width=0,
        text=owners_list,
        hoverinfo="text",
        hovertemplate="<b>Owner:</b> %{text}<extra></extra>"
    ))
    fig.update_layout(
        margin={"r":0,"t":0,"l":0,"b":0},
        height=650,
        geo=dict(scope='usa', projection_type='albers usa', showlakes=True, lakecolor='rgb(255, 255, 255)')
    )
    return fig

# --- UI ---
st.title("🏟️ Madden Imperialism Engine")

with st.sidebar:
    st.header("🎮 Game Control")
    mode = st.radio("Select Action", ["New Game", "Load Session"])

    if mode == "New Game":
        input_type = st.radio("Team Source", ["Default NFL", "Manual Entry"])
        if st.button("🚀 Start Engine"):
            with st.spinner("Analyzing borders..."):
                geojson, counties_df, adj_dict = load_map_resources()
                if input_type == "Default NFL":
                    path = next((p for p in ["nfl.csv", "inputs/nfl.csv"] if os.path.exists(p)), None)
                    if path:
                        st.session_state.teams = process_teams_df(pd.read_csv(path))
                    else:
                        st.error("nfl.csv not found.")
                st.session_state.adjacencies = adj_dict
                st.session_state.county_assignments = assign_initial_territories(st.session_state.teams, counties_df)
                st.session_state.battle_log = []
                st.session_state.game_active = True
                st.session_state.last_loaded_file_id = None
                st.rerun()

    else:
        uploaded_file = st.file_uploader("📂 Load JSON Save", type=["json"])
        if uploaded_file:
            # Check if this is a new file we haven't replayed yet
            current_file_id = uploaded_file.name + str(uploaded_file.size)

            if st.session_state.last_loaded_file_id != current_file_id:
                data = json.load(uploaded_file)
                st.session_state.teams = data["teams"]
                st.session_state.county_assignments = data["counties"]
                st.session_state.battle_log = data["history"]
                st.session_state.game_active = True
                st.session_state.trigger_replay = True
                st.session_state.last_loaded_file_id = current_file_id
                st.success("Save Loaded! Starting replay...")

    if st.session_state.game_active:
        st.divider()
        save_data = {
            "teams": st.session_state.teams,
            "counties": st.session_state.county_assignments,
            "history": st.session_state.battle_log
        }
        st.download_button("💾 Save Progress", data=json.dumps(save_data), file_name="madden_empire_save.json", mime="application/json")

if st.session_state.game_active:
    geojson, counties_df, _ = load_map_resources()
    active_teams = [t for t in st.session_state.teams if t['active']]

    col_map, col_ctrl = st.columns([2, 1])

    with col_map:
        map_placeholder = st.empty()
        if not st.session_state.is_replaying:
            map_placeholder.plotly_chart(render_map(geojson, st.session_state.county_assignments, st.session_state.teams), use_container_width=True)

    with col_ctrl:
        st.subheader("🛠️ Battle Management")
        replay_speed = st.slider("Animation Speed", 0.5, 5.0, 1.0)

        # Trigger Replay logic
        if (st.button("⏪ Watch History") or st.session_state.trigger_replay) and st.session_state.battle_log:
            st.session_state.trigger_replay = False
            st.session_state.is_replaying = True

            # 1. Reset actual session state to Day 0
            st.session_state.county_assignments = assign_initial_territories(st.session_state.teams, counties_df)
            for t in st.session_state.teams:
                t['active'] = True

            replay_info = st.empty()
            replay_info.info("🎬 Replaying History: Day 0")
            map_placeholder.plotly_chart(render_map(geojson, st.session_state.county_assignments, st.session_state.teams), use_container_width=True)
            time.sleep(1.5 / replay_speed)

            # 2. Sequential state progression
            for i, battle in enumerate(st.session_state.battle_log):
                att, dfn, win = battle['att'], battle['def'], battle['winner']
                loser = dfn if win == att else att

                replay_info.markdown(f"**Battle {i+1}:** {att} ⚔️ {dfn} ... **Winner: {win}!**")

                # Update actual session state
                st.session_state.county_assignments = {f: (win if o == loser else o) for f, o in st.session_state.county_assignments.items()}
                for t in st.session_state.teams:
                    if t['name'] == loser: t['active'] = False

                map_placeholder.plotly_chart(render_map(geojson, st.session_state.county_assignments, st.session_state.teams), use_container_width=True)
                time.sleep(1.0 / replay_speed)

            st.session_state.is_replaying = False
            replay_info.success("✅ Replay Complete! Final state persisted.")
            time.sleep(1.0)
            st.rerun() # Refresh to clear out UI artifacts and lock the final state

        st.divider()
        if st.button("🎰 SPIN FOR BATTLE", use_container_width=True, disabled=st.session_state.is_replaying):
            placeholder = st.empty()
            attacker = random.choice(active_teams)
            for _ in range(8):
                temp = random.choice(active_teams)
                placeholder.markdown(f"<h2 style='text-align:center;'>🌀 Picking Attacker...</h2><h1 style='text-align:center; color:{temp['color']};'>{temp['name']}</h1>", unsafe_allow_html=True)
                time.sleep(0.08)

            placeholder.markdown(f"<h2 style='text-align:center;'>⚔️ ATTACKER</h2><h1 style='text-align:center; color:{attacker['color']};'>{attacker['name']}</h1>", unsafe_allow_html=True)
            time.sleep(1.0)

            neighbors = get_neighbors(attacker['name'])
            if neighbors:
                for _ in range(8):
                    temp = random.choice(neighbors)
                    placeholder.markdown(f"<h2 style='text-align:center;'>🏹 Hunting Target...</h2><h1 style='text-align:center;'>{temp}</h1>", unsafe_allow_html=True)
                    time.sleep(0.08)

                target = random.choice(neighbors)
                st.session_state.current_battle = {"att": attacker['name'], "def": target}
                placeholder.markdown(f"<h2 style='text-align:center;'>🎯 MATCHUP</h2><h1 style='text-align:center; color:{attacker['color']};'>{attacker['name']}</h1><h3 style='text-align:center;'>VS</h3><h1 style='text-align:center;'>{target}</h1>", unsafe_allow_html=True)
            else:
                placeholder.error(f"{attacker['name']} has no neighbors!")

        if 'current_battle' in st.session_state:
            b = st.session_state.current_battle
            st.markdown(f"### Match: **{b['att']}** vs **{b['def']}**")
            winner = st.radio("Select Winner", [b['att'], b['def']], horizontal=True)
            if st.button("🏆 Record Win", use_container_width=True):
                loser = b['def'] if winner == b['att'] else b['att']
                st.session_state.battle_log.append({"att": b['att'], "def": b['def'], "winner": winner})
                st.session_state.county_assignments = {f: (winner if o == loser else o) for f, o in st.session_state.county_assignments.items()}
                for t in st.session_state.teams:
                    if t['name'] == loser: t['active'] = False
                del st.session_state.current_battle
                st.rerun()

    with col_map:
        st.write("### Active Empires")
        legend_cols = st.columns(4)
        for i, t in enumerate(active_teams):
            legend_cols[i % 4].markdown(f"<span style='color:{t['color']};'>●</span> {t['name']}", unsafe_allow_html=True)
