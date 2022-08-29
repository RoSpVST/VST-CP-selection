# -*- coding: utf-8 -*-
"""

"""
from geopy.geocoders import Nominatim
import re
import streamlit as st
import requests
from urllib.parse import quote
import geopandas as gpd
import pandas as pd
import openrouteservice # wrapper for ORS api
import overpass # wrapper for overpass api
import folium


def convert_address(address):
    """
    Convert address as string to lat, long coordinate by using Nominatim
    geocoder. This geocoder is based on the openstreetmap API.
    """
    # Nominatin to convert address to a latitude/longitude coordinates"
    geolocator = Nominatim(user_agent="CP_sellection",
                           timeout=300) 
    Geo_Coordinate = geolocator.geocode(address)
    lat = Geo_Coordinate.latitude
    long = Geo_Coordinate.longitude
    return lat, long


def match_lat_long_input(string):
    """
    Function to check if string input follows lat long format.
    Input is checked with regex.
    
    """
    # regex pattern to check string for lat long in DD format
    pattern = r"^[-+]?([1-8]?\d(\.\d+)?|90(\.0+)?),\s*[-+]?(180(\.0+)?|((1[0-7]\d)|([1-9]?\d))(\.\d+)?)$"
    latlong = re.compile(pattern) # compile the patteren
    if re.match(latlong, string): # check for match in input string
        return True
    return False
    
    
def calculate_half_isodistance(hours, speed):
    """
    Calculates half of the distance the missing person
    can reach.
    
    The function is to prevent exceding the limits of the open
    route service API
    """
    half_isodistance = (speed*hours)/2
    return round(half_isodistance * 1000)


def create_isodistance(lkp_dic):
    """
    Function to use Open Route Service API with isodistances based
    on the user input stored in lkp_dic object.
    
    Output is the result object from Open route service API.
    """
    key='5b3ce3597851110001cf62488238eb0d4788436aaae61d6f415dc75a'
    client = openrouteservice.Client( # set openrouteservice API client
                                    key=key,
                                    timeout=300, 
                                    retry_timeout=60
                                    )

    # Create isodistance based on the LKP dictionary object
    isodistance_result = client.isochrones( 
                                            locations=[(lkp_dic["long"],
                                                        lkp_dic["lat"])],
                                            profile="foot-walking",
                                            range_type="distance",
                                            range=lkp_dic["ranges"],
                                            units="m",
                                            smoothing=0.85,
                                            validate=True
                                            )
    return isodistance_result


def get_bbox(isodistance_result_object):
    """
    Transform de bbox from the Open Route Service isodistance
    to the bbox accepted by the overpass API.
    
    Output is BBOX (S,W,N,E) as string
    """
    bbox = isodistance_result_object["bbox"] # store bbox from result object
    reorder_bbox = [1, 0, 3, 2] # indices to reorder bbox to S,W,N,E
    bbox = ", ".join([str(bbox[i]) for i in reorder_bbox]) # reorder bbox
    return bbox


def get_parking(bbox, max_parking=50):
    """
    Get parking=surfaces from OSM. Only parkings stored as 
    surface and as the way data type are requested.
    
    User may set max parkings in future. Default value is 30.
    
    """
    q = f"""way["parking"="surface"]({bbox});out;"""
    api = overpass.API(timeout=500) # query overpass
    result = api.get(q, verbosity='geom') # store result
    # load result in geodataframe
    gdf = gpd.GeoDataFrame.from_features(result, crs="4326") 
    # filter parkinglots of witch boundaries are stored in the result
    gdf= gdf[gdf.geom_type != 'GeometryCollection'] 
    # create polygons from the parkinglots
    gdf["geometry"] = gdf["geometry"].convex_hull 
    # calculate and store areas of the parking (crs to RD New)
    gdf["area"] = gdf.to_crs("28992").geometry.area 
    # select largest parking by using max_parking parameter
    largest_parkings = gdf.sort_values("area",ascending=False).head(max_parking)
    if gdf['capacity'].isnull().values.any() < len(gdf['capacity']):
        # calculate average area per car
        average_area = int(largest_parkings["area"].mean(skipna=True)/largest_parkings["capacity"].astype(float).mean(skipna=True))
    else:
        average_area = 30
    # if capacity is NaN the capcity  will be calculated with average area per vehicle
    largest_parkings["capacity"] = largest_parkings["capacity"].fillna(largest_parkings["area"]/average_area)
    largest_parkings["capacity"] = largest_parkings["capacity"].astype(int)
    # set NaN values in access attribute to unknown
    largest_parkings["access"] = largest_parkings["access"].fillna("onbekend")
    # transform area to string
    largest_parkings["area"] = largest_parkings["area"].round().astype(str)
    # add m² to geodataframe area column
    largest_parkings["area"] = largest_parkings["area"] +" m\u00b2"
    # adds center of parking to geodataframe
    largest_parkings["center"] = largest_parkings["geometry"].apply(lambda _ : (_.centroid.y, _.centroid.x))
    return largest_parkings

@st.cache
def convert_to_geojson(gdf):
    return gdf.to_json()


