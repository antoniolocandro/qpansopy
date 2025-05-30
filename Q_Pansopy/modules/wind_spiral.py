# -*- coding: utf-8 -*-
"""
Wind Spiral Generator
"""
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, 
    QgsCoordinateReferenceSystem, QgsCoordinateTransform,
    QgsPointXY, QgsWkbTypes, QgsField, QgsFields, QgsPoint,
    QgsLineString, QgsPolygon, QgsVectorFileWriter, QgsCircularString
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from qgis.core import Qgis
from qgis.utils import iface
import math
import os
import datetime
import json

def ISA_temperature(adElev, tempRef):
    """Calculate ISA temperature and deviation"""
    tempISA = 15 - 0.00198 * adElev
    deltaISA = tempRef - tempISA
    return (adElev, tempRef, tempISA, deltaISA)

def tas_calculation(ias, altitude, var, bank_angle):
    """Calculate TAS and turn parameters"""
    k = 171233 * (((288 + var) - 0.00198 * altitude) ** 0.5) / (288 - 0.00198 * altitude) ** 2.628
    tas = k * ias
    rate_of_turn = (3431 * math.tan(math.radians(bank_angle))) / (math.pi * tas)
    radius_of_turn = tas / (20 * math.pi * rate_of_turn)
    w = 30  # Wind speed (hardcoded for now)
    return k, tas, rate_of_turn, radius_of_turn, w

