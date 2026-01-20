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

st.markdown("""
    <style>
    .reportview-container .main .block-container { padding-top: 2rem; }
    .stButton>button { border-radius: 8px; }
    div[data-testid="stVerticalBlock"] > div:has(div.js-plotly-plot) {
        min-height: 650px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- CONSTANTS ---
COUNTY_GEOJSON_URL = "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"
CENSUS_CENTER_URL = "https://www2.census.gov/geo/docs/reference/cenpop2020/county/CenPop2020_Mean_CO.txt"
ADJACENCY_URL = "https://www2.census.gov/geo/docs/reference/county_adjacency.txt"

# --- STATE INITIALIZATION ---
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
if 'stop_replay' not in st.session_state:
    st.session_state.stop_replay = False
if 'trigger_replay' not in st.session_state:
    st.session_state.trigger_replay = False
if 'last_loaded_file_id' not in st.session_state:
    st.session_state.last_loaded_file_id = None

# --- LOGIC ---
@st.cache_data
def load_map_resources():
    try:
        req = Request(COUNTY_GEOJSON_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urlopen(req) as response:
            geojson = json.load(response)
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
            line_str = line.decode('latin-1').strip()
            if not line_str: continue
            parts = line_str.split('\t')
            if len(parts) >= 4:
                if parts[1].strip():
                    current_county = parts[1].strip().zfill(5)
                    if current_county not in adj_dict:
                        adj_dict[current_county] = []
                neighbor_fips = parts[3].strip().zfill(5)
                if current_county and neighbor_fips != current_county:
                    adj_dict[current_county].append(neighbor_fips)
    except: pass

    return geojson, counties_df.dropna(), adj_dict

def process_teams_df(df):
    processed = []
    df.columns = [c.lower() for c in df.columns]
    for i, row in df.iterrows():
        color = row['color'] if 'color' in row else "#%06x" % random.randint(0, 0xFFFFFF)
        processed.append({"name": row['team'], "lat": float(row['latitude']), "lon": float(row['longitude']), "color": color, "active": True})
    return processed

def assign_initial_territories(teams, counties_df):
    if not teams: return {}
    team_coords = np.array([[t['lat'], t['lon']] for t in teams])
    county_coords = counties_df[['lat', 'lon']].values
    tree = KDTree(team_coords)
    _, indices = tree.query(county_coords)
    return {counties_df.iloc[i]['fips']: teams[team_idx]['name'] for i, team_idx in enumerate(indices)}

def apply_history_to_state(teams, initial_counties, history):
    current_counties = initial_counties.copy()
    current_teams = [dict(t) for t in teams]
    for t in current_teams: t['active'] = True

    for battle in history:
        win = battle['winner']
        att, dfn = battle['att'], battle['def']
        loser = dfn if win == att else att
        for fips, owner in current_counties.items():
            if owner == loser:
                current_counties[fips] = win
        remaining = set(current_counties.values())
        for t in current_teams:
            t['active'] = t['name'] in remaining
    return current_counties, current_teams

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
    z_vals = [team_to_id.get(name, 0) for name in owners_list]

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
        geo=dict(scope='usa', projection_type='albers usa', showlakes=True, lakecolor='rgb(255, 255, 255)', bgcolor='rgba(0,0,0,0)')
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
                    path = next((p for p in ["nfl_teams.csv", "nfl.csv", "inputs/nfl.csv"] if os.path.exists(p)), None)
                    if path: st.session_state.teams = process_teams_df(pd.read_csv(path))
                st.session_state.adjacencies = adj_dict
                st.session_state.county_assignments = assign_initial_territories(st.session_state.teams, counties_df)
                st.session_state.battle_log = []
                st.session_state.game_active = True
                st.rerun()

    else:
        uploaded_file = st.file_uploader("📂 Load JSON Save", type=["json"])
        if uploaded_file:
            current_file_id = f"{uploaded_file.name}_{uploaded_file.size}"
            if st.session_state.last_loaded_file_id != current_file_id:
                data = json.load(uploaded_file)
                geojson, counties_df, adj_dict = load_map_resources()

                st.session_state.teams = data["teams"]
                st.session_state.battle_log = data.get("history", [])
                st.session_state.adjacencies = adj_dict

                init_counties = assign_initial_territories(data["teams"], counties_df)
                synced_counties, synced_teams = apply_history_to_state(data["teams"], init_counties, st.session_state.battle_log)

                st.session_state.county_assignments = synced_counties
                st.session_state.teams = synced_teams
                st.session_state.game_active = True
                st.session_state.last_loaded_file_id = current_file_id

                if st.session_state.battle_log:
                    st.session_state.trigger_replay = True
                st.rerun()

    if st.session_state.game_active:
        st.divider()
        save_data = {
            "teams": st.session_state.teams,
            "history": st.session_state.battle_log
        }
        st.download_button("💾 Save Progress", data=json.dumps(save_data, indent=4), file_name="madden_empire_save.json", mime="application/json")

# --- MAIN RENDER LOOP ---
if st.session_state.game_active:
    geojson, counties_df, _ = load_map_resources()
    active_teams = [t for t in st.session_state.teams if t['active']]

    col_map, col_ctrl = st.columns([2, 1])

    with col_map:
        map_placeholder = st.empty()
        if not st.session_state.is_replaying:
            map_placeholder.plotly_chart(
                render_map(geojson, st.session_state.county_assignments, st.session_state.teams),
                use_container_width=True,
                key="main_static_map"
            )

    with col_ctrl:
        st.subheader("⚔️ Battle Station")
        replay_speed = st.slider("Animation Speed", 0.5, 5.0, 1.0)

        btn_col1, btn_col2 = st.columns(2)
        watch_history = btn_col1.button("⏪ Watch History", disabled=not st.session_state.battle_log or st.session_state.is_replaying)
        stop_btn = btn_col2.button("⏹️ Stop Replay", disabled=not st.session_state.is_replaying)

        if stop_btn:
            st.session_state.stop_replay = True

        if watch_history or st.session_state.trigger_replay:
            st.session_state.trigger_replay = False
            st.session_state.stop_replay = False
            st.session_state.is_replaying = True

            replay_status = st.empty()

            # Day 0 State
            current_sim_counties = assign_initial_territories(st.session_state.teams, counties_df)
            replay_status.info("Day 0: Initial Board State")
            map_placeholder.plotly_chart(
                render_map(geojson, current_sim_counties, st.session_state.teams),
                use_container_width=True,
                key=f"replay_frame_0_{time.time()}"
            )
            time.sleep(1.0 / replay_speed)

            # Steps
            for i, battle in enumerate(st.session_state.battle_log):
                if st.session_state.stop_replay: break

                att, dfn, win = battle['att'], battle['def'], battle['winner']
                loser = dfn if win == att else att
                replay_status.markdown(f"**Day {i+1}:** {att} vs {dfn} → **{win}**")

                current_sim_counties = {f: (win if o == loser else o) for f, o in current_sim_counties.items()}

                map_placeholder.plotly_chart(
                    render_map(geojson, current_sim_counties, st.session_state.teams),
                    use_container_width=True,
                    key=f"replay_frame_{i+1}_{time.time()}"
                )
                time.sleep(1.0 / replay_speed)

            st.session_state.is_replaying = False
            st.session_state.stop_replay = False
            st.rerun()

        st.divider()
        if st.button("🎰 SPIN FOR BATTLE", use_container_width=True, disabled=st.session_state.is_replaying):
            placeholder = st.empty()
            viable_attackers = [t for t in active_teams if get_neighbors(t['name'])]

            if not viable_attackers:
                st.balloons()
                st.success(f"🏆 {active_teams[0]['name']} has conquered the world!")
            else:
                attacker = random.choice(viable_attackers)
                placeholder.markdown(f"<h2 style='text-align:center;'>⚔️ ATTACKER: {attacker['name']}</h2>", unsafe_allow_html=True)
                time.sleep(1.0)
                target = random.choice(get_neighbors(attacker['name']))
                st.session_state.current_battle = {"att": attacker['name'], "def": target}
                placeholder.markdown(f"<h2 style='text-align:center;'>🎯 MATCHUP: {attacker['name']} vs {target}</h2>", unsafe_allow_html=True)

        if 'current_battle' in st.session_state:
            b = st.session_state.current_battle
            st.markdown(f"### Match: **{b['att']}** vs **{b['def']}**")
            winner = st.radio("Select Winner", [b['att'], b['def']], horizontal=True)
            if st.button("🏆 Record Win", use_container_width=True):
                loser = b['def'] if winner == b['att'] else b['att']
                st.session_state.battle_log.append({"att": b['att'], "def": b['def'], "winner": winner})
                st.session_state.county_assignments = {f: (winner if o == loser else o) for f, o in st.session_state.county_assignments.items()}

                remaining_territory = set(st.session_state.county_assignments.values())
                for t in st.session_state.teams:
                    t['active'] = t['name'] in remaining_territory

                del st.session_state.current_battle
                st.rerun()

    with col_map:
        st.write("### Active Empires")
        legend_cols = st.columns(4)
        for i, t in enumerate(active_teams):
            legend_cols[i % 4].markdown(f"<span style='color:{t['color']};'>●</span> {t['name']}", unsafe_allow_html=True)
