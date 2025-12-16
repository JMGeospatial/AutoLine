from qgis.core import QgsVectorLayer, QgsFeature
import processing
import math

def sample_depth(line_geom, dem_layer, crs_authid, depth_sampling_interval=5, mode='min',log=None):
    temp_line = QgsVectorLayer(f"LineString?crs={crs_authid}", "temp", "memory")
    prov = temp_line.dataProvider()
    feat = QgsFeature()
    feat.setGeometry(line_geom)
    prov.addFeature(feat)
    temp_line.updateExtents()

    points = processing.run("native:pointsalonglines", {
        'INPUT': temp_line,
        'DISTANCE': depth_sampling_interval,
        'OUTPUT': 'memory:points'
    })['OUTPUT']

    sampled = processing.run("native:rastersampling", {
        'INPUT': points,
        'RASTERCOPY': dem_layer,
        'COLUMN_PREFIX': 'z_',
        'OUTPUT': 'memory:sampled'
    })['OUTPUT']

    min_depth = None
    sum_depth = 0
    count = 0

    for f in sampled.getFeatures():
        val = f['z_1']
        if val is not None:
            val = abs(val)
            sum_depth += val
            count += 1
            if min_depth is None or val < min_depth:
                min_depth = val

    if count > 0:
        return min_depth if mode == 'min' else (sum_depth / count)

    stats = processing.run("qgis:rasterlayerstatistics", {
        'INPUT': dem_layer,
        'BAND': 1,
        'OUTPUT_HTML_FILE': 'TEMPORARY_OUTPUT'
    })
    mean_val = abs(stats['MEAN']) if 'MEAN' in stats else 5
    if log:
        log("⚠️ No depth values sampled for line. Using DEM mean value as fallback.")
    else: 
        print("⚠️ No depth values sampled for line. Using DEM mean value or 5 m as fallback.")
    return mean_val

def compute_swath(depth, angle_deg=120, overlap=0.3):
    swath = 2 * depth * math.tan(math.radians(angle_deg / 2))
    return swath, swath * (1 - overlap)
