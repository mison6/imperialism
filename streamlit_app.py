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
    .replay-header {
        background-color: #1e1e1e;
        color: white;
        padding: 20px;
        border-radius: 12px;
        text-align: center;
        margin-bottom: 20px;
        border: 2px solid #444;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
    }
    .vs-badge {
        font-weight: bold;
        padding: 6px 12px;
        border-radius: 6px;
        display: inline-block;
        margin: 0 10px;
        border: 1px solid rgba(255,255,255,0.2);
    }
    .winner-text {
        color: #4CAF50;
        font-weight: bold;
        text-transform: uppercase;
        letter-spacing: 1px;
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

def render_map(geojson, county_assignments, teams_list, highlight_teams=None):
    team_to_id = {t['name']: i for i, t in enumerate(teams_list)}
    fips_list = list(county_assignments.keys())
    owners_list = list(county_assignments.values())

    text_list = []
    for owner in owners_list:
        if highlight_teams:
            text_list.append(owner if owner in highlight_teams else "")
        else:
            text_list.append(owner)

    z_vals = [team_to_id.get(name, 0) for name in owners_list]

    colorscale = []
    for i, t in enumerate(teams_list):
        scale_val = i / (max(1, len(teams_list) - 1))
        color = t['color']
        # If we are in highlight mode, turn everyone else into a ghost gray
        if highlight_teams and t['name'] not in highlight_teams:
            color = 'rgba(100, 100, 100, 0.08)'
        colorscale.append([scale_val, color])

    fig = go.Figure(go.Choropleth(
        geojson=geojson,
        locations=fips_list,
        z=z_vals,
        colorscale=colorscale,
        showscale=False,
        marker_line_width=0,
        text=text_list,
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
    mode = st.radio("Select Action", ["New Game", "Load Session"], key="action_mode")

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
        uploaded_file = st.file_uploader("📂 Load JSON Save", type=["json"], key="session_loader")
        if uploaded_file and not st.session_state.game_active:
            data = json.load(uploaded_file)
            geojson, counties_df, adj_dict = load_map_resources()
            st.session_state.teams = data["teams"]
            st.session_state.battle_log = data.get("history", [])
            st.session_state.adjacencies = adj_dict
            # Initial state setup
            init_counties = assign_initial_territories(data["teams"], counties_df)
            synced_counties, synced_teams = apply_history_to_state(data["teams"], init_counties, st.session_state.battle_log)
            # We don't set county_assignments yet because we want the replay to start from Day 0
            st.session_state.county_assignments = synced_counties
            st.session_state.teams = synced_teams
            st.session_state.game_active = True
            st.session_state.trigger_replay = True
            st.rerun()

# --- MAIN INTERFACE ---
if st.session_state.game_active:
    geojson, counties_df, _ = load_map_resources()
    active_teams = [t for t in st.session_state.teams if t['active']]

    col_map, col_ctrl = st.columns([2.5, 1])

    with col_map:
        header_placeholder = st.empty()
        map_placeholder = st.empty()

        # Static view when not replaying
        if not st.session_state.is_replaying:
            header_placeholder.markdown("<div style='height: 40px;'></div>", unsafe_allow_html=True)
            map_placeholder.plotly_chart(
                render_map(geojson, st.session_state.county_assignments, st.session_state.teams),
                use_container_width=True, key="static_map"
            )

    with col_ctrl:
        st.subheader("⚔️ Battle Station")
        replay_speed = st.slider("Playback Speed", 0.5, 5.0, 1.2)

        c1, c2 = st.columns(2)
        watch_history = c1.button("⏪ Replay", disabled=not st.session_state.battle_log or st.session_state.is_replaying)
        if c2.button("⏹️ Stop", disabled=not st.session_state.is_replaying):
            st.session_state.stop_replay = True

        # Replay Animation Sequence
        if watch_history or st.session_state.trigger_replay:
            st.session_state.trigger_replay = False
            st.session_state.is_replaying = True
            st.session_state.stop_replay = False

            # Step 0: Day 0
            current_sim_counties = assign_initial_territories(st.session_state.teams, counties_df)
            header_placeholder.markdown("<div class='replay-header'><h2>Day 0: Initial Borders</h2></div>", unsafe_allow_html=True)
            map_placeholder.plotly_chart(render_map(geojson, current_sim_counties, st.session_state.teams), use_container_width=True, key="frame_0")
            time.sleep(2.0 / replay_speed)

            for i, battle in enumerate(st.session_state.battle_log):
                if st.session_state.stop_replay: break

                att, dfn, win = battle['att'], battle['def'], battle['winner']
                loser = dfn if win == att else att
                att_c = next((t['color'] for t in st.session_state.teams if t['name'] == att), "#666")
                dfn_c = next((t['color'] for t in st.session_state.teams if t['name'] == dfn), "#666")

                header_html = f"""
                    <div class='replay-header'>
                        <div style='font-size: 0.9em; opacity: 0.7;'>BATTLE {i+1}</div>
                        <div style='margin: 10px 0;'>
                            <span class='vs-badge' style='background:{att_c};'>{att}</span>
                            <b>VS</b>
                            <span class='vs-badge' style='background:{dfn_c};'>{dfn}</span>
                        </div>
                        <div class='winner-text'>Result: {win} Wins</div>
                    </div>
                """
                header_placeholder.markdown(header_html, unsafe_allow_html=True)

                # STAGE 1: HIGHLIGHT (Everything else grays out)
                map_placeholder.plotly_chart(
                    render_map(geojson, current_sim_counties, st.session_state.teams, highlight_teams=[att, dfn]),
                    use_container_width=True, key=f"highlight_{i}"
                )
                time.sleep(1.5 / replay_speed)

                # STAGE 2: ABSORB (Loser changes color while highlighted)
                current_sim_counties = {f: (win if o == loser else o) for f, o in current_sim_counties.items()}
                map_placeholder.plotly_chart(
                    render_map(geojson, current_sim_counties, st.session_state.teams, highlight_teams=[att, dfn]),
                    use_container_width=True, key=f"absorb_{i}"
                )
                time.sleep(1.0 / replay_speed)

                # STAGE 3: RESUME (Show full map colors again)
                map_placeholder.plotly_chart(
                    render_map(geojson, current_sim_counties, st.session_state.teams),
                    use_container_width=True, key=f"resume_{i}"
                )
                time.sleep(1.0 / replay_speed)

            st.session_state.is_replaying = False
            st.rerun()

        st.divider()
        if st.button("🎰 SPIN FOR BATTLE", use_container_width=True, disabled=st.session_state.is_replaying):
            viable = [t for t in active_teams if get_neighbors(t['name'])]
            if not viable:
                st.balloons()
                st.success(f"🏆 {active_teams[0]['name']} Wins!")
            else:
                attacker = random.choice(viable)
                target = random.choice(get_neighbors(attacker['name']))
                st.session_state.current_battle = {"att": attacker['name'], "def": target}

        if 'current_battle' in st.session_state:
            b = st.session_state.current_battle
            st.info(f"Battle: **{b['att']}** vs **{b['def']}**")
            winner = st.selectbox("Who Won?", [b['att'], b['def']])
            if st.button("Confirm Result"):
                loser = b['def'] if winner == b['att'] else b['att']
                st.session_state.battle_log.append({"att": b['att'], "def": b['def'], "winner": winner})
                st.session_state.county_assignments = {f: (winner if o == loser else o) for f, o in st.session_state.county_assignments.items()}
                for t in st.session_state.teams:
                    t['active'] = t['name'] in set(st.session_state.county_assignments.values())
                del st.session_state.current_battle
                st.rerun()

    st.write("### 🚩 Empire Legend")
    lcols = st.columns(6)
    for idx, t in enumerate(active_teams):
        lcols[idx % 6].markdown(f"<span style='color:{t['color']};'>●</span> {t['name']}", unsafe_allow_html=True)