def calculate_wind_spiral(iface, point_layer, reference_layer, params):
    """
    Create Wind Spiral
    
    :param iface: QGIS interface
    :param point_layer: Point layer with the reference point
    :param reference_layer: Reference line layer (runway or approach track)
    :param params: Dictionary with calculation parameters
    :return: Dictionary with results
    """
    # Extract parameters
    adElev = float(params.get('adElev', 0))
    tempRef = float(params.get('tempRef', 15))
    IAS = float(params.get('IAS', 205))
    altitude = float(params.get('altitude', 800))
    bankAngle = float(params.get('bankAngle', 15))
    w = float(params.get('w', 30))
    turn_direction = params.get('turn_direction', 'R')
    show_points = params.get('show_points', True)
    export_kml = params.get('export_kml', True)
    output_dir = params.get('output_dir', os.path.expanduser('~'))
    
    # Create a parameters dictionary for JSON storage
    parameters_dict = {
        'adElev': str(adElev),
        'tempRef': str(tempRef),
        'IAS': str(IAS),
        'altitude': str(altitude),
        'bankAngle': str(bankAngle),
        'w': str(w),
        'turn_direction': turn_direction,
        'calculation_date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'calculation_type': 'Wind Spiral'
    }
    
    # Convert parameters to JSON string
    parameters_json = json.dumps(parameters_dict)
    
    # Calculate ISA temperature
    valueISA = ISA_temperature(adElev, tempRef)
    
    # Log ISA deviation
    iface.messageBar().pushMessage(
        "Info", 
        f"ISA + {valueISA[3]}", 
        level=Qgis.Info
    )
    
    # Set turn direction
    if turn_direction == "L":
        side = 90
        d = (30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330)  # NM
    else:  # Default to right turn
        side = -90
        d = (-30, -60, -90, -120, -150, -180, -210, -240, -270, -300, -330)  # NM
    
    # Calculate TAS and turn parameters
    values = tas_calculation(IAS, altitude, valueISA[3], bankAngle)
    r_turn = values[3]
    
    # Calculate drift angle
    drift_angle = math.asin(values[4] / values[1])
    
    # Calculate wind spiral radii
    wind_spiral_radius = {}
    for i in range(30, 390, 30):
        windspiral = (i / values[2]) * (values[4] / 3600)
        wind_spiral_radius["radius_" + str(i)] = windspiral
    
    # Get map CRS
    map_srid = iface.mapCanvas().mapSettings().destinationCrs().authid()
    
    # Get reference line geometry
    if reference_layer and reference_layer.featureCount() > 0:
        reference_feature = next(reference_layer.getFeatures())
        geom = reference_feature.geometry().asPolyline()
        start_point = QgsPoint(geom[-1])
        end_point = QgsPoint(geom[0])
        angle0 = start_point.azimuth(end_point) + 180
    else:
        iface.messageBar().pushMessage("Error", "Reference layer not provided or empty", level=Qgis.Critical)
        return None
    
    # Initial true azimuth data
    azimuth = angle0
    
    # Get point geometry
    if point_layer and point_layer.featureCount() > 0:
        point_feature = next(point_layer.getFeatures())
        p_geom = point_feature.geometry().asPoint()
    else:
        iface.messageBar().pushMessage("Error", "Point layer not provided or empty", level=Qgis.Critical)
        return None
    
    # Initialize points list for circular string
    u = []
    u.append(QgsPoint(p_geom))
    
    # Create point layer if requested
    if show_points:
        v_layer = QgsVectorLayer("Point?crs=" + map_srid, "Wind Spiral Points", "memory")
        myField = QgsField('spiral', QVariant.String)
        v_layer.dataProvider().addAttributes([myField])
        v_layer.updateFields()
        pr = v_layer.dataProvider()
        
        # Calculate center point
        angle = 90 - azimuth + side  # left/right
        bearing = math.radians(azimuth)
        angle = math.radians(angle)
        dist_x, dist_y = (r_turn * 1852 * math.cos(angle), r_turn * 1852 * math.sin(angle))
        xc, yc = (p_geom.x() + dist_x, p_geom.y() + dist_y)
        line_start = QgsPointXY(xc, yc)
        
        # Add center point
        seg = QgsFeature()
        seg.setGeometry(QgsGeometry.fromPointXY(line_start))
        seg.setAttributes(['Wind Spiral Center'])
        pr.addFeatures([seg])
        
        # Get angle from Center to P
        connect_line = QgsGeometry.fromPolyline([QgsPoint(line_start), QgsPoint(p_geom)])
        start_point_C = QgsPoint(connect_line.asPolyline()[0])
    else:
        # Calculate center point without creating layer
        angle = 90 - azimuth + side
        bearing = math.radians(azimuth)
        angle = math.radians(angle)
        dist_x, dist_y = (r_turn * 1852 * math.cos(angle), r_turn * 1852 * math.sin(angle))
        xc, yc = (p_geom.x() + dist_x, p_geom.y() + dist_y)
        line_start = QgsPointXY(xc, yc)
        start_point_C = QgsPoint(line_start)
    
    # Calculate points for wind spiral
    for i in d:
        e = list(wind_spiral_radius.values())[int(abs(i) / 30) - 1]
        
        bearing = azimuth
        angle = 90 - bearing + i - side
        bearing = math.radians(bearing)
        angle = math.radians(angle)
        
        # Calculate point on spiral
        dist_x, dist_y = ((r_turn + e) * 1852 * math.cos(angle), (r_turn + e) * 1852 * math.sin(angle))
        bx1, by2 = (start_point_C.x() + dist_x, start_point_C.y() + dist_y)
        line_start1 = QgsPointXY(bx1, by2)
        
        # Calculate point on circle
        dist_x, dist_y = (r_turn * 1852 * math.cos(angle), r_turn * 1852 * math.sin(angle))
        cx1, cy2 = (start_point_C.x() + dist_x, start_point_C.y() + dist_y)
        line_start2 = QgsPointXY(cx1, cy2)
        
        # Calculate drift point
        dist_xd, dist_yd = (e * 1852 * math.cos(angle - drift_angle * (side / 90)), 
                           e * 1852 * math.sin(angle - drift_angle * (side / 90)))
        dx1, dy2 = (cx1 + dist_xd, cy2 + dist_yd)
        line_startd = QgsPointXY(dx1, dy2)
        
        # Add point to circular string
        u.append(QgsPoint(line_startd))
        
        # Add drift point to point layer if requested
        if show_points:
            seg = QgsFeature()
            seg.setGeometry(QgsGeometry.fromPointXY(line_startd))
            seg.setAttributes(['drift_angle'])
            pr.addFeatures([seg])
    
    # Create line layer for wind spiral curve
    pv_layer = QgsVectorLayer("LineString?crs=" + map_srid, "Wind Spiral Curve", "memory")
    myField = QgsField('parameters', QVariant.String)
    pv_layer.dataProvider().addAttributes([myField])
    pv_layer.updateFields()
    prv = pv_layer.dataProvider()
    
    # Create circular string geometry
    cString = QgsCircularString()
    cString.setPoints(u)
    geom_cString = QgsGeometry(cString)
    
    # Add feature to line layer
    seg = QgsFeature()
    seg.setGeometry(geom_cString)
    seg.setAttributes([parameters_json])
    prv.addFeatures([seg])
    
    # Update layer extents
    pv_layer.updateExtents()
    
    # Style line layer
    pv_layer.renderer().symbol().setColor(QColor("green"))
    pv_layer.renderer().symbol().setWidth(0.5)
    pv_layer.triggerRepaint()
    
    # Add layers to the project
    QgsProject.instance().addMapLayer(pv_layer)
    
    if show_points:
        v_layer.updateExtents()
        QgsProject.instance().addMapLayer(v_layer)
    
    # Export to KML if requested
    result = {
        'spiral_layer': pv_layer
    }
    
    if show_points:
        result['points_layer'] = v_layer
    
    if export_kml:
        # Get current timestamp for unique filenames
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Define KML export path
        spiral_export_path = os.path.join(output_dir, f'wind_spiral_{timestamp}.kml')
        
        # Export to KML
        crs = QgsCoordinateReferenceSystem("EPSG:4326")
        
        # Export spiral layer
        spiral_error = QgsVectorFileWriter.writeAsVectorFormat(
            pv_layer,
            spiral_export_path,
            'utf-8',
            crs,
            'KML',
            layerOptions=['MODE=2']
        )
        
        # Apply corrections to KML file
        if spiral_error[0] == QgsVectorFileWriter.NoError:
            result['spiral_path'] = spiral_export_path
    
    # Show success message
    iface.messageBar().pushMessage("QPANSOPY:", "Wind Spiral created successfully", level=Qgis.Success)
    
    return result

