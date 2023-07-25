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
            "handlers": ["console", "log_file", "summary_file"],
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
def delete_file(d_file):
    if os.path.exists(d_file):
        try:
            os.remove(d_file)
        except OSError as e:
            logging.error(e)
        else:
            logging.debug(f"Deleted file: {d_file}")

def copy_or_overwrite(s_file,d_file):
    delete_file(d_file)
    try:
        shutil.copy(s_file, d_file)
    except Exception as e:
        logging.error(e)
    else:
        logging.debug(f"Copied file: {s_file} -> {d_file}")

def append_x32_suffix(d_file):
    return "".join([d_file[:-4],'x32','.tab'])

# Pre-start checks (4)
# 1. CWD is IP - Spatial\Input\Existing Assets\Update Tool or thereabouts
is_correct_tool_directory = all([
    "Existing Assets" in cwd,
    'IP - Spatial' in cwd,
    os.path.exists(
        os.path.join(
            cwd,
            "../",
            "Central Region"
        )
    ),
])
if not is_correct_tool_directory:
    # TODO: create custom exception for this error
    raise Exception(f"Run this script from the Existing Asset folder on the 'IP - Spatial' sharepoint site. Detected cwd={cwd}")

# 2. Networks are available
is_network_connected = all([
    os.path.exists('N:/'), # better to use full server path ie. \\citywestwater.com.au\data\pccommon\
    os.path.exists('A:/')
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
if not using_qgis_interpreter and not ('attemptedToFindInstallationOfQGIS' in sys.argv): # additional argument prevents multi-level recursion
    logging.warning(f'Python interpreter {sys.executable} not inside QGIS/OSGEO4W environment. Will attempt to rerun in QGIS environment.')
    qgis_folders = [f.name for f in os.scandir('C:/Program Files') if f.is_dir() and 'QGIS' in f.name]
    latest_qgis_version = max(qgis_folders, key=lambda x: version.parse(x))
    logging.debug(f'QGIS versions detected ({latest_qgis_version}): {qgis_folders}')

    subp = subprocess.run(
        [
        f"C:/Program Files/{latest_qgis_version}/bin/python-qgis.bat", 
        __file__,
        'attemptedToFindInstallationOfQGIS'
        ], 
        capture_output=True,
        text=True
    )
    logging.info('Subprocess run with result: {subp.stdout}')
    if subp.stderr:
        logging.info('Subprocess error: {subp.stderr}')

# Initialize the QGIS application, load processing module
from qgis.core import QgsVectorLayer, QgsApplication
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

    # Check if the layer is valid when loaded
    layer_obj = QgsVectorLayer(
        layer_file_paths[0][0], 
        layer['source_file_name'], 
        'ogr'
    )

    if layer_obj.isValid():
        # Check for TAB file field types incompatible with QGIS version <= 3.28.6
        fields_to_drop = [
            field.name() for field in layer_obj.fields() 
            if field.typeName() in ['Integer64'] # TODO: is this the only unsupported field type?
        ]
        if fields_to_drop and layer['source_file_format'] == 'tab':
            # drop column(s)
            for _, destination_file in layer_file_paths:
                delete_file(append_x32_suffix(destination_file))
            processing.run(
                "native:deletecolumn", 
                {
                    'INPUT': layer_file_paths[0][0],
                    'COLUMN': fields_to_drop,
                    'OUTPUT': append_x32_suffix(layer_file_paths[0][1])
                }
            )
            logging.info(f"Generated x32 layer: {layer['source_file_name']}x32, {fields_to_drop=}, path={append_x32_suffix(layer_file_paths[0][1])}")

        for source_file, destination_file in layer_file_paths:
            copy_or_overwrite(source_file, destination_file)
        logging.info(f"Copied layer {layer['source_file_name']} without dropped fields")
    else:
        logging.warning(f"Invalid layer: {layer['source_file_name']}")

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

logging.debug(f"Set all files to read-only: {file_count} files modified")

# Exit the QGIS application
qgs.exitQgis()