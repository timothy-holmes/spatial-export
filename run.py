import json
import logging
import logging.config
import os
from packaging import version
import shutil
import stat
import subprocess
import sys


class NetworkError(Exception):
    pass

## logging module
cwd = os.path.dirname(__file__)
logging.config.dictConfig(
    {
        "version": 1,
        "formatters": {
            "summary": {
                "format": "%(asctime)s | %(message)s",
                "datefmt": "%Y-%m-%d-%H%M%S",
                "style": "%"
            },
            "log": {
                "format": "%(asctime)s | %(relativeCreated)i | %(levelname)s | %(filename)s:%(lineno)d | %(funcName)s | %(message)s",
                "datefmt": "%Y-%m-%d-%H%M%S",
                "style": "%"
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "log",
                "level": "DEBUG",
                "filters": [],
                "stream": "ext://sys.stdout"
            },
            "summary": {
                "class": "logging.handlers.TimedRotatingFileHandler",
                "when": "W4",
                "formatter": "summary",
                "level": "INFO",
                "filename": f"{cwd}/log_summary.log"
            },
            "log_file": {
                "class": "logging.handlers.TimedRotatingFileHandler",
                "when": "W4",
                "formatter": "log",
                "level": "DEBUG",
                "filename": f"{cwd}/log_file.log"
            }
        },
        "root": {
            "handlers": ["console", "log_file", "summary"],
            "level": "DEBUG"
        }
    }
)
# class Logger:
#     @staticmethod
#     def alt_print(*args):
#         print(*args)

# for level in ['debug', 'info','warning','error','critical','exception']:
#     setattr(Logger,level,Logger.alt_print)

# logging = Logger()

def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logging.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = handle_exception

# Helper functions
def is_file_deletable(d_file):
    file_dirname = os.path.dirname(d_file)               
    if os.access(file_dirname, os.W_OK | os.X_OK):
        try:
            file = open(d_file, 'ab')
            file.close()
            return True
        except OSError:
            pass
    return False

def delete_file(d_file):
    if os.path.exists(d_file):
        try:
            os.remove(d_file)
        except OSError as e:
            logging.error(e)
            return False
        else:
            return True

def drop_fields_Integer64(input, layer, layer_obj):
    fields_to_keep = [
        field.name() for field in layer_obj.fields() 
        if not field.typeName() in ['Integer64'] # TODO: is this the only unsupported field type?
    ]
    if fields_to_keep and layer['source_file_format'] == 'tab':
        return processing.run(
            "native:retainfields", 
            {
                'INPUT': input,
                'COLUMN': fields_to_keep,
                'OUTPUT': 'TEMPORARY_OUTPUT'
            }
        )
    else:
        return None


# Pre-start checks (5)
# 1. CWD is IP - Spatial\Input\Existing Assets\Update Tool or thereabouts
is_correct_tool_directory = all([
    "Existing Assets" in cwd,
    'IP - Spatial' in cwd,
    os.path.exists(os.path.join(cwd,"../","Central Region")),
    os.path.exists(os.path.join(cwd,"../","Western Region"))
])
if not is_correct_tool_directory:
    # TODO: create custom exception for this error
    raise Exception(f"Run this script from the Existing Asset folder on the 'IP - Spatial' sharepoint site. Detected cwd={cwd}")

# 2. Networks are available
is_network_connected = all([
    os.path.exists("//citywestwater.com.au/data/PCCommon/"),
    os.path.exists("//wro-gisapp/MunsysExport/")
])
if not is_network_connected: 
    raise NetworkError('Network drive(s) is not available. Confirm connection to VPN.')

# 3. Config.json is present
is_file_list_available = os.path.exists(file_list_path := os.path.join(cwd,"config.json"))
if is_file_list_available:
    # Load file list
    with open(file_list_path, 'r') as file_list_file:
        file_list = json.load(file_list_file)
        settings, files = file_list['settings'], file_list['files']
else:
    raise Exception('File list does not exist. Please seek help.')

# 4. Inside QGIS/OS4GEOW environment
# TODO: add condition to account difference in interpreter path between LTR vs spot release
using_qgis_interpreter = 'QGIS' in sys.executable
if not using_qgis_interpreter:
    raise Exception('Run this script from the QGIS/OS4GEOW environment.')

# Initialize the QGIS application, load processing module
from qgis.core import QgsVectorLayer, QgsApplication, QgsProcessingException
qgs = QgsApplication([], False)
qgs.initQgis()
sys.path.append(
    os.path.join(
        os.path.dirname(sys.executable),
        '../apps/qgis-ltr/python/plugins'
    )
)
sys.path.append(
    os.path.join(
        os.path.dirname(sys.executable),
        '../apps/qgis/python/plugins'
    )
)
try:
    import processing
    from processing.core.Processing import Processing
    Processing.initialize()
