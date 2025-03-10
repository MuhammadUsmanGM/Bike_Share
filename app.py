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

# Configure Streamlit page
st.set_page_config(
    page_title="Toronto Bike Share Status",
    page_icon="🚲",
    layout="wide",
    initial_sidebar_state="expanded",
)


# Error handling decorator for API calls
def handle_api_error(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (urllib.error.URLError, requests.RequestException) as e:
            st.error(f"Error fetching data: {str(e)}. Please try again later.")
            return None
        except Exception as e:
            st.error(f"An unexpected error occurred: {str(e)}. Please try again later.")
            return None

    return wrapper


# Initialize session state variables
if "bike_method" not in st.session_state:
    st.session_state.bike_method = "Rent"
if "input_bike_modes" not in st.session_state:
    st.session_state.input_bike_modes = []
if "findmeabike" not in st.session_state:
    st.session_state.findmeabike = False
if "findmeadock" not in st.session_state:
    st.session_state.findmeadock = False
if "iamhere" not in st.session_state:
    st.session_state.iamhere = 0
if "iamhere_return" not in st.session_state:
    st.session_state.iamhere_return = 0

# Example URL to fetch bike share data (replace with the actual URL from the resource_urls list)
station_url = "https://tor.publicbikesystem.net/ube/gbfs/v1/en/station_status.json"
latlon_url = "https://tor.publicbikesystem.net/ube/gbfs/v1/en/station_information"

# Streamlit app setup
st.title("Toronto Bike Share Station Status")  # Set the title of the app
st.markdown(
    "This dashboard tracks bike availability at each bike share station in Toronto."
)  # Add a description


# Fetch data with error handling
@st.cache_data(ttl=60)
@handle_api_error
def get_data():
    data_df = query_station_status(station_url)
    if data_df is None:
        return None
    latlon_df = get_station_latlon(latlon_url)
    if latlon_df is None:
        return None
    return join_latlon(data_df, latlon_df)


# Get data
data = get_data()

if data is not None:
    # Display initial metrics
    col1, col2, col3 = st.columns(3)  # Create three columns for metrics
    with col1:
        st.metric(
            label="Bikes Available Now", value=sum(data["num_bikes_available"])
        )  # Display total number of bikes available
        st.metric(
            label="E-Bikes Available Now", value=sum(data["ebike"])
        )  # Display total number of e-bikes available
    with col2:
        st.metric(
            label="Stations w Available Bikes",
            value=len(data[data["num_bikes_available"] > 0]),
        )  # Display number of stations with available bikes
        st.metric(
            label="Stations w Available E-Bikes", value=len(data[data["ebike"] > 0])
        )  # Display number of stations with available e-bikes
    with col3:
        st.metric(
            label="Stations w Empty Docks",
            value=len(data[data["num_docks_available"] > 0]),
        )  # Display number of stations with empty docks

    # Track metrics for delta calculation
    deltas = [
        sum(data["num_bikes_available"]),
        sum(data["ebike"]),
        len(data[data["num_bikes_available"] > 0]),
        len(data[data["ebike"] > 0]),
        len(data[data["num_docks_available"] > 0]),
    ]

    # Add sidebar selection for user inputs
    with st.sidebar:
        bike_method = st.selectbox(
            "Are you looking to rent or return a bike?",
            ("Rent", "Return"),
            key="bike_method",
        )

        if bike_method == "Rent":
            input_bike_modes = st.multiselect(
                "What kind of bikes are you looking to rent?",
                ["ebike", "mechanical"],
                key="input_bike_modes",
            )
            st.subheader("Where are you located?")
            input_street = st.text_input("Street", "", key="input_street")
            input_city = st.text_input("City", "Toronto", key="input_city")
            input_country = st.text_input("Country", "Canada", key="input_country")
            drive = st.checkbox("I'm driving there.", key="drive")

            if st.button("Find me a bike!", type="primary"):
                if input_street.strip() == "":
                    st.error("Please input your location.")
                else:
                    with st.spinner("Finding the nearest bike..."):
                        st.session_state.findmeabike = True
                        st.session_state.iamhere = geocode(
                            f"{input_street} {input_city} {input_country}"
                        )
                        if not st.session_state.iamhere:
                            st.error("Invalid address. Please check your input.")

        elif bike_method == "Return":
            st.subheader("Where are you located?")
            input_street_return = st.text_input("Street", "", key="input_street_return")
            input_city_return = st.text_input(
                "City", "Toronto", key="input_city_return"
            )
            input_country_return = st.text_input(
                "Country", "Canada", key="input_country_return"
            )

            if st.button("Find me a dock!", type="primary"):
                if input_street_return.strip() == "":
                    st.error("Please input your location.")
                else:
                    with st.spinner("Finding the nearest dock..."):
                        st.session_state.findmeadock = True
                        st.session_state.iamhere_return = geocode(
                            f"{input_street_return} {input_city_return} {input_country_return}"
                        )
                        if not st.session_state.iamhere_return:
                            st.error("Invalid address. Please check your input.")

    try:
        # Display map based on session state
        if bike_method == "Return" and not st.session_state.findmeadock:
            center = [43.65306613746548, -79.38815311015]  # Coordinates for Toronto
            m = folium.Map(
                location=center, zoom_start=13, tiles="cartodbpositron"
            )  # Create a map with a grey background
            for _, row in data.iterrows():
                marker_color = get_marker_color(
                    row["num_bikes_available"]
                )  # Determine marker color based on bikes available
                folium.CircleMarker(
                    location=[row["lat"], row["lon"]],
                    radius=2,
                    color=marker_color,
                    fill=True,
                    fill_color=marker_color,
                    fill_opacity=0.7,
                    popup=folium.Popup(
                        f"Station ID: {row['station_id']}<br>"
                        f"Total Bikes Available: {row['num_bikes_available']}<br>"
                        f"Mechanical Bike Available: {row['mechanical']}<br>"
                        f"eBike Available: {row['ebike']}",
                        max_width=300,
                    ),
                ).add_to(m)
            st_folium(
                m, key="initial_return_map", width=800
            )  # Display the map in the Streamlit app

        if bike_method == "Rent" and not st.session_state.findmeabike:
            center = [43.65306613746548, -79.38815311015]  # Coordinates for Toronto
            m = folium.Map(
                location=center, zoom_start=13, tiles="cartodbpositron"
            )  # Create a map with a grey background
            for _, row in data.iterrows():
                marker_color = get_marker_color(
                    row["num_bikes_available"]
                )  # Determine marker color based on bikes available
                folium.CircleMarker(
                    location=[row["lat"], row["lon"]],
                    radius=2,
                    color=marker_color,
                    fill=True,
                    fill_color=marker_color,
                    fill_opacity=0.7,
                    popup=folium.Popup(
                        f"Station ID: {row['station_id']}<br>"
                        f"Total Bikes Available: {row['num_bikes_available']}<br>"
                        f"Mechanical Bike Available: {row['mechanical']}<br>"
                        f"eBike Available: {row['ebike']}",
                        max_width=300,
                    ),
                ).add_to(m)
            st_folium(
                m, key="initial_rent_map", width=800
            )  # Display the map in the Streamlit app

        # Logic for finding a bike
        if st.session_state.findmeabike and st.session_state.iamhere:
            try:
                chosen_station = get_bike_availability(
                    st.session_state.iamhere, data, st.session_state.input_bike_modes
                )
                if chosen_station:
                    center = st.session_state.iamhere
                    m1 = folium.Map(
                        location=center, zoom_start=16, tiles="cartodbpositron"
                    )
                    for _, row in data.iterrows():
                        marker_color = get_marker_color(row["num_bikes_available"])
                        folium.CircleMarker(
                            location=[row["lat"], row["lon"]],
                            radius=2,
                            color=marker_color,
                            fill=True,
                            fill_color=marker_color,
                            fill_opacity=0.7,
                            popup=folium.Popup(
                                f"Station ID: {row['station_id']}<br>"
                                f"Total Bikes Available: {row['num_bikes_available']}<br>"
                                f"Mechanical Bike Available: {row['mechanical']}<br>"
                                f"eBike Available: {row['ebike']}",
                                max_width=300,
                            ),
                        ).add_to(m1)
                    folium.Marker(
                        location=st.session_state.iamhere,
                        popup="You are here.",
                        icon=folium.Icon(color="blue", icon="person", prefix="fa"),
                    ).add_to(m1)
                    folium.Marker(
                        location=(chosen_station[1], chosen_station[2]),
                        popup="Rent your bike here.",
                        icon=folium.Icon(color="red", icon="bicycle", prefix="fa"),
                    ).add_to(m1)
                    coordinates, duration = run_osrm(
                        chosen_station, st.session_state.iamhere
                    )
                    folium.PolyLine(
                        locations=coordinates,
                        color="blue",
                        weight=5,
                        tooltip="it'll take you {} to get here.".format(duration),
                    ).add_to(m1)
                    st_folium(m1, key="route_rent_map", width=800)
                    with col3:
                        st.metric(label=":green[Travel Time (min)]", value=duration)
                else:
                    st.error("No available bikes found at nearby stations.")
            except Exception as e:
                st.error(f"Error finding a bike: {str(e)}")

        # Logic for finding a dock
        if st.session_state.findmeadock and st.session_state.iamhere_return:
            try:
                chosen_station = get_dock_availability(
                    st.session_state.iamhere_return, data
                )
                if chosen_station:
                    center = st.session_state.iamhere_return
                    m1 = folium.Map(
                        location=center, zoom_start=16, tiles="cartodbpositron"
                    )
                    for _, row in data.iterrows():
                        marker_color = get_marker_color(row["num_bikes_available"])
                        folium.CircleMarker(
                            location=[row["lat"], row["lon"]],
                            radius=2,
                            color=marker_color,
                            fill=True,
                            fill_color=marker_color,
                            fill_opacity=0.7,
                            popup=folium.Popup(
                                f"Station ID: {row['station_id']}<br>"
                                f"Total Bikes Available: {row['num_bikes_available']}<br>"
                                f"Mechanical Bike Available: {row['mechanical']}<br>"
                                f"eBike Available: {row['ebike']}",
                                max_width=300,
                            ),
                        ).add_to(m1)
                    folium.Marker(
                        location=st.session_state.iamhere_return,
                        popup="You are here.",
                        icon=folium.Icon(color="blue", icon="person", prefix="fa"),
                    ).add_to(m1)
                    folium.Marker(
                        location=(chosen_station[1], chosen_station[2]),
                        popup="Return your bike here.",
                        icon=folium.Icon(color="red", icon="bicycle", prefix="fa"),
                    ).add_to(m1)
                    coordinates, duration = run_osrm(
                        chosen_station, st.session_state.iamhere_return
                    )
                    folium.PolyLine(
                        locations=coordinates,
                        color="blue",
                        weight=5,
                        tooltip="it'll take you {} to get here.".format(duration),
                    ).add_to(m1)
                    st_folium(m1, key="route_return_map", width=800)
                    with col3:
                        st.metric(label=":green[Travel Time (min)]", value=duration)
                else:
                    st.error("No available docks found at nearby stations.")
            except Exception as e:
                st.error(f"Error finding a dock: {str(e)}")

    except Exception as e:
        st.error(f"Error displaying map: {str(e)}")

    # Add a reset button in the sidebar
    with st.sidebar:
        if st.button("Reset"):
            st.session_state.findmeabike = False
            st.session_state.findmeadock = False
            st.session_state.iamhere = 0
            st.session_state.iamhere_return = 0
            st.session_state.input_bike_modes = []
            st.experimental_rerun()

else:
    st.error("Unable to fetch bike share data. Please try again later.")
