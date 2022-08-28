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
    #Here we use Nominatin to convert address to a latitude/longitude coordinates"
    geolocator = Nominatim(user_agent="CP_sellection",
                           timeout=250) #using open street map API 
    Geo_Coordinate = geolocator.geocode(address)
    lat = Geo_Coordinate.latitude
    long = Geo_Coordinate.longitude
    return lat, long


def match_lat_long_input(string):
    """
    Function to check if string input follows lat long format.
    Input is checked with regex.
    
    """
    latlong = re.compile(r"^[-+]?([1-8]?\d(\.\d+)?|90(\.0+)?),\s*[-+]?(180(\.0+)?|((1[0-7]\d)|([1-9]?\d))(\.\d+)?)$")
    if re.match(latlong, string):
        return True
    else:
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
    client = openrouteservice.Client( # set openrouteservice API client
                                    key='5b3ce3597851110001cf62488238eb0d4788436aaae61d6f415dc75a',
                                    timeout=200, 
                                    retry_timeout=60
                                    )

    # Create isodistance based on the LKP dictionary object
    isodistance_result = client.isochrones( 
                                            locations=[(lkp_dic["long"],lkp_dic["lat"])],
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


def get_parking(bbox, max_parking=20):
    """
    Get parking=surfaces from OSM. Only parkings stored as 
    surface and as the way data type are requested.
    
    User may set max parkings in future. Default value is 10.
    
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
    # transform area to string
    largest_parkings["area"] = largest_parkings["area"].round().astype(str)
    # add m² to geodataframe area column
    largest_parkings["area"] = largest_parkings["area"] +" m\u00b2"
    # adds center of parking to geodataframe
    largest_parkings["center"] = largest_parkings["geometry"].apply(lambda _ : (_.centroid.y, _.centroid.x))
    return largest_parkings


def display_map(lkp_dic, isodistance_result_object, largest_parkings):
    """
    Using folium wrapper for leaflet.js to generate map to visualize
    result on a interactive map.
    """
    m = folium.Map( # create map object
                    location=(lkp_dic["lat"],lkp_dic["long"]),
                    tiles='CartoDB positron'
                    )
    
    folium.Marker(# Add LKP as marker to map
        location=[lkp_dic["lat"], lkp_dic["long"]],
        popup="Laatst bekende locatie.",
        icon=folium.Icon(color="red", prefix="fa", icon="fa-male"),
    ).add_to(m)
    # Add the isodistances to map
    folium.GeoJson(
                    isodistance_result_object,
                    style_function=lambda x: {'fillColor': 'yellow',
                                              'color':'black',
                                              'fillOpacity': 0.03,
                                              'weight':1},
                    popup="value"
                    ).add_to(m)
    counter = 1
    # Add all the largest parkings to map
    for _, r in largest_parkings.iterrows():
        sim_geo = gpd.GeoSeries(r['geometry'])
        geo_j = sim_geo.to_json() # convert shapely geometry to geojson
        geo_j = folium.GeoJson(# add parking polygons to the map
                               data=geo_j,
                               style_function=lambda x: {'fillColor': 'blue',
                                                        'color':'black',
                                                        'fillOpacity': 0.6,
                                                        'weight':0.5}
                               )
        
        geo_j.add_to(m)
        icon_url = r"https://upload.wikimedia.org/wikipedia/commons/8/84/Parking_lot_symbol_FLC.svg"
        icon = folium.features.CustomIcon(icon_url, icon_size=(24, 24))
        
        parking = folium.Marker(# add a marker to the center of the parkinglot
                      location=[r["center"][0], r["center"][1]],
                      popup="Parking",
                      icon=icon
                      )
        # Popup to add to the parking polygons
        popup = f"""
        <a href=https://www.google.com/search?q={str(r["center"][0])}%2C+{str(r["center"][1])} target="_blank" rel="noopener noreferrer">Google search location</a><br>
        <strong>Oppervlakte:</strong> {r["area"]}
        """
        counter +=1
        folium.Popup(popup, max_width=350, min_width=50).add_to(parking)
        parking.add_to(m)

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
                          min_value=0, 
                          max_value=10,
                          value=3,
                          step=1
                          ))
    # get user input for the estimate speed the missed person traveles by foot
    speed = float(st.slider('Inschatting verplaatsing snelheid te voet km/h',
                            min_value=0.0, 
                            max_value=6.0,
                            value=5.0,
                            step=0.5
                            ))
    # get the half distance of the maximum distance the missed person could have
    # covered
    half_distance = calculate_half_isodistance(hours, speed)
    # ranges are set to the distance the missing person could travel per half hour
    ranges = list(range(0,half_distance,round(speed*.5*1000)))
    
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
    #Call the display_map function by passing coordinates, dataframe and geoJSON file    
    st.text("")
    display_map(lkp_dic, isodistance_result, largest_parkings)
    st.text("")

if __name__ == "__main__":
    main()