'''
Wind Spiral Construction
'''

myglobals = set(globals().keys())

from qgis.core import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from qgis.gui import *
from qgis.PyQt.QtCore import QVariant
from math import *

#side = 90 #right
#side = 90

#Parameters
#XTT = 1.0
#AW = 2.5
adElev = 62/0.3048 #feet
tempRef = 34.597244094488189
IAS = 205
altitude = 800
bankAngle = 15
w = 30
tp = 6

u = []

def ISA_temperature (adElev,tempRef):
    tempISA = 15 -0.00198*adElev
    deltaISA = tempRef-tempISA
    return(adElev,tempRef,tempISA,deltaISA)

valueISA = ISA_temperature(adElev,tempRef)

print ("ISA +",valueISA[3])

sides= QInputDialog.getText(None, "Turn Direction" ,"L or R")


if sides[0] =="L":
    side = 90
    d = (30,60,90,120,150,180,210,240,270,300,330) #NM
elif sides[0] =="R":
    side=-90
    d = (-30,-60,-90,-120,-150,-180,-210,-240,-270,-300,-330) #NM
else:
    side ='X'

#print (side)


'''
IAS: 240KT Table I-4-1-2
Conversion factor: 1.1586
TAS = k*IAS = 1.1586 * 240KT = 278.064KT
Bank angle = 25°
R = 3431*tan(25) / pi*278.064KT = 1.831465 °/s (<3°/s then ok)
r = 278.064KT/(20*pi*1.831465°/s) = 2.4164 NM

W = 2*8 + 47 = 63KT

Eθ = (θ/R)*(w/3600)
T30 = 16.38s
E30 = (30/1.831465)*(63/3600) = 0.29
E60 = 0.58
E90 = 0.87
E120 = 1.16
E150 = 1.45
E180 = 1.74
E210 = 2.03

Arcsin (63/278.064) = 13.10°

'''
#IAS = QInputDialog.getText(None, 'Turn Parameters', 'IAS')

# import required modules
from math import *

'''
Aviation Calculations for Wind Spiral
'''

