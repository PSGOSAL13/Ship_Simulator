# NMEA GPS Ship Simulator

A desktop GPS/NMEA simulator built with Python and Tkinter. The application lets you set a vessel position, course, speed, and update interval, then generates live NMEA 0183-style GPS sentences while optionally plotting the simulated vessel on an interactive map.

## Features

- Generate live `$GPRMC`, `$GPGGA`, `$GPVTG`, and `$GPGLL` sentences.
- Edit starting latitude and longitude.
- Control course over ground and speed over ground from the GUI.
- Auto-advance the vessel position using dead reckoning.
- Choose output intervals of `0.5`, `1`, `2`, or `5` seconds.
- View live latitude and longitude in the main window.
- Clear generated output or copy the latest NMEA block.
- Open a live tracking map with:
  - rotating ship marker
  - vessel trail path
  - auto-center toggle
  - manual center button
  - trail clearing
  - street, satellite, and dark tile options
  - map HUD for COG, SOG, position, and trail count

## Project Files

```text
NMEA_Simulator/
+-- main.py      # Tkinter GUI, simulator loop, output panel, and map window
+-- nmea.py      # NMEA sentence builders and dead-reckoning calculation
+-- README.md    # Project description and usage guide
```

## Requirements

- Python 3.10 or newer
- Tkinter, usually included with Python on Windows
- Pillow
- tkintermapview

Install the map/image dependencies with:

```powershell
python -m pip install pillow tkintermapview
```

## How to Run

From the project folder:

```powershell
cd NMEA_Simulator
python main.py
```

## How to Use

1. Enter a starting latitude and longitude, then click `Apply Position`.
2. Set the vessel course and speed using the sliders.
3. Choose whether `Auto-advance position` should be enabled.
4. Select an output interval.
5. Click `START` to begin generating NMEA output.
6. Click `Open Map Window` to view the simulated vessel on the chart.
7. Use `STOP` to pause the simulator.

## NMEA Sentences

The simulator generates:

- `$GPRMC`: recommended minimum GPS data, including position, speed, course, date, and validity.
- `$GPGGA`: GPS fix data, including time, position, fix quality, satellites, and altitude fields.
- `$GPVTG`: course and speed over ground.
- `$GPGLL`: geographic position with UTC time and status.

Each sentence includes a checksum generated from the sentence body.

## Map Notes

The map window uses `tkintermapview`, which loads map tiles from online tile servers. An internet connection is required for fresh map tiles. If the map library is not installed or the map cannot load, the simulator continues generating NMEA output and shows a fallback status window instead of stopping.

## Troubleshooting

If the map button opens a fallback window, install the map dependency:

```powershell
python -m pip install tkintermapview
```

If the map window opens but tiles are blank, check your internet connection or firewall settings. The simulator can still generate NMEA sentences without map tiles.

If Python cannot import Pillow, install it with:

```powershell
python -m pip install pillow
```
