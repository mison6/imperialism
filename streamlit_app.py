import streamlit as st
import pandas as pd
import numpy as np
import random
from geopy.geocoders import Nominatim
import plotly.express as px
from scipy.spatial import KDTree

# --- CONFIG & SETUP ---
st.set_page_config(page_title="Madden Imperialism", layout="wide")

# Initialize Session State for game persistence
if 'game_active' not in st.session_state:
    st.session_state.game_active = False
if 'teams' not in st.session_state:
    st.session_state.teams = [] # List of dicts: {name, address, lat, lon, color, active}
if 'county_assignments' not in st.session_state:
    st.session_state.county_assignments = {} # FIPS: Team Name

# --- DATA FETCHING ---
@st.cache_data
def load_county_data():
    """Loads US County centroids (Lat/Lon for every county)."""
    url = "https://raw.githubusercontent.com/kjhealy/us-county-nodes/master/data/county-centroids.csv"
    df = pd.read_csv(url)
    return df[['fips', 'name', 'state', 'lat', 'lng']].rename(columns={'lng': 'lon'})

@st.cache_data
def geocode_address(address):
    """Converts string address to Lat/Lon using Nominatim."""
    try:
        geolocator = Nominatim(user_agent="madden_imperialism_engine")
        location = geolocator.geocode(address)
        if location:
            return location.latitude, location.longitude
    except Exception:
        pass
    return None, None

def get_random_color():
    return f"rgb({random.randint(50, 255)}, {random.randint(50, 255)}, {random.randint(50, 255)})"

# --- GAME LOGIC ---
def assign_initial_territories(teams, counties):
    """Voronoi-style assignment: every county belongs to the closest team."""
    team_coords = np.array([[t['lat'], t['lon']] for t in teams])
    county_coords = counties[['lat', 'lon']].values

    # KDTree allows for near-instant nearest-neighbor lookups
    tree = KDTree(team_coords)
    _, indices = tree.query(county_coords)

    assignments = {}
    for i, team_idx in enumerate(indices):
        fips = str(counties.iloc[i]['fips']).zfill(5)
        assignments[fips] = teams[team_idx]['name']
    return assignments

def find_defender(attacker_name, direction, teams_dict, counties, assignments):
    """Calculates the defender based on an attack vector from the attacker's city."""
    attacker = teams_dict[attacker_name]

    # Direction vectors (lat, lon)
    vectors = {
        "North": (2, 0), "South": (-2, 0), "East": (0, 2), "West": (0, -2),
        "NE": (1.5, 1.5), "NW": (1.5, -1.5), "SE": (-1.5, 1.5), "SW": (-1.5, -1.5)
    }
    dy, dx = vectors[direction]

    # We look for a county center in that general direction
    target_lat = attacker['lat'] + dy
    target_lon = attacker['lon'] + dx

    county_coords = counties[['lat', 'lon']].values
    tree = KDTree(county_coords)
    _, idx = tree.query([target_lat, target_lon])

    target_fips = str(counties.iloc[idx]['fips']).zfill(5)
    defender_name = assignments.get(target_fips)

    # Handle edge case where it targets its own land
    if defender_name == attacker_name:
        others = [t['name'] for t in st.session_state.teams if t['active'] and t['name'] != attacker_name]
        return random.choice(others) if others else "No Neighbors"

    return defender_name

# --- UI ---
st.title("🏈 Madden Imperialism Engine")
st.write("Determine your matchups, play your games, and conquer the map.")

with st.sidebar:
    st.header("Team Entry")
    team_list_raw = st.text_area("Teams (Name, Address)",
                                "Chicago Bears, Soldier Field, Chicago\nGreen Bay Packers, Lambeau Field, Green Bay\nDetroit Lions, Ford Field, Detroit",
                                help="One team per line: Name, Address")

    if st.button("Generate Map"):
        counties = load_county_data()
        new_teams = []
        for line in team_list_raw.split('\n'):
            if ',' in line:
                name, addr = line.split(',', 1)
                lat, lon = geocode_address(addr.strip())
                if lat:
                    new_teams.append({
                        "name": name.strip(), "lat": lat, "lon": lon,
                        "color": get_random_color(), "active": True
                    })

        if new_teams:
            st.session_state.teams = new_teams
            st.session_state.county_assignments = assign_initial_territories(new_teams, counties)
            st.session_state.game_active = True
            st.rerun()

if st.session_state.game_active:
    counties = load_county_data()
    teams_dict = {t['name']: t for t in st.session_state.teams}
    active_teams = [t for t in st.session_state.teams if t['active']]

    col1, col2 = st.columns([2, 1])

    with col2:
        st.subheader("The Spinners")
        if st.button("SPIN!", use_container_width=True):
            attacker = random.choice(active_teams)
            direction = random.choice(["North", "South", "East", "West", "NE", "NW", "SE", "SW"])
            defender = find_defender(attacker['name'], direction, teams_dict, counties, st.session_state.county_assignments)

            st.session_state.current_battle = {
                "attacker": attacker['name'],
                "defender": defender,
                "direction": direction
            }

        if 'current_battle' in st.session_state:
            b = st.session_state.current_battle
            st.info(f"**Attacker:** {b['attacker']} (Moving {b['direction']})")
            st.warning(f"**Defender:** {b['defender']}")

            winner = st.selectbox("Who won the game?", [b['attacker'], b['defender']])
            if st.button("Update Empire"):
                loser = b['defender'] if winner == b['attacker'] else b['attacker']

                # Update assignments
                new_map = st.session_state.county_assignments.copy()
                for fips, owner in new_map.items():
                    if owner == loser:
                        new_map[fips] = winner
                st.session_state.county_assignments = new_map

                # Deactivate loser
                for t in st.session_state.teams:
                    if t['name'] == loser: t['active'] = False

                del st.session_state.current_battle
                st.rerun()

    with col1:
        # Prepare data for map
        map_df = counties.copy()
        map_df['fips_str'] = map_df['fips'].apply(lambda x: str(x).zfill(5))
        map_df['Owner'] = map_df['fips_str'].map(st.session_state.county_assignments)

        # Plot using Plotly Scatter Mapbox (Centroids)
        fig = px.scatter_mapbox(
            map_df, lat="lat", lon="lon", color="Owner",
            color_discrete_map={t['name']: t['color'] for t in st.session_state.teams},
            hover_name="name", zoom=3, height=600
        )
        fig.update_layout(mapbox_style="carto-positron", margin={"r":0,"t":0,"l":0,"b":0})
        st.plotly_chart(fig, use_container_width=True)

else:
    st.info("Please enter your teams and addresses in the sidebar to initialize the map.")