def tas_calculation (ias,altitude,var,bank_angle):
    k = 171233*(((288+var)-0.00198*altitude)**0.5)/(288-0.00198*altitude)**2.628
    tas = k*ias
    rate_of_turn = (3431*tan(radians(bank_angle)))/(pi*tas)
    radius_of_turn = tas/(20*pi*rate_of_turn)
    #w = (2*altitude/1000)+47 #hardcoded icao standard wind
    w = 30 
    return k,tas,rate_of_turn,radius_of_turn,w

#print (tas_calculation(250,5100,20,25))

values = tas_calculation(IAS,altitude,valueISA[3],bankAngle)

print (values)



#r_turn=tas_calculation(240,8000,15,25)[3]
r_turn=values[3]
wind_spiral_radius ={}
drift_angle = asin(values[4]/values[1])
print ("drift angle:",degrees(drift_angle))

for i in range (30,390,30):
    windspiral = (i/values[2])*(values[4]/3600)
    wind_spiral_radius["radius_"+str(i)]=windspiral
    #print ('%i,%s' % (i, windspiral))

#print (wind_spiral_radius)

from qgis.core import Qgis
iface.messageBar().pushMessage("QPANSOPY:", "Wind Spiral", level=Qgis.Info)

# Select line
# Gets the routing layer 

for layer in QgsProject.instance().mapLayers().values():
    if "reference" in layer.name():
        layer = layer
        selection = layer.selectedFeatures()
        geom=selection[0].geometry().asPolyline()
        #print (geom)
        start_point = QgsPoint(geom[-1])
        end_point = QgsPoint(geom[0])
        angle0=start_point.azimuth(end_point)+180
        length0=selection[0].geometry().length()
        back_angle0 = angle0+180
        #print ("angle:",angle0,length0/1852)

#initial true azimuth data
azimuth =angle0

#map_srid
map_srid = iface.mapCanvas().mapSettings().destinationCrs().authid()
#print (map_srid)

# Selected point P
# Gets the active layer 
layer = iface.activeLayer()
selection = layer.selectedFeatures()
# Gets x,y
for feat in selection:
    p_geom = feat.geometry().asPoint()
    #print (p_geom)

#print("radius_turn",round(r_turn,3))

u.append(QgsPoint(p_geom))


#Create memory layer
v_layer = QgsVectorLayer("Point?crs="+map_srid, "wind spiral", "memory")
myField = QgsField( 'spiral', QVariant.String)
v_layer.dataProvider().addAttributes([myField])
v_layer.updateFields()


#def draw windspiral

angle =     90-azimuth+side#left/right
#print (angle)
bearing = math.radians(azimuth)
angle =   math.radians(angle)
dist_x, dist_y = (r_turn*1852 * math.cos(angle), r_turn*1852 * math.sin(angle))
#print (dist_x, dist_y)
xc, yc = (p_geom.x() + dist_x, p_geom.y() + dist_y)
#xc, yc = (p_geom.x() , p_geom.y())
line_start = QgsPointXY(xc,yc)
pr = v_layer.dataProvider()

# create a new feature
seg = QgsFeature()
seg.setGeometry(QgsGeometry.fromPointXY(line_start))
seg.setAttributes(['Wind Spiral Center'])
### ...it was here that you can add attributes, after having defined....
### add the geometry to the layer
pr.addFeatures( [ seg ] )

#Get angle from Center to P

connect_line = QgsGeometry.fromPolyline([QgsPoint(line_start),QgsPoint(p_geom)])
start_point_C = QgsPoint(connect_line.asPolyline()[0])
anglec=start_point_C.azimuth(end_point)+180
#print ("angle center: ",anglec)

v_layer.updateExtents()

## show the line  
QgsProject.instance().addMapLayers([v_layer])
#

for i in d:
    
    e=list(wind_spiral_radius.values())[int(abs(i)/30)-1]
    print (i,e)
    bearing =  azimuth
    angle =     90 - bearing+i-side
    bearing = math.radians(bearing)
    angle =   math.radians(angle)
    dist_x, dist_y = \
        ((r_turn+e)*1852 * math.cos(angle), (r_turn+e)*1852 * math.sin(angle))
    #print (dist_x, dist_y)
    bx1, by2 = (start_point_C.x()  + dist_x, start_point_C.y()  + dist_y)
    #print (bx1, by2)
    line_start1 = QgsPointXY(bx1,by2)
    # add the geometry to the feature, 
