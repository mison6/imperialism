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

# --- 1. CRITICAL: PRE-FLIGHT DATA RECOVERY (Anti-Flicker Fix) ---
# Check for existing game state BEFORE any UI logic runs to prevent the "No Game Found" flicker.
AUTOSAVE_FILE = ".imperialism_autosave.json"

def load_autosave_silent():
    if os.path.exists(AUTOSAVE_FILE):
        try:
            with open(AUTOSAVE_FILE, "r") as f:
                data = json.load(f)
                for k, v in data.items():
                    if k not in st.session_state:
                        st.session_state[k] = v
        except:
            pass

load_autosave_silent()

# --- CONFIG & SETUP ---
st.set_page_config(page_title="Madden Imperialism Engine", layout="wide")

# CSS for layout stability and polish
st.markdown("""
    <style>
    .reportview-container .main .block-container { padding-top: 1rem; }

    .header-container {
        height: 150px;
        margin-bottom: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .replay-header {
        background-color: #1e1e1e;
        color: white;
        padding: 15px;
        border-radius: 12px;
        text-align: center;
        width: 100%;
        border: 2px solid #444;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
    }

    .vs-badge {
        font-weight: bold;
        padding: 4px 12px;
        border-radius: 6px;
        display: inline-block;
        margin: 0 8px;
        border: 1px solid rgba(255,255,255,0.2);
        color: white;
    }

    .winner-text {
        color: #4CAF50;
        font-weight: bold;
        text-transform: uppercase;
        font-size: 0.9em;
        margin-top: 5px;
    }

    .spinning-text {
        color: #ffcc00;
        font-style: italic;
        animation: blinker 0.2s linear infinite;
    }

    @keyframes blinker {
        50% { opacity: 0; }
    }
    </style>
    """, unsafe_allow_html=True)

# --- CONSTANTS ---
COUNTY_GEOJSON_URL = "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"
CENSUS_CENTER_URL = "https://www2.census.gov/geo/docs/reference/cenpop2020/county/CenPop2020_Mean_CO.txt"
ADJACENCY_URL = "https://www2.census.gov/geo/docs/reference/county_adjacency.txt"

