# -*- coding: utf-8 -*-
"""
Basic ILS Surface Generator
"""
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, 
    QgsCoordinateReferenceSystem,
    QgsPointXY, QgsWkbTypes, QgsField, QgsFields, QgsPoint,
    QgsLineString, QgsPolygon, QgsVectorFileWriter
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from qgis.core import Qgis
from qgis.utils import iface
import math
import os
import datetime
import json
from ..utils import get_selected_feature

def calculate_basic_ils(iface, point_layer, runway_layer, params):
    """
    Create Basic ILS Surfaces
    
    :param iface: QGIS interface
    :param point_layer: Point layer with the reference point (projected CRS)
    :param runway_layer: Runway layer (projected CRS)
    :param params: Dictionary with calculation parameters
    :return: Dictionary with results
    """
    # Extract parameters - convert string values to float for calculations
    thr_elev = float(params.get('thr_elev', 0))
    export_kml = params.get('export_kml', True)
    output_dir = params.get('output_dir', os.path.expanduser('~'))
    
    # Get units and convert to meters if necessary
    thr_elev_unit = params.get('thr_elev_unit', 'm')
    original_thr_elev = thr_elev  # Store original value for logging
    
    # Convert threshold elevation to meters if it's in feet
    if thr_elev_unit == 'ft':
        thr_elev = thr_elev * 0.3048  # Convert feet to meters
        iface.messageBar().pushMessage(
            "Info", 
            f"Converted threshold elevation from {original_thr_elev} ft to {round(thr_elev, 3)} m", 
            level=Qgis.Info
        )
    elif thr_elev_unit == 'm':
        iface.messageBar().pushMessage(
            "Info", 
            f"Using threshold elevation: {thr_elev} m (no conversion needed)", 
            level=Qgis.Info
        )
    else:
        # Handle unknown units by defaulting to meters
        iface.messageBar().pushMessage(
            "Warning", 
            f"Unknown elevation unit '{thr_elev_unit}', assuming meters", 
            level=Qgis.Warning
        )
        thr_elev_unit = 'm'
    
    # Create a parameters dictionary for JSON storage
    parameters_dict = {
        'thr_elev': str(thr_elev),
        'thr_elev_unit': thr_elev_unit,
        'calculation_date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'calculation_type': 'Basic ILS'
    }
    
    # Convert parameters to JSON string
    parameters_json = json.dumps(parameters_dict)
    
    # Log the units being used
    iface.messageBar().pushMessage(
        "Info", 
        f"Using units - Threshold Elevation: {thr_elev_unit}", 
        level=Qgis.Info
    )
    
    # Check if layers exist
    if not point_layer or not runway_layer:
        iface.messageBar().pushMessage("Error", "Point or runway layer not provided", level=Qgis.Critical)
        return None
    
    # Usar la función auxiliar para obtener las features
    def show_error(message):
        iface.messageBar().pushMessage("Error", message, level=Qgis.Critical)
    
    point_feature = get_selected_feature(point_layer, show_error)
    if not point_feature:
        return None
    
    runway_feature = get_selected_feature(runway_layer, show_error)
    if not runway_feature:
        return None
    
    # Get the reference point
    thr_geom = point_feature.geometry().asPoint()
    
    # Get the runway line
    runway_geom = runway_feature.geometry().asPolyline()
    
    # Get map CRS
    map_srid = iface.mapCanvas().mapSettings().destinationCrs().authid()
    
    # Calculate azimuth
    start_point = QgsPoint(runway_geom[0])
    end_point = QgsPoint(runway_geom[1])
    #angle0 = start_point.azimuth(end_point)
    azimuth = start_point.azimuth(end_point)
    back_azimuth = azimuth + 180
    
    # # Use end of runway for calculation
    # s = -1
    # if s == -1:
    #     s2 = 0
    # else:
    #     s2 = 180
    
    # azimuth = angle0 + s2
    # back_azimuth = azimuth - 180
    
    # Function to convert from PointXY and add Z value
    def pz(point, z):
        cPoint = QgsPoint(point)
        cPoint.addZValue()
        cPoint.setZ(z)
        return cPoint
    
    # Create memory layer
    v_layer = QgsVectorLayer("PolygonZ?crs=" + map_srid, "Basic_ILS_Surfaces", "memory")
    provider = v_layer.dataProvider()
    
    # Add fields
    provider.addAttributes([
        QgsField('ILS_surface', QVariant.String),
        QgsField('parameters', QVariant.String),
        QgsField('constants', QVariant.String) #these are required for automatic processing later
    ])
    v_layer.updateFields()
    
    # Calculate surface points
    # Ground surface
    gs_center = thr_geom.project(60, back_azimuth)
    gs_a = gs_center.project(150, back_azimuth-90)
    gs_b = gs_a.project(960, azimuth)
    gs_d = gs_center.project(150, back_azimuth+90)
    gs_c = gs_d.project(960, azimuth)
    
    # Approach surface section 1
    as1_center = gs_center.project(3000, back_azimuth)
    as1_a = as1_center.project(3000*.15+150, back_azimuth-90)
    as1_d = as1_center.project(3000*.15+150, back_azimuth+90)
    
    # Approach surface section 2
    as2_center = as1_center.project(9600, back_azimuth)
    as2_a = as2_center.project(12600*.15+150, back_azimuth-90)
    as2_d = as2_center.project(12600*.15+150, back_azimuth+90)
    
    # Missed approach surface
    missed_center = thr_geom.project(900, azimuth)
    missed_a = missed_center.project(150, back_azimuth-90)
    missed_m_center = missed_center.project(1800, azimuth)
    
    # Simplified missed approach divergence calculation:
    # For the lateral divergence at 1800m from start:
    # Standard 15% slope gives lateral spread of 15% of distance = 1800 * 0.15 = 270m
    # Add initial half-width of 150m: total = 150 + 270 = 420m
    missed_half_width_1800m = 150 + (1800 * 0.15)
    
    missed_b = missed_m_center.project(missed_half_width_1800m, back_azimuth-90)
    missed_e = missed_m_center.project(missed_half_width_1800m, back_azimuth+90)
    missed_f = missed_center.project(150, back_azimuth+90)
    missed_f_center = missed_center.project(12000, azimuth)
    
    # For the final points at 12000m from start:
    # Total distance from threshold = 900 + 12000 = 12900m
    # Lateral spread = 15% of 12900m = 1935m
    # Add initial half-width: total = 150 + 1935 = 2085m
    missed_half_width_12000m = 150 + (12900 * 0.15)
    
    missed_c = missed_f_center.project(missed_half_width_12000m, back_azimuth-90)
    missed_d = missed_f_center.project(missed_half_width_12000m, back_azimuth+90)
    
    # Transition surface side distances
    transition_distance_1 = (300 - 60) / (14.3/100)
    transition_distance_2 = (300 / (14.3/100))
    transition_distance_3 = (300 - 45) / (14.3/100)
    
    # Transition surface points
    transition_e1_left = as1_d.project(transition_distance_1, back_azimuth + 90)
    transition_e1_right = as1_a.project(transition_distance_1, back_azimuth - 90)
    transition_e2_left = gs_d.project(transition_distance_2, back_azimuth + 90)
    transition_e2_right = gs_a.project(transition_distance_2, back_azimuth - 90)
    transition_e3_left = missed_e.project(transition_distance_3, back_azimuth + 90)
    transition_e3_right = missed_b.project(transition_distance_3, back_azimuth - 90)
    
    # Create and add features for each surface
    # Note: Constants arrays in the format [a, b, c] define surface equations z = ax + by + c
    # where x,y are coordinates relative to a reference point and z is elevation
    
    # Ground surface - horizontal at threshold elevation
    exterior_ring = [pz(gs_a, thr_elev), pz(gs_b, thr_elev), pz(gs_c, thr_elev), pz(gs_d, thr_elev)]
    feature = QgsFeature()
    feature.setGeometry(QgsPolygon(QgsLineString(exterior_ring)))
    feature.setAttributes(['ground surface', parameters_json,'[0,0,0]'])  # Horizontal surface
    provider.addFeatures([feature])
    
    # Approach surface section 1 - 2% upward slope (1:50)
    exterior_ring = [pz(as1_a, thr_elev+60), pz(gs_a, thr_elev), pz(gs_d, thr_elev), pz(as1_d, thr_elev+60)]
    feature = QgsFeature()
    feature.setGeometry(QgsPolygon(QgsLineString(exterior_ring)))
    feature.setAttributes(['approach surface first section', parameters_json,'[0.02,0,-1.2]'])  # 2% slope
    provider.addFeatures([feature])
    
    # Approach surface section 2 - 2.5% upward slope (1:40)
    exterior_ring = [pz(as2_a, thr_elev+300), pz(as1_a, thr_elev+60), pz(as1_d, thr_elev+60), pz(as2_d, thr_elev+300)]
    feature = QgsFeature()
    feature.setGeometry(QgsPolygon(QgsLineString(exterior_ring)))
    feature.setAttributes(['approach surface second section', parameters_json,'[0.025,0,-16.5]'])  # 2.5% slope
    provider.addFeatures([feature])
    
    # Missed approach surface - 2.5% upward slope (1:40) with lateral divergence
    exterior_ring = [pz(missed_a, thr_elev), pz(missed_b, thr_elev+1800*0.025), pz(missed_c, thr_elev+12000*.025), pz(missed_d, thr_elev+12000*0.025), pz(missed_e, thr_elev+1800*0.025), pz(missed_f, thr_elev)]
    feature = QgsFeature()
    feature.setGeometry(QgsPolygon(QgsLineString(exterior_ring)))
    feature.setAttributes(['missed approach surface', parameters_json,'[-0.025,0,-22.5]'])  # 2.5% downward slope
    provider.addFeatures([feature])
    
    # Transition surfaces - 14.3% lateral slope (1:7) connecting approach/missed surfaces
    # Left 1 - connects approach section 1 to approach section 2
    exterior_ring = [pz(as2_d, thr_elev+300), pz(as1_d, thr_elev+60), pz(transition_e1_left, thr_elev+300)]
    feature = QgsFeature()
    feature.setGeometry(QgsPolygon(QgsLineString(exterior_ring)))
    feature.setAttributes(['transition surface - left 1', parameters_json,'[0.00355,.143,-36.66]'])  # Complex slope
    provider.addFeatures([feature])
    
    # Left 2 - connects approach section 1 to ground surface
    exterior_ring = [pz(as1_d, thr_elev+60), pz(transition_e1_left, thr_elev+300), pz(transition_e2_left, thr_elev+300), pz(gs_d, thr_elev)]
    feature = QgsFeature()
    feature.setGeometry(QgsPolygon(QgsLineString(exterior_ring)))
    feature.setAttributes(['transition surface - left 2', parameters_json,'[-0.00145,0.143,-21.36]'])  # Complex slope
    provider.addFeatures([feature])
    
    # Left 3 - connects ground surface to missed approach surface
    exterior_ring = [pz(transition_e2_left, thr_elev+300), pz(gs_d, thr_elev), pz(gs_c, thr_elev), pz(missed_e, thr_elev+1800*0.025), pz(transition_e3_left, thr_elev+300)]
    feature = QgsFeature()
    feature.setGeometry(QgsPolygon(QgsLineString(exterior_ring)))
    feature.setAttributes(['transition surface - left 3', parameters_json,'[0,0.143,-21.45]'])  # 14.3% lateral slope
    provider.addFeatures([feature])
    
    # Left 4 - continues missed approach transition
    exterior_ring = [pz(missed_e, thr_elev+1800*0.025), pz(missed_d, thr_elev+12000*.025), pz(transition_e3_left, thr_elev+300)]
    feature = QgsFeature()
    feature.setGeometry(QgsPolygon(QgsLineString(exterior_ring)))
    feature.setAttributes(['transition surface - left 4', parameters_json,'[0.01075,0.143,7.58]'])  # Complex slope
    provider.addFeatures([feature])
    
    # Right 1 - mirrors left 1 on opposite side
    exterior_ring = [pz(as2_a, thr_elev+300), pz(as1_a, thr_elev+60), pz(transition_e1_right, thr_elev+300)]
    feature = QgsFeature()
    feature.setGeometry(QgsPolygon(QgsLineString(exterior_ring)))
    feature.setAttributes(['transition surface - right 1', parameters_json,'[0.00355,.143,-36.66]'])  # Complex slope
    provider.addFeatures([feature])
    
    # Right 2 - mirrors left 2 on opposite side
    exterior_ring = [pz(as1_a, thr_elev+60), pz(transition_e1_right, thr_elev+300), pz(transition_e2_right, thr_elev+300), pz(gs_a, thr_elev)]
    feature = QgsFeature()
    feature.setGeometry(QgsPolygon(QgsLineString(exterior_ring)))
    feature.setAttributes(['transition surface - right 2', parameters_json,'[-0.00145,0.143,-21.36]'])  # Complex slope
    provider.addFeatures([feature])
    
    # Right 3 - mirrors left 3 on opposite side
    exterior_ring = [pz(transition_e2_right, thr_elev+300), pz(transition_e3_right, thr_elev+300), pz(missed_b, thr_elev+1800*0.025), pz(gs_b, thr_elev), pz(gs_a, thr_elev)]
    feature = QgsFeature()
    feature.setGeometry(QgsPolygon(QgsLineString(exterior_ring)))
    feature.setAttributes(['transition surface - right 3', parameters_json,'[0,0.143,-21.45]'])  # 14.3% lateral slope
    provider.addFeatures([feature])
    
    # Right 4 - mirrors left 4 on opposite side
    exterior_ring = [pz(missed_b, thr_elev+1800*0.025), pz(missed_c, thr_elev+12000*.025), pz(transition_e3_right, thr_elev+300)]
    feature = QgsFeature()
    feature.setGeometry(QgsPolygon(QgsLineString(exterior_ring)))
    feature.setAttributes(['transition surface - right 4', parameters_json,'[0.01075,0.143,7.58]'])  # Complex slope
    provider.addFeatures([feature])
    
    # Update layer extents
    v_layer.updateExtents()
    
    # Style the layer - green with 50% opacity as requested by client
    v_layer.renderer().symbol().setColor(QColor(0, 255, 0, 127))  # Green with 50% opacity
    v_layer.renderer().symbol().symbolLayer(0).setStrokeColor(QColor(0, 255, 0))
    v_layer.renderer().symbol().symbolLayer(0).setStrokeWidth(0.7)
    
    # Add layer to the project
    QgsProject.instance().addMapLayer(v_layer)
    
    # Zoom to layer
    v_layer.selectAll()
    canvas = iface.mapCanvas()
    canvas.zoomToSelected(v_layer)
    v_layer.removeSelection()
    
    # Export to KML if requested
    result = {
        'ils_layer': v_layer
    }
    
    if export_kml:
        # Get current timestamp for unique filenames
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Define KML export path
        kml_export_path = os.path.join(output_dir, f'Basic_ILS_Surfaces_{timestamp}.kml')
        
        # Export to KML using WGS84 (required for KML format)
        kml_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        
        kml_error = QgsVectorFileWriter.writeAsVectorFormat(
            v_layer,
            kml_export_path,
            'utf-8',
            kml_crs,
            'KML',
            layerOptions=['MODE=2']
        )
        
        # Correct KML structure for better visualization
        def correct_kml_structure(kml_file_path):
            with open(kml_file_path, 'r') as file:
                kml_content = file.read()
            
            # Add altitude mode
            kml_content = kml_content.replace('<Polygon>', '<Polygon>\n  <altitudeMode>absolute</altitudeMode>')
            
            # Add style - green with 50% opacity
            style_kml = '''
            <Style id="style1">
                <LineStyle>
                    <color>ff00ff00</color>
                    <width>2</width>
                </LineStyle>
                <PolyStyle>
                    <fill>1</fill>
                    <color>ff00ff7F</color>
                </PolyStyle>
            </Style>
            '''
            
            kml_content = kml_content.replace('<Document>', f'<Document>{style_kml}')
            kml_content = kml_content.replace('<styleUrl>#</styleUrl>', '<styleUrl>#style1</styleUrl>')
            
            with open(kml_file_path, 'w') as file:
                file.write(kml_content)
        
        # Apply corrections to KML file
        if kml_error[0] == QgsVectorFileWriter.NoError:
            correct_kml_structure(kml_export_path)
            result['kml_path'] = kml_export_path
    
    # Zoom to appropriate scale
    sc = canvas.scale()
    if sc < 20000:
        sc = 20000
    canvas.zoomScale(sc)
    
    # Show success message
    iface.messageBar().pushMessage("QPANSOPY:", "Basic ILS Surfaces created successfully", level=Qgis.Success)
    
    return result

