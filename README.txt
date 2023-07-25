Update Tool to Maintain Existing Asset Information on IP-Spatial Sharepoint Site.

What:
- copies files for network drives to sharepoint site
- creates a version of layer files without Integer64 compatible with older versions of QGIS
- logs actions in log_summary.log

How:
- powershell script finds latest version of QGIS installed and runs python script inside QGIS environment
- right-click on run.ps1 and select 'Run with Powershell'

When:
- manually fired