# --- STATE INITIALIZATION ---
def init_state():
    defaults = {
        'game_active': False,
        'teams': [],
        'county_assignments': {},
        'adjacencies': {},
        'battle_log': [],
        'is_replaying': False,
        'trigger_replay': False,
        'last_header_content': "<div class='replay-header'><h2>Welcome to Imperialism</h2></div>"
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

init_state()

# --- HELPER FUNCTIONS ---
def save_game_state():
    """Serializes current state to a local JSON file."""
    state = {
        "teams": st.session_state.teams,
        "county_assignments": st.session_state.county_assignments,
        "battle_log": st.session_state.battle_log,
        "last_header_content": st.session_state.last_header_content,
        "game_active": st.session_state.game_active
    }
    with open(AUTOSAVE_FILE, "w") as f:
        json.dump(state, f)

@st.cache_data
def load_map_resources():
    try:
        req = Request(COUNTY_GEOJSON_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urlopen(req) as response:
            geojson = json.load(response)

        df = pd.read_csv(CENSUS_CENTER_URL, dtype={'STATEFP': str, 'COUNTYFP': str})
        df['fips'] = df['STATEFP'].str.zfill(2) + df['COUNTYFP'].str.zfill(3)
        counties_df = df[['fips', 'COUNAME', 'LATITUDE', 'LONGITUDE']].rename(columns={'LATITUDE':'lat', 'LONGITUDE':'lon', 'COUNAME':'name'})

        adj_dict = {}
        response = urlopen(ADJACENCY_URL)
        current_county = None
        for line in response:
            line_str = line.decode('latin-1').strip()
            if not line_str: continue
            parts = line_str.split('\t')
            if len(parts) >= 4:
                if parts[1].strip():
                    current_county = parts[1].strip().zfill(5)
                    if current_county not in adj_dict: adj_dict[current_county] = []
                neighbor_fips = parts[3].strip().zfill(5)
                if current_county and neighbor_fips != current_county:
                    adj_dict[current_county].append(neighbor_fips)
        return geojson, counties_df.dropna(), adj_dict
    except Exception as e:
        st.error(f"Failed to load resources: {e}")
        return None, None, None

def assign_initial_territories(teams, counties_df):
    if not teams: return {}
    team_coords = np.array([[t['lat'], t['lon']] for t in teams])
    county_coords = counties_df[['lat', 'lon']].values
    tree = KDTree(team_coords)
    _, indices = tree.query(county_coords)
    return {counties_df.iloc[i]['fips']: teams[team_idx]['name'] for i, team_idx in enumerate(indices)}

def hex_to_rgba(hex_color, alpha):
    hex_color = hex_color.lstrip('#')
    lv = len(hex_color)
    rgb = tuple(int(hex_color[i:i + lv // 3], 16) for i in range(0, lv, lv // 3))
    return f'rgba({rgb[0]}, {rgb[1]}, {rgb[2]}, {alpha})'

def render_map(geojson, county_assignments, teams_list, highlight_teams=None):
    team_to_id = {t['name']: i for i, t in enumerate(teams_list)}
    fips_list = list(county_assignments.keys())
    owners_list = list(county_assignments.values())

    z_vals = [team_to_id.get(name, 0) for name in owners_list]

    colorscale = []
    for i, t in enumerate(teams_list):
        scale_val = i / (max(1, len(teams_list) - 1)) if len(teams_list) > 1 else 0
        base_color = t['color']

        if highlight_teams:
            if t['name'] in highlight_teams:
                color = hex_to_rgba(base_color, 1.0)
            else:
                color = hex_to_rgba(base_color, 0.15)
        else:
            color = hex_to_rgba(base_color, 1.0)

        colorscale.append([scale_val, color])

    fig = go.Figure(go.Choropleth(
        geojson=geojson,
        locations=fips_list,
        z=z_vals,
        colorscale=colorscale,
        showscale=False,
        marker_line_width=0,
        text=owners_list,
        hoverinfo="text"
    ))

    fig.update_layout(
        margin={"r":0,"t":0,"l":0,"b":0},
        height=650,
        uirevision='constant',
        geo=dict(
            scope='usa',
            projection_type='albers usa',
            showlakes=False,
            bgcolor='rgba(0,0,0,0)'
        )
    )
    return fig

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

def format_battle_header(att, dfn, winner=None, label="BATTLE", spinning=False, spin_target="ALL"):
    att_c = next((t['color'] for t in st.session_state.teams if t['name'] == att), "#555")
    dfn_c = next((t['color'] for t in st.session_state.teams if t['name'] == dfn), "#555")

    if spinning:
        if spin_target == "ATTACKER":
            status_html = "<div class='spinning-text'>🎰 SELECTING ATTACKER...</div>"
        elif spin_target == "DEFENDER":
            status_html = "<div class='spinning-text'>🎰 SELECTING DEFENDER...</div>"
        else:
            status_html = "<div class='spinning-text'>🎰 SPINNING...</div>"
    elif winner:
        status_html = f"<div class='winner-text'>WINNER: {winner}</div>"
    else:
        status_html = "<div class='winner-text' style='color:#aaa'>Waiting for result...</div>"

    return f"""
        <div class='replay-header'>
            <div style='font-size: 0.8em; opacity: 0.6; letter-spacing: 2px;'>{label}</div>
            <div style='margin-top: 5px;'>
                <span class='vs-badge' style='background:{att_c};'>{att}</span>
                <b style='font-size: 1.2em;'>vs</b>
                <span class='vs-badge' style='background:{dfn_c};'>{dfn}</span>
            </div>
            {status_html}
        </div>
    """

# --- AUTO-LOAD ON STARTUP ---
geojson, counties_df, adj_dict = load_map_resources()
if adj_dict:
    st.session_state.adjacencies = adj_dict

# Check for active battle in the history log
active_battle = None
if st.session_state.battle_log and st.session_state.battle_log[-1].get('winner') is None:
    active_battle = st.session_state.battle_log[-1]

# Ensure header content matches current state (especially for pending matchups)
if active_battle and not st.session_state.is_replaying:
    st.session_state.last_header_content = format_battle_header(active_battle['att'], active_battle['def'])

# --- MAIN INTERFACE ---
with st.sidebar:
    st.header("⚙️ Game Controls")
    if st.session_state.game_active:
        save_data = {
            "teams": st.session_state.teams,
            "history": st.session_state.battle_log
        }
        st.download_button(
            "💾 Save Map",
            data=json.dumps(save_data, indent=2),
            file_name="madden_imperialism_save.json",
            mime="application/json",
            use_container_width=True
        )

        # Reset Button logic
        if st.button("🗑️ Clear Cache & Reset", use_container_width=True):
            if os.path.exists(AUTOSAVE_FILE):
                os.remove(AUTOSAVE_FILE)
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

# PERSISTENT SETUP CONTAINER
setup_ui_container = st.empty()

if not st.session_state.game_active:
    with setup_ui_container.container():
        st.title("🏟️ Madden Imperialism Engine")
        st.info("No active game found. Start a new one or upload a save.")

        uploaded_file = st.file_uploader("📂 Upload Save File", type=["json"])
        if uploaded_file:
            data = json.load(uploaded_file)
            st.session_state.teams = data["teams"]
            st.session_state.battle_log = data.get("history", [])
            st.session_state.county_assignments = assign_initial_territories(st.session_state.teams, counties_df)
            st.session_state.trigger_replay = True
            st.session_state.game_active = True
            setup_ui_container.empty() # CLEAR THE BLOCK
            save_game_state()
            st.rerun()

        st.markdown("---")
        possible_paths = ["nfl_teams.csv", "inputs/nfl_teams.csv", "nfl.csv", "inputs/nfl.csv"]
        valid_path = next((p for p in possible_paths if os.path.exists(p)), None)

        if valid_path:
            st.success(f"Default team list found: `{valid_path}`")
        else:
            st.warning("No default team CSV found. Please ensure `nfl_teams.csv` exists in the root or `inputs/` folder.")

        if st.button("🚀 Start New NFL Imperialism", disabled=(valid_path is None)):
            new_teams = [
                {"name": r['Team'], "lat": r['Latitude'], "lon": r['Longitude'], "color": r.get('Color', "#%06x" % random.randint(0, 0xFFFFFF)), "active": True}
                for _, r in pd.read_csv(valid_path).iterrows()
            ]
            st.session_state.teams = new_teams
            st.session_state.county_assignments = assign_initial_territories(new_teams, counties_df)
            st.session_state.battle_log = []
            st.session_state.last_header_content = "<div class='replay-header'><h2>Initial Territories</h2></div>"
            st.session_state.game_active = True
            st.session_state.trigger_replay = False
            st.session_state.is_replaying = False
            setup_ui_container.empty() # CLEAR THE BLOCK

            save_game_state()
            st.rerun()

if st.session_state.game_active:
    setup_ui_container.empty() # Keep it cleared when game is active

    active_teams = [t for t in st.session_state.teams if t['active']]
    col_map, col_ctrl = st.columns([2.5, 1])

    with col_map:
        header_placeholder = st.empty()
        map_placeholder = st.empty()

        if not st.session_state.is_replaying:
            header_placeholder.markdown(f"<div class='header-container'>{st.session_state.last_header_content}</div>", unsafe_allow_html=True)
            current_highlight = [active_battle['att'], active_battle['def']] if active_battle else None
            map_placeholder.plotly_chart(
                render_map(geojson, st.session_state.county_assignments, st.session_state.teams, highlight_teams=current_highlight),
                use_container_width=True, key="main_map", config={'displayModeBar': False}
            )

    with col_ctrl:
        st.subheader("⚔️ Actions")

        if st.button("⏪ Replay All Battles", disabled=st.session_state.is_replaying) or st.session_state.trigger_replay:
            st.session_state.trigger_replay = False
            st.session_state.is_replaying = True
            cur_map = assign_initial_territories(st.session_state.teams, counties_df)

            # SHOW INITIAL STATE
            header_placeholder.markdown("<div class='header-container'><div class='replay-header'><h2>Initial Territories</h2></div></div>", unsafe_allow_html=True)
            map_placeholder.plotly_chart(render_map(geojson, cur_map, st.session_state.teams), use_container_width=True, key="replay_start")
            time.sleep(2.0)

            completed_battles = [b for b in st.session_state.battle_log if b.get('winner')]
            for i, battle in enumerate(completed_battles):
                att, dfn, win = battle['att'], battle['def'], battle['winner']
                loser = dfn if win == att else att

                # --- STEP 1: MATCHUP PHASE ---
                # 1. Pre-calculate the figure so it's ready for immediate transmission
                matchup_fig = render_map(geojson, cur_map, st.session_state.teams, [att, dfn])
                current_header = format_battle_header(att, dfn, label=f'BATTLE {i+1}')

                # 2. Update Map FIRST (since it's the slower element to render)
                map_placeholder.plotly_chart(matchup_fig, use_container_width=True, key=f"replay_m_{i}", config={'displayModeBar': False})
                # 3. Update Header IMMEDIATELY after
                header_placeholder.markdown(f"<div class='header-container'>{current_header}</div>", unsafe_allow_html=True)

                time.sleep(1.2)

                # --- STEP 2: WINNER PHASE ---
                # 1. Calculate next state
                cur_map = {f: (win if o == loser else o) for f, o in cur_map.items()}
                winner_fig = render_map(geojson, cur_map, st.session_state.teams, [att, dfn])
                winner_header = format_battle_header(att, dfn, win, label=f'BATTLE {i+1}')

                # 2. Update Map FIRST
                map_placeholder.plotly_chart(winner_fig, use_container_width=True, key=f"replay_w_{i}", config={'displayModeBar': False})
                # 3. Update Header IMMEDIATELY after
                header_placeholder.markdown(f"<div class='header-container'>{winner_header}</div>", unsafe_allow_html=True)

                if i == len(completed_battles) - 1:
                    st.session_state.last_header_content = winner_header

                time.sleep(1.0)

            st.session_state.county_assignments = cur_map
            st.session_state.is_replaying = False
            save_game_state()
            st.rerun()

        st.divider()

        # --- BATTLE INTERFACE ---
        if active_battle:
            st.markdown(f"**Current Matchup:** {active_battle['att']} vs {active_battle['def']}")
            winner = st.selectbox("Select Winner", [active_battle['att'], active_battle['def']])
            if st.button("Confirm Result", use_container_width=True):
                st.session_state.battle_log[-1]['winner'] = winner
                loser = active_battle['def'] if winner == active_battle['att'] else active_battle['att']

                st.session_state.county_assignments = {f: (winner if o == loser else o) for f, o in st.session_state.county_assignments.items()}
                for t in st.session_state.teams:
                    t['active'] = t['name'] in set(st.session_state.county_assignments.values())

                st.session_state.last_header_content = format_battle_header(active_battle['att'], active_battle['def'], winner)
                save_game_state()
                st.rerun()
        else:
            if st.button("🎰 SPIN FOR NEXT BATTLE", use_container_width=True, type="primary", disabled=st.session_state.is_replaying):
                viable_attackers = [t for t in active_teams if get_neighbors(t['name'])]
                if viable_attackers:
                    for i in range(12):
                        temp_att = random.choice(viable_attackers)
                        header_placeholder.markdown(f"<div class='header-container'>{format_battle_header(temp_att['name'], '?', spinning=True, spin_target='ATTACKER')}</div>", unsafe_allow_html=True)
                        time.sleep(0.1)

                    final_attacker = random.choice(viable_attackers)['name']
                    valid_neighbors = get_neighbors(final_attacker)

                    for i in range(10):
                        temp_dfn = random.choice(valid_neighbors)
                        header_placeholder.markdown(f"<div class='header-container'>{format_battle_header(final_attacker, temp_dfn, spinning=True, spin_target='DEFENDER')}</div>", unsafe_allow_html=True)
                        time.sleep(0.1)

                    final_defender = random.choice(valid_neighbors)

                    st.session_state.battle_log.append({"att": final_attacker, "def": final_defender, "winner": None})
                    st.session_state.last_header_content = format_battle_header(final_attacker, final_defender)
                    save_game_state()
                    st.rerun()

    # Footer
    st.markdown("---")
    st.caption(f"Unlocking potential once the sludge/friction/sand in the gears is removed. | Active: {len(active_teams)} teams")