#    seg.setGeometry(QgsGeometry.fromPointXY(line_start1))
#    seg.setAttributes(['W+E'+str(i)])
#    ## ...it was here that you can add attributes, after having defined....
#    ## add the geometry to the layer
#    pr.addFeatures( [ seg ] )
#    
    dist_x, dist_y = (r_turn*1852 * math.cos(angle),r_turn*1852 * math.sin(angle))
#    #print (dist_x, dist_y)
    cx1, cy2 = (start_point_C.x()  + dist_x, start_point_C.y()  + dist_y)
    #print (bx1, by2)
    line_start2 = QgsPointXY(cx1,cy2)
#    # add the geometry to the feature, 
#    seg.setGeometry(QgsGeometry.fromPointXY(line_start2))
#    seg.setAttributes(['Wind Spiral Center'+str(i)])
#    ## ...it was here that you can add attributes, after having defined....
#    ## add the geometry to the layer
#    pr.addFeatures( [ seg ] )

    drift_line = QgsGeometry.fromPolyline([QgsPoint(line_start2),QgsPoint(line_start1)])
    #print ("drift_line",drift_line)
    start_point_d = QgsPoint(drift_line.asPolyline()[0])
    #bearing_d=start_point_d.azimuth(end_point)-180
    #print ("bearing_d",bearing_d)
    
    #angled =     90 - bearing_d
    dist_xd, dist_yd = (e*1852 * math.cos(angle-drift_angle*(side/90)),e*1852 * math.sin(angle-drift_angle*(side/90)))
    dx1, dy2 = (cx1  + dist_xd, cy2  + dist_yd)
    #print (dx1, dy2)
    line_startd = QgsPointXY(dx1,dy2)
    u.append (QgsPoint(line_startd))
    #print ("line startd",line_startd)
    # add the geometry to the feature, 
    seg = QgsFeature()
    seg.setGeometry(QgsGeometry.fromPointXY(line_startd))
    seg.setAttributes(['drift_angle'])
    ## ...it was here that you can add attributes, after having defined....
    ## add the geometry to the layer
    pr.addFeatures( [ seg ] )

#print (u)


#Create memory layer
pv_layer = QgsVectorLayer("LineString?crs="+map_srid, "Wind Spiral Curve", "memory")
myField = QgsField( 'turn', QVariant.String)
pv_layer.dataProvider().addAttributes([myField])
pv_layer.updateFields()
prv = pv_layer.dataProvider()
cString=QgsCircularString()
cString.setPoints(u)
#print (cString.hasCurvedSegments())
geom_cString=QgsGeometry(cString)
seg = QgsFeature()
seg.setGeometry(geom_cString)
prv.addFeatures( [ seg ] )



pv_layer.updateExtents()
QgsProject.instance().addMapLayers([pv_layer])

#Change style of layer 
pv_layer.renderer().symbol().setColor(QColor("green"))
pv_layer.renderer().symbol().setWidth(0.5)
pv_layer.triggerRepaint()




##
## Zoom to layer
#v_layer.selectAll()
#canvas = iface.mapCanvas()
#canvas.zoomToSelected(v_layer)
#v_layer.removeSelection()
##
###
####get canvas scale
###sc = canvas.scale()
####print (sc)
###if sc < 20000:
###   sc=20000
##else:
##    sc=sc
###print (sc)
##
#canvas.zoomScale(150000)
#
##for layer in QgsProject.instance().mapLayers().values():
##    if "Initial Approach Area" in layer.name():
##        layer.loadNamedStyle('c:/Users/Antonio/Documents/GitHub/qpansopy/styles/primary_secondary_areas.qml')
##    else:
##            pass
#            
#v_layer.loadNamedStyle('c:/Users/Antonio/Documents/GitHub/qpansopy/styles/primary_secondary_areas.qml')
#

iface.messageBar().pushMessage("QPANSOPY:", "Finished Wind Spirals", level=Qgis.Success)

set(globals().keys()).difference(myglobals)

for g in set(globals().keys()).difference(myglobals):
    if g != 'myglobals':
        del globals()[g]