except ModuleNotFoundError:
    logging.error(f"Couldn't import QGIS processing module. {[p for p in sys.path if 'QGIS' in p]}")

# 5. GDAL version >= 3.28.6
try:
    import osgeo.gdal
    assert version.parse(osgeo.gdal.__version__) >= version.parse('3.7')
except AssertionError:
    raise Exception(f"GDAL version {osgeo.gdal.__version__} detected. Please update to QGIS 3.28.7+ (LTR) or 3.30.3+ (Spot Release).")


# Load the layers and copy the files
for layer in files:
    layer_file_paths = [
        (
            (settings['source_path'][layer['region']]
                .format(
                    source_service=layer['destination_service'],
                    source_file_name=layer['source_file_name'],
                    extension=ext,
                )
            ),
            (settings['destination_path'][layer['region']]
                .format(
                    cwd=cwd,
                    destination_service=layer['destination_service'],
                    destination_file_name=layer['source_file_name'],
                    extension=ext,
                )
            )
        ) for ext in settings['format_extensions'][layer['source_file_format']]
    ]

    # Check if layer can be deleted
    is_deletable = all([is_file_deletable(d_file) for _, d_file in layer_file_paths])
    if not is_deletable:
        logging.warning(f"File(s) cannot be deleted: {layer_file_paths}")
        continue

    layer_obj = QgsVectorLayer(
        layer_file_paths[0][0], 
        layer['source_file_name'], 
        'ogr'
    )

    # Check if the layer is valid when loaded
    if not layer_obj.isValid():
        logging.warning(f"{layer['source_file_name']}: Invalid layer")
        continue

    # Assume processing will be successful
    for _, d_file in layer_file_paths:
        if delete_file(d_file):
            logging.debug(f"{layer['source_file_name']}: Deleted {d_file}")
        else:
            logging.critical(f"{layer['source_file_name']}: Failed to delete {d_file}")
            continue

    # Doing processing
    input = layer_file_paths[0][0]
    result = None
    operations = layer['operations'] or ['copy_layer']
    
    for i, operation in enumerate(operations):
        # use temp folder for intermediate outputs
        output = 'TEMPORARY_OUTPUT' if i+1 < len(operations) else layer_file_paths[0][1]

        # match operation:
            # case "drop_fields.Integer64":
        if operation == "drop_fields.Integer64":
            alg_name = "native:deletecolumn"
            kwargs = {
                'INPUT': input,
                'COLUMN': [field.name() for field in layer_obj.fields() if field.typeName() in ['Integer64']],
                'OUTPUT': output
            }
        # case "refactor_PIPE_DIA":
        elif operation == "refactor_PIPE_DIA":
            alg_name = "native:fieldcalculator"
            kwargs = {
                'INPUT': input,
                'FIELD_NAME':'PIPE_DIA_INT',
                'FIELD_TYPE':1,
                'FIELD_LENGTH':0,
                'FIELD_PRECISION':0,
                'FORMULA':'if(to_int(left("Name",5)),to_int(left("Name",5)),1)',
                'OUTPUT': output
            }
        # case "copy_layer":
        elif operation == "copy_layer":
            alg_name = "native:retainfields"
            kwargs = {
                'INPUT': input,
                'FIELDS': [field.name() for field in layer_obj.fields()],
                'OUTPUT': output
            }
        else:
            raise Exception(f"Unknown operation: {operation}")

        try:
            result = processing.run(alg_name, kwargs)
        except QgsProcessingException as e:
            logging.error(f"{layer['source_file_name']}: {e}")
            continue
        else:
            logging.debug(f"{layer['source_file_name']}: Ran {alg_name}, {result=}")

        if result:
            input = result['output']

# Exit the QGIS application
qgs.exitQgis()

# make all files read-only
for root, dirs, files in os.walk(os.path.abspath(os.path.join(cwd,'../'))):
    file_count = 0
    if root == cwd:
        continue # skip 'Update Tool' directory
    for file in files:
        file_path = os.path.join(root, file)
        if not os.access(file_path, os.W_OK):
            # Skip read-only files
            continue
        file_permissions = os.stat(file_path).st_mode
        if not stat.S_ISDIR(file_permissions):
            # Check if the path is a file
            os.chmod(file_path, file_permissions | stat.S_IREAD)
            file_count += 1
            logging.debug(f'{file}, set to read-only {os.stat(file_path).st_mode}')