# VST-CP-selection
The VST-CP selection tool is created to locate possible CP location when VST support is requested.

The CP selection is done in two simple steps:
1. Isodistances are created with the openrouteservice API. The input parameters are based on the *last known possition* (LKP) of the missing person, the estimated speed of the missing person traveling by foot and the duration since the person is missing in hours. Half of the maximum distance the person could travel by foot is taken as a search area for a potential CP-location.
1. The bounding box in the result object from openrouteservice API is used to query Open Street Map (OSM) for parking=surface. These results are filtered to parkings of which the outline is available on OSM. Then the parking areas are ordered by there area (area is calculated by projecting the polygons to RD New EPSG:28992). The 20 largest areas are suggested as possible CP-locations.

The output of the possible CP locations are visualized on a leaflet.js map produced with folium.

This map also shows the isodistance polygons used to query the result and the LKP of the missing person. These isodistances also show the half hour distance the person could cover by foot at the estimated speed.


