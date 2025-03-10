import datetime as dt  # Import datetime for handling date and time
import json  # Import json for handling JSON data
import time  # Import time for time-related functions
import urllib.error
import urllib.request

import folium  # Import folium for creating interactive maps
import pandas as pd  # Import pandas for data manipulation
import requests  # Import requests for making HTTP requests
import streamlit as st  # Import Streamlit for creating web apps
from streamlit_folium import (
    st_folium,  # Import st_folium to render Folium maps in Streamlit
)

from helpers import *  # Import custom helper functions

# Configure page and handle errors gracefully
try:
    st.set_page_config(
        page_title="Toronto Bike Share Status",
        page_icon="🚲",
        layout="wide",
        initial_sidebar_state="expanded",
    )
except Exception as e:
    st.error(f"Error configuring page: {str(e)}")


# Initialize session state with defaults
def init_session_state():
    defaults = {
        "bike_method": "Rent",
        "input_bike_modes": [],
        "findmeabike": False,
        "findmeadock": False,
        "iamhere": None,
        "iamhere_return": None,
        "data": None,
        "error": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_session_state()

# API URLs
STATION_URL = "https://tor.publicbikesystem.net/ube/gbfs/v1/en/station_status.json"
LATLON_URL = "https://tor.publicbikesystem.net/ube/gbfs/v1/en/station_information"


# Fetch data with robust error handling
@st.cache_data(ttl=60)
def get_data():
    try:
        data_df = query_station_status(STATION_URL)
        if data_df is None:
            raise Exception("Failed to fetch station status data")

        latlon_df = get_station_latlon(LATLON_URL)
        if latlon_df is None:
            raise Exception("Failed to fetch station location data")

        data = join_latlon(data_df, latlon_df)
        if data is None or data.empty:
            raise Exception("Failed to join station data")

        return data
    except Exception as e:
        st.session_state.error = f"Data fetch error: {str(e)}"
        return None


# Main app layout
def main():
    st.title("Toronto Bike Share Station Status")
    st.markdown(
        "This dashboard tracks bike availability at each bike share station in Toronto."
    )

    # Fetch data
    data = get_data()
    if data is None:
        st.error(
            st.session_state.error
            or "Unable to fetch bike share data. Please try again later."
        )
        return

    # Display metrics
    try:
        display_metrics(data)
    except Exception as e:
        st.error(f"Error displaying metrics: {str(e)}")

    # Sidebar inputs
    try:
        handle_sidebar_inputs(data)
    except Exception as e:
        st.error(f"Error processing inputs: {str(e)}")

    # Display maps
    try:
        display_maps(data)
    except Exception as e:
        st.error(f"Error displaying maps: {str(e)}")


def display_metrics(data):
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Bikes Available Now", value=int(sum(data["num_bikes_available"])))
        st.metric("E-Bikes Available Now", value=int(sum(data["ebike"])))
    with col2:
        st.metric(
            "Stations w Available Bikes",
            value=int(len(data[data["num_bikes_available"] > 0])),
        )
        st.metric(
            "Stations w Available E-Bikes", value=int(len(data[data["ebike"] > 0]))
        )
    with col3:
        st.metric(
            "Stations w Empty Docks",
            value=int(len(data[data["num_docks_available"] > 0])),
        )


def handle_sidebar_inputs(data):
    with st.sidebar:
        st.session_state.bike_method = st.selectbox(
            "Are you looking to rent or return a bike?",
            ("Rent", "Return"),
            key="bike_method_select",
        )

        if st.session_state.bike_method == "Rent":
            handle_rent_inputs()
        else:
            handle_return_inputs()

        if st.button("Reset"):
            reset_session_state()


def handle_rent_inputs():
    st.session_state.input_bike_modes = st.multiselect(
        "What kind of bikes are you looking to rent?", ["ebike", "mechanical"]
    )

    st.subheader("Where are you located?")
    col1, col2 = st.columns(2)
    with col1:
        input_street = st.text_input("Street", key="rent_street")
        input_city = st.text_input("City", "Toronto", key="rent_city")
    with col2:
        input_country = st.text_input("Country", "Canada", key="rent_country")

    if st.button("Find me a bike!", type="primary"):
        process_rent_request(input_street, input_city, input_country)


def handle_return_inputs():
    st.subheader("Where are you located?")
    col1, col2 = st.columns(2)
    with col1:
        input_street = st.text_input("Street", key="return_street")
        input_city = st.text_input("City", "Toronto", key="return_city")
    with col2:
        input_country = st.text_input("Country", "Canada", key="return_country")

    if st.button("Find me a dock!", type="primary"):
        process_return_request(input_street, input_city, input_country)


def process_rent_request(street, city, country):
    if not street.strip():
        st.error("Please enter your street address.")
        return

    with st.spinner("Finding the nearest available bike..."):
        try:
            location = geocode(f"{street} {city} {country}")
            if not location:
                st.error("Could not find this address. Please check your input.")
                return
            st.session_state.iamhere = location
            st.session_state.findmeabike = True
        except Exception as e:
            st.error(f"Error processing location: {str(e)}")


def process_return_request(street, city, country):
    if not street.strip():
        st.error("Please enter your street address.")
        return

    with st.spinner("Finding the nearest available dock..."):
        try:
            location = geocode(f"{street} {city} {country}")
            if not location:
                st.error("Could not find this address. Please check your input.")
                return
            st.session_state.iamhere_return = location
            st.session_state.findmeadock = True
        except Exception as e:
            st.error(f"Error processing location: {str(e)}")


def display_maps(data):
    if st.session_state.bike_method == "Rent":
        display_rent_map(data)
    else:
        display_return_map(data)


def display_rent_map(data):
    try:
        if st.session_state.findmeabike and st.session_state.iamhere:
            display_route_map(
                data,
                st.session_state.iamhere,
                st.session_state.input_bike_modes,
                is_return=False,
            )
        else:
            display_initial_map(data, "rent")
    except Exception as e:
        st.error(f"Error displaying rent map: {str(e)}")


def display_return_map(data):
    try:
        if st.session_state.findmeadock and st.session_state.iamhere_return:
            display_route_map(
                data, st.session_state.iamhere_return, None, is_return=True
            )
        else:
            display_initial_map(data, "return")
    except Exception as e:
        st.error(f"Error displaying return map: {str(e)}")


def display_initial_map(data, map_type):
    center = [43.65306613746548, -79.38815311015]
    m = folium.Map(location=center, zoom_start=13, tiles="cartodbpositron")

    for _, row in data.iterrows():
        marker_color = get_marker_color(row["num_bikes_available"])
        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=2,
            color=marker_color,
            fill=True,
            fill_color=marker_color,
            fill_opacity=0.7,
            popup=create_popup_html(row),
        ).add_to(m)

    st_folium(m, key=f"initial_{map_type}_map", width=800, height=600)