def copy_parameters_table(params):
    """Generate formatted table for Basic ILS parameters"""
    from ..utils import format_parameters_table
    
    # Get original and converted values for display
    original_value = params.get('thr_elev', 0)
    original_unit = params.get('thr_elev_unit', 'm')
    
    # Calculate converted value if necessary
    if original_unit == 'ft':
        converted_value = float(original_value) * 0.3048
        display_text = f"{original_value} {original_unit} ({round(converted_value, 3)} m)"
    else:
        display_text = f"{original_value} {original_unit}"
    
    params_dict = {
        'runway_data': {
            'threshold_elevation': {'value': display_text, 'unit': ''}
        },
        'calculation_info': {
            'coordinate_system': {'value': 'Projected CRS Required', 'unit': ''},
            'surface_slopes': {'value': 'Approach: 2-2.5%, Transition: 14.3%', 'unit': ''},
            'constants_format': {'value': '[a, b, c] for z = ax + by + c', 'unit': ''}
        }
    }

    sections = {
        'threshold_elevation': 'Runway Data',
        'coordinate_system': 'Calculation Info',
        'surface_slopes': 'Calculation Info',
        'constants_format': 'Calculation Info'
    }

    return format_parameters_table(
        "QPANSOPY BASIC ILS PARAMETERS",
        params_dict,
        sections
    )