def display_map(lkp_dic, isodistance_result_object, largest_parkings):
    """
    Using folium wrapper for leaflet.js to visualize the result of the CP
    suggestions, LKP and the half of the distance covered by the missing person
    on one map.
    
    The map has 2 basemaps available being:
        - Openstreetmap
        - Esri sattelite layer
    
    
    """
    # create map object
    m = folium.Map( 
                    location=(lkp_dic["lat"],lkp_dic["long"]),
                    tiles='openstreetmap'
                    )
   
    # add imagery basemap to map
    folium.TileLayer(
        tiles = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr = 'Esri',
        name = 'Esri Satellite',
        overlay = False,
        control = True
       ).add_to(m)
    
    # add LKP as marker to map
    folium.Marker(
                  location=[lkp_dic["lat"], lkp_dic["long"]],
                  popup="Laatst bekende locatie.",
                  icon=folium.Icon(
                                   color="red", 
                                   prefix="fa", 
                                   icon="fa-male"
                                   ),
                  ).add_to(m)
    
    # add the isodistance to map
    folium.GeoJson(
                    isodistance_result_object,
                    style_function=lambda x: {'fillColor':'yellow',
                                              'color':'black',
                                              'fillOpacity': 0.2,
                                              'weight':1},
                    popup="value",
                    control=False,
                    ).add_to(m)

    # add all the largest parkings to map
    for _, r in largest_parkings.iterrows():
        sim_geo = gpd.GeoSeries(r['geometry'])
        geo_j = sim_geo.to_json() # convert shapely geometry to geojson
        # add outline of parking surfaces to map object
        folium.GeoJson(
                       data=geo_j,
                       style_function=lambda x: {'fillColor': 'blue',
                                             'color':'black',
                                             'fillOpacity': 0.6,
                                             'weight':0.5},
                       control=False
                       ).add_to(m)
        icon_url = r"https://upload.wikimedia.org/wikipedia/commons/8/84/Parking_lot_symbol_FLC.svg"
        icon = folium.features.CustomIcon(icon_url, icon_size=(24, 24))
        
        parking = folium.Marker(# add a marker to the center of the parkinglot
                      location=[r["center"][0], r["center"][1]],
                      popup="Parking",
                      icon=icon
                      )
        
        # Popup to add to the parking polygons
        popup = f"""
        <a href=http://maps.google.com/maps?z=12&t=m&q=loc:{str(r["center"][0])}+{str(r["center"][1])} target="_blank" rel="noopener noreferrer">Open locatie in Google Maps</a><br>
        <strong>Oppervlakte:</strong> {r["area"]}<br>
        <strong>Capaciteit (schatting indien niet aanwezig in brondata):</strong> {str(r["capacity"])}<br>
        <strong>Open toegankelijk:</strong> {r["access"]}</br>
        """
        # add popup to marker
        folium.Popup(popup, max_width=350, min_width=50).add_to(parking)
        # add parking marker to mapp
        parking.add_to(m)
    folium.LayerControl().add_to(m)
    m.fit_bounds(m.get_bounds(),padding=(-150,-150))
    return st.markdown(m._repr_html_(), unsafe_allow_html=True)


def main():
    # html code to hide default buttons and footer from streamlit
    hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
    """
    st.markdown(hide_streamlit_style, unsafe_allow_html=True)  
    #for the page display, create headers and subheader, and get an input address from the user
    st.header("VST CP selectie (bèta-versie)")
    st.text("")
    st.subheader("CP selecteren op basis van Last Known Position (LKP)")
    st.text("")
    address = st.text_input("Adres of coordinaat (lat, long) van de LKP?", 
                            value="Hobbemalaan 5, 3712 AZ Huis Ter Heide",
                            help="Use decimal degree for lat long input."
                           )
    # to check if a lat long coordinate is used as input
    if match_lat_long_input(address):
        lat = float(address.split(",")[0].strip())
        long = float(address.split(",")[1].strip())
    else:
        # use the convert_address function to convert address to coordinates
        lat, long = convert_address(address)
    # get user input of hours since person was at LKP
    hours = int(st.slider('Aantal uren vermist vanaf LKP?', 
                          min_value=1, 
                          max_value=10,
                          value=2,
                          step=1
                          ))
    # get user input for the estimate speed the missed person traveles by foot
    speed = float(st.slider('Inschatting verplaatsing snelheid te voet km/h',
                            min_value=0.5, 
                            max_value=6.0,
                            value=5.0,
                            step=0.5
                            ))
    # get the half distance of the maximum distance the missed person could have
    # covered
    half_distance = calculate_half_isodistance(hours, speed)
    # ranges are set to the distance the missing person could travel per half hour
    ranges = [int(half_distance)]
    lkp_dic ={ # store the input in dictionary
              "lat":lat,
              "long":long,
              "distance":half_distance,
              "duration":hours,
              "speed":speed,
              "ranges":ranges
              }
    # get the isodistances by using lkp_dic
    isodistance_result = create_isodistance(lkp_dic)
    # get the bounding box in the correct format for overpass query
    bbox = get_bbox(isodistance_result)
    # query overpass for parking locations
    largest_parkings = get_parking(bbox)
    # convert geodataframe to json
    json = convert_to_geojson(largest_parkings)
    # add download button to download CP suggestions
    st.download_button(
                        label="Download mogelijke CP locaties als JSON",
                        data=json,
                        file_name='cp_selection_parking.json'
                        )
    #Call the display_map function by passing coordinates, dataframe and geoJSON file    
    st.text("")
    # build and add map html to streamlit app
    display_map(
                lkp_dic, 
                isodistance_result, 
                largest_parkings
                )
    st.text("")

if __name__ == "__main__":
    main()