def display_route_map(data, location, bike_modes=None, is_return=False):
    try:
        if is_return:
            chosen_station = get_dock_availability(location, data)
        else:
            chosen_station = get_bike_availability(location, data, bike_modes or [])

        if not chosen_station:
            st.error("No available stations found nearby.")
            return

        m = create_route_map(data, location, chosen_station, is_return)
        st_folium(
            m,
            key=f"route_{'return' if is_return else 'rent'}_map",
            width=800,
            height=600,
        )

    except Exception as e:
        st.error(f"Error creating route map: {str(e)}")


def create_route_map(data, location, chosen_station, is_return):
    m = folium.Map(location=location, zoom_start=16, tiles="cartodbpositron")

    # Add station markers
    for _, row in data.iterrows():
        marker_color = get_marker_color(row["num_bikes_available"])
        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=2,
            color=marker_color,
            fill=True,
            fill_color=marker_color,
            fill_opacity=0.7,
            popup=create_popup_html(row),
        ).add_to(m)

    # Add user location marker
    folium.Marker(
        location=location,
        popup="You are here",
        icon=folium.Icon(color="blue", icon="info-sign"),
    ).add_to(m)

    # Add chosen station marker
    folium.Marker(
        location=(chosen_station[1], chosen_station[2]),
        popup="Return here" if is_return else "Rent here",
        icon=folium.Icon(color="red", icon="info-sign"),
    ).add_to(m)

    # Add route
    try:
        coordinates, duration = run_osrm(chosen_station, location)
        folium.PolyLine(
            locations=coordinates, weight=2, color="blue", opacity=0.8
        ).add_to(m)

        # Display duration
        col1, col2, col3 = st.columns(3)
        with col3:
            st.metric(":green[Travel Time (min)]", f"{duration:.1f}")

    except Exception as e:
        st.warning(f"Could not calculate route: {str(e)}")

    return m


def create_popup_html(row):
    return folium.Popup(
        f"Station ID: {row['station_id']}<br>"
        f"Total Bikes Available: {row['num_bikes_available']}<br>"
        f"Mechanical Bikes: {row['mechanical']}<br>"
        f"E-Bikes: {row['ebike']}<br>"
        f"Docks Available: {row['num_docks_available']}",
        max_width=300,
    )


def reset_session_state():
    st.session_state.findmeabike = False
    st.session_state.findmeadock = False
    st.session_state.iamhere = None
    st.session_state.iamhere_return = None
    st.session_state.input_bike_modes = []
    st.experimental_rerun()


if __name__ == "__main__":
    main()
