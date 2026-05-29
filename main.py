import tkinter as tk
from tkinter import ttk
import math
import re
from nmea import gprmc, gpgga, gpvtg, gpgll, dead_reckon

BG      = "#1e1e2e"
FG      = "#cdd6f4"
ACCENT  = "#89b4fa"
GREEN   = "#a6e3a1"
RED     = "#f38ba8"
SURFACE = "#313244"
MUTED   = "#6c7086"
YELLOW  = "#f9e2af"
PURPLE  = "#cba6f7"
OVERLAY = "#45475a"
BLACK   = "#11111b"

MAX_TRAIL = 500   # cap trail length so set_path stays fast


def _dms_to_decimal(value, is_lat=True):
    text = value.strip().upper().replace(" ", "")
    match = re.fullmatch(r"""(\d+(?:\.\d+)?)°(\d+(?:\.\d+)?)'(\d+(?:\.\d+)?)"([NSEW])""", text)
    if not match:
        return float(value)

    degrees, minutes, seconds, direction = match.groups()
    decimal = float(degrees) + float(minutes) / 60 + float(seconds) / 3600
    if direction in ("S", "W"):
        decimal *= -1

    limit = 90 if is_lat else 180
    if abs(decimal) > limit:
        raise ValueError("coordinate out of range")
    return decimal


def _decimal_to_dms(value, is_lat=True):
    direction = ("N" if value >= 0 else "S") if is_lat else ("E" if value >= 0 else "W")
    absolute = abs(value)
    degrees = int(absolute)
    minutes_float = (absolute - degrees) * 60
    minutes = int(minutes_float)
    seconds = (minutes_float - minutes) * 60

    if round(seconds, 1) >= 60:
        seconds = 0
        minutes += 1
    if minutes >= 60:
        minutes = 0
        degrees += 1

    return f'{degrees}°{minutes:02d}\'{seconds:04.1f}"{direction}'


def _btn(parent, text, cmd, bg=OVERLAY, fg=FG, font=None, **kw):
    b = tk.Button(parent, text=text, command=cmd,
                  bg=bg, fg=fg, activebackground=MUTED, activeforeground=FG,
                  relief="flat", cursor="hand2",
                  font=font or ("Segoe UI", 10), **kw)
    b.bind("<Enter>", lambda e, _b=b, _bg=bg: _b.config(bg=MUTED))
    b.bind("<Leave>", lambda e, _b=b, _bg=bg: _b.config(bg=_bg))
    return b


# ── Map Window ─────────────────────────────────────────────────────────────

class MapWindow(tk.Toplevel):
    def __init__(self, master, lat, lon):
        super().__init__(master)
        self.title("Ship Live Tracking Map")
        self.configure(bg=BG)
        self.geometry("960x720")
        self.minsize(700, 500)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._trail   = []
        self._marker  = None
        self._path    = None
        self._ship_icon = None
        self._alive   = True
        self._map_ready = False
        self._auto_center = tk.BooleanVar(value=True)
        self._last_lat = lat
        self._last_lon = lon

        try:
            from tkintermapview import TkinterMapView
            self._build_ui(TkinterMapView, lat, lon)
        except ImportError:
            self._no_lib_ui("tkintermapview not found", "pip install tkintermapview")
        except Exception as exc:
            self._no_lib_ui("Map could not be loaded", str(exc))

    # ── UI build ────────────────────────────────────────────

    def _build_ui(self, TkinterMapView, lat, lon):
        # ── Top bar ──
        top = tk.Frame(self, bg=SURFACE, padx=12, pady=8)
        top.pack(fill=tk.X, side=tk.TOP)

        self._info_lbl = tk.Label(
            top,
            text="Lat: --  |  Lon: --  |  COG: ---.-  |  SOG: --.-- kts  |  Trail: 0 pts",
            bg=SURFACE, fg=FG, font=("Courier New", 11), anchor="w")
        self._info_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

        btn_row = tk.Frame(top, bg=SURFACE)
        btn_row.pack(side=tk.RIGHT)
        tk.Checkbutton(btn_row, text="Auto-center", variable=self._auto_center,
                       bg=SURFACE, fg=FG, selectcolor=OVERLAY,
                       activebackground=SURFACE, activeforeground=FG,
                       font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 8))
        _btn(btn_row, "Center", self._center_ship, padx=8, pady=3).pack(side=tk.LEFT, padx=4)
        _btn(btn_row, "Clear Trail", self._clear_trail, padx=8, pady=3).pack(side=tk.LEFT, padx=4)

        # Tile server switcher
        tile_row = tk.Frame(top, bg=SURFACE)
        tile_row.pack(side=tk.RIGHT, padx=(0, 16))
        tk.Label(tile_row, text="Tiles:", bg=SURFACE, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self._tile_var = tk.StringVar(value="Street")
        for label in ("Street", "Satellite", "Dark"):
            tk.Radiobutton(tile_row, text=label, variable=self._tile_var, value=label,
                           command=self._switch_tiles,
                           bg=SURFACE, fg=FG, selectcolor=OVERLAY,
                           activebackground=SURFACE, activeforeground=FG,
                           font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=2)

        # ── Map widget ──
        self._map = TkinterMapView(self, corner_radius=0)
        self._map.pack(fill=tk.BOTH, expand=True, side=tk.TOP)
        self._map.set_position(lat, lon)
        self._map.set_zoom(13)
        self._map_ready = True

        # ── HUD overlay (placed inside map frame) ──
        hud = tk.Frame(self._map, bg=SURFACE, padx=10, pady=8,
                       highlightthickness=1, highlightbackground=MUTED)
        hud.place(relx=0.01, rely=0.99, anchor="sw")

        tk.Label(hud, text="SHIP HUD", bg=SURFACE, fg=ACCENT,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self._hud_cog = tk.Label(hud, text="COG   ---.- deg",
                                  bg=SURFACE, fg=YELLOW, font=("Courier New", 10, "bold"))
        self._hud_cog.pack(anchor="w")
        self._hud_sog = tk.Label(hud, text="SOG    --.- kts",
                                  bg=SURFACE, fg=GREEN, font=("Courier New", 10, "bold"))
        self._hud_sog.pack(anchor="w")
        tk.Frame(hud, bg=MUTED, height=1).pack(fill=tk.X, pady=4)
        self._hud_lat = tk.Label(hud, text="LAT  --------",
                                  bg=SURFACE, fg=FG, font=("Courier New", 9))
        self._hud_lat.pack(anchor="w")
        self._hud_lon = tk.Label(hud, text="LON  --------",
                                  bg=SURFACE, fg=FG, font=("Courier New", 9))
        self._hud_lon.pack(anchor="w")
        tk.Frame(hud, bg=MUTED, height=1).pack(fill=tk.X, pady=4)
        self._hud_trail = tk.Label(hud, text="TRAIL  0 pts",
                                    bg=SURFACE, fg=MUTED, font=("Courier New", 9))
        self._hud_trail.pack(anchor="w")

    def _no_lib_ui(self, title, message):
        f = tk.Frame(self, bg=BG)
        f.pack(expand=True)
        tk.Label(f, text=title, bg=BG, fg=RED,
                 font=("Segoe UI", 14, "bold")).pack(pady=(30, 8))
        tk.Label(f, text=message, bg=BG, fg=YELLOW,
                 font=("Courier New", 12), wraplength=760).pack()
        self._fallback_lbl = tk.Label(
            f,
            text=f"Lat: {self._last_lat:+.6f}  |  Lon: {self._last_lon:+.6f}",
            bg=BG, fg=FG, font=("Courier New", 11))
        self._fallback_lbl.pack(pady=(18, 0))
        _btn(f, "Close", self._on_close, padx=12, pady=6).pack(pady=20)

    # ── Public update called from main tick ─────────────────

    def update_ship(self, lat, lon, course, speed):
        if not self._alive:
            return
        self._last_lat, self._last_lon = lat, lon

        self._trail.append((lat, lon))
        if len(self._trail) > MAX_TRAIL:
            self._trail = self._trail[-MAX_TRAIL:]

        n = len(self._trail)

        if not self._map_ready:
            if hasattr(self, "_fallback_lbl"):
                self._fallback_lbl.config(
                    text=(f"Lat: {lat:+.6f}  |  Lon: {lon:+.6f}  |  "
                          f"COG: {course:05.1f} deg  |  SOG: {speed:.2f} kts"))
            return

        # Top bar
        self._info_lbl.config(
            text=(f"Lat: {lat:+.6f}  |  Lon: {lon:+.6f}  |  "
                  f"COG: {course:05.1f} deg  |  SOG: {speed:.2f} kts  |  Trail: {n} pts"))

        # HUD
        self._hud_cog.config(text=f"COG   {course:05.1f} deg")
        self._hud_sog.config(text=f"SOG    {speed:5.2f} kts")
        self._hud_lat.config(text=f"LAT  {lat:+.6f}")
        self._hud_lon.config(text=f"LON  {lon:+.6f}")
        self._hud_trail.config(text=f"TRAIL  {n} pts")

        # Marker
        if self._marker:
            self._marker.delete()
        self._ship_icon = self._make_ship_icon(course)
        self._marker = self._map.set_marker(
            lat, lon,
            text=f"{course:.0f} deg | {speed:.1f} kts",
            icon=self._ship_icon,
            icon_anchor="center",
            text_color=FG)

        # Trail path
        if n >= 2:
            if self._path:
                self._path.delete()
            self._path = self._map.set_path(list(self._trail),
                                             color=ACCENT, width=2)

        # Auto-center
        if self._auto_center.get():
            self._map.set_position(lat, lon)

    def _make_ship_icon(self, course):
        from PIL import Image, ImageDraw, ImageTk

        size = 44
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        hull = [(22, 4), (34, 31), (22, 39), (10, 31)]
        draw.polygon(hull, fill=ACCENT, outline=BLACK)
        draw.line((22, 8, 22, 35), fill=BLACK, width=2)
        draw.polygon([(22, 4), (28, 25), (22, 31), (16, 25)],
                     fill=GREEN, outline=BLACK)
        draw.ellipse((17, 25, 27, 35), fill=RED, outline=BLACK)

        rotated = img.rotate(-course, resample=Image.Resampling.BICUBIC)
        return ImageTk.PhotoImage(rotated)

    # ── Controls ────────────────────────────────────────────

    def _center_ship(self):
        if not self._map_ready:
            return
        self._map.set_position(self._last_lat, self._last_lon)

    def _clear_trail(self):
        self._trail.clear()
        if self._path:
            self._path.delete()
            self._path = None
        if self._map_ready:
            self._hud_trail.config(text="TRAIL  0 pts")

    def _switch_tiles(self):
        if not self._map_ready:
            return
        servers = {
            "Street":    "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
            "Satellite": "https://mt0.google.com/vt/lyrs=s&hl=en&x={x}&y={y}&z={z}&s=Ga",
            "Dark":      "https://tiles.stadiamaps.com/tiles/alidade_smooth_dark/{z}/{x}/{y}.png",
        }
        url = servers.get(self._tile_var.get(), servers["Street"])
        self._map.set_tile_server(url, max_zoom=22)

    def _on_close(self):
        self._alive = False
        self.destroy()

    @property
    def alive(self):
        return self._alive


# ── Main Simulator Window ──────────────────────────────────────────────────

class NMEASimulator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("NMEA GPS Ship Simulator")
        self.configure(bg=BG)
        self.geometry("1040x700")
        self.minsize(900, 600)

        self._lat = _dms_to_decimal('9°58\'11.7"N', is_lat=True)
        self._lon = _dms_to_decimal('76°13\'46.9"E', is_lat=False)
        self._course = 124.0
        self._speed  = 10.0
        self._running  = False
        self._after_id = None
        self._interval_ms = 1000
        self._map_win = None

        self._build_ui()

    # ── Layout ─────────────────────────────────────────────

    def _build_ui(self):
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill=tk.X, padx=16, pady=(14, 6))
        tk.Label(hdr, text="NMEA GPS Ship Simulator",
                 bg=BG, fg=ACCENT, font=("Segoe UI", 15, "bold")).pack(side=tk.LEFT)

        body = tk.Frame(self, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 16))

        left = tk.Frame(body, bg=SURFACE, padx=14, pady=12, width=330)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left.pack_propagate(False)
        self._build_controls(left)

        right = tk.Frame(body, bg=SURFACE, padx=14, pady=12)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self._build_output(right)

    def _section(self, parent, title):
        tk.Label(parent, text=title, bg=SURFACE, fg=ACCENT,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(12, 2))
        tk.Frame(parent, bg=MUTED, height=1).pack(fill=tk.X, pady=(0, 8))

    def _build_controls(self, p):
        # Position
        self._section(p, "POSITION")
        pf = tk.Frame(p, bg=SURFACE)
        pf.pack(fill=tk.X)

        tk.Label(pf, text="Latitude :", bg=SURFACE, fg=FG,
                 font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w", pady=3)
        self._lat_var = tk.StringVar(value=_decimal_to_dms(self._lat, is_lat=True))
        tk.Entry(pf, textvariable=self._lat_var, width=18,
                 bg=OVERLAY, fg=FG, insertbackground=FG,
                 relief="flat", font=("Courier New", 10)).grid(row=0, column=1, padx=(8, 0), pady=3)

        tk.Label(pf, text="Longitude:", bg=SURFACE, fg=FG,
                 font=("Segoe UI", 10)).grid(row=1, column=0, sticky="w", pady=3)
        self._lon_var = tk.StringVar(value=_decimal_to_dms(self._lon, is_lat=False))
        tk.Entry(pf, textvariable=self._lon_var, width=18,
                 bg=OVERLAY, fg=FG, insertbackground=FG,
                 relief="flat", font=("Courier New", 10)).grid(row=1, column=1, padx=(8, 0), pady=3)

        _btn(pf, "Apply Position", self._apply_pos, padx=10, pady=4).grid(
            row=2, column=1, sticky="e", pady=(6, 0))

        # Navigation
        self._section(p, "NAVIGATION")

        cr = tk.Frame(p, bg=SURFACE)
        cr.pack(fill=tk.X, pady=(0, 2))
        tk.Label(cr, text="Course", bg=SURFACE, fg=FG, font=("Segoe UI", 10)).pack(side=tk.LEFT)
        self._course_lbl = tk.Label(cr, text=f"  {self._course:05.1f} deg", bg=OVERLAY, fg=YELLOW,
                                    font=("Courier New", 11, "bold"), padx=6, pady=2)
        self._course_lbl.pack(side=tk.RIGHT)

        self._course_var = tk.DoubleVar(value=self._course)
        tk.Scale(p, from_=0, to=359.9, variable=self._course_var,
                 orient=tk.HORIZONTAL, showvalue=False,
                 bg=SURFACE, fg=FG, troughcolor=OVERLAY,
                 activebackground=ACCENT, highlightthickness=0,
                 command=self._on_course).pack(fill=tk.X, pady=(0, 10))

        sr = tk.Frame(p, bg=SURFACE)
        sr.pack(fill=tk.X, pady=(0, 2))
        tk.Label(sr, text="Speed", bg=SURFACE, fg=FG, font=("Segoe UI", 10)).pack(side=tk.LEFT)
        self._speed_lbl = tk.Label(sr, text=f"  {self._speed:5.1f} kts", bg=OVERLAY, fg=YELLOW,
                                   font=("Courier New", 11, "bold"), padx=6, pady=2)
        self._speed_lbl.pack(side=tk.RIGHT)

        self._speed_var = tk.DoubleVar(value=self._speed)
        tk.Scale(p, from_=0, to=30, variable=self._speed_var,
                 orient=tk.HORIZONTAL, showvalue=False, resolution=0.1,
                 bg=SURFACE, fg=FG, troughcolor=OVERLAY,
                 activebackground=ACCENT, highlightthickness=0,
                 command=self._on_speed).pack(fill=tk.X, pady=(0, 6))

        # Compass
        self._compass = tk.Canvas(p, width=160, height=180, bg=SURFACE, highlightthickness=0)
        self._compass.pack(pady=(4, 0))
        self._draw_compass(self._course)

        # Options
        self._section(p, "OPTIONS")
        of = tk.Frame(p, bg=SURFACE)
        of.pack(fill=tk.X)

        self._auto_var = tk.BooleanVar(value=True)
        tk.Checkbutton(of, text="Auto-advance position",
                       variable=self._auto_var, bg=SURFACE, fg=FG,
                       selectcolor=OVERLAY, activebackground=SURFACE,
                       activeforeground=FG, font=("Segoe UI", 9)).pack(anchor="w")

        ir = tk.Frame(of, bg=SURFACE)
        ir.pack(fill=tk.X, pady=(6, 0))
        tk.Label(ir, text="Interval:", bg=SURFACE, fg=FG, font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self._int_var = tk.StringVar(value="1")
        cb = ttk.Combobox(ir, textvariable=self._int_var,
                          values=["0.5", "1", "2", "5"], width=5, state="readonly")
        cb.pack(side=tk.LEFT, padx=6)
        cb.bind("<<ComboboxSelected>>", self._on_interval)
        tk.Label(ir, text="sec", bg=SURFACE, fg=FG, font=("Segoe UI", 9)).pack(side=tk.LEFT)

        # Start / Stop
        self._btn = tk.Button(p, text="  START  ", command=self._toggle,
                              bg=GREEN, fg="#1e1e2e", activebackground="#b6f3b1",
                              activeforeground="#1e1e2e", relief="flat",
                              font=("Segoe UI", 12, "bold"), cursor="hand2", pady=8)
        self._btn.pack(fill=tk.X, pady=(14, 0))

        # Open Map button
        _btn(p, "Open Map Window", self._open_map, padx=10, pady=6).pack(fill=tk.X, pady=(6, 0))

        # Live coords
        self._section(p, "LIVE POSITION")
        self._live_lbl = tk.Label(p, text="Lat:  --\nLon:  --",
                                  bg=OVERLAY, fg=GREEN, font=("Courier New", 10),
                                  justify="left", anchor="w", padx=8, pady=6)
        self._live_lbl.pack(fill=tk.X)

    def _build_output(self, p):
        hf = tk.Frame(p, bg=SURFACE)
        hf.pack(fill=tk.X, pady=(0, 6))
        tk.Label(hf, text="NMEA OUTPUT", bg=SURFACE, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)
        _btn(hf, "Clear", self._clear, padx=8, pady=3).pack(side=tk.RIGHT, padx=(4, 0))
        _btn(hf, "Copy Last Block", self._copy_last, padx=8, pady=3).pack(side=tk.RIGHT)

        leg = tk.Frame(p, bg=SURFACE)
        leg.pack(fill=tk.X, pady=(0, 6))
        for color, label in [(ACCENT, "GPRMC"), (GREEN, "GPGGA"),
                             (YELLOW, "GPVTG"), (PURPLE, "GPGLL")]:
            tk.Label(leg, text=f" {label} ", bg=SURFACE, fg=color,
                     font=("Courier New", 9, "bold")).pack(side=tk.LEFT)

        tf = tk.Frame(p, bg=SURFACE)
        tf.pack(fill=tk.BOTH, expand=True)
        tf.grid_rowconfigure(0, weight=1)
        tf.grid_columnconfigure(0, weight=1)

        self._out = tk.Text(tf, bg=BLACK, fg=GREEN, font=("Courier New", 10),
                            insertbackground=FG, selectbackground=ACCENT,
                            relief="flat", wrap=tk.NONE,
                            state=tk.DISABLED, padx=8, pady=6)
        self._out.grid(row=0, column=0, sticky="nsew")

        vsb = tk.Scrollbar(tf, orient=tk.VERTICAL,   command=self._out.yview,
                           bg=SURFACE, troughcolor=OVERLAY)
        vsb.grid(row=0, column=1, sticky="ns")
        xsb = tk.Scrollbar(tf, orient=tk.HORIZONTAL, command=self._out.xview,
                           bg=SURFACE, troughcolor=OVERLAY)
        xsb.grid(row=1, column=0, sticky="ew")
        self._out.configure(yscrollcommand=vsb.set, xscrollcommand=xsb.set)

        self._out.tag_configure("rmc", foreground=ACCENT)
        self._out.tag_configure("gga", foreground=GREEN)
        self._out.tag_configure("vtg", foreground=YELLOW)
        self._out.tag_configure("gll", foreground=PURPLE)
        self._out.tag_configure("sep", foreground=OVERLAY)

    # ── Compass ────────────────────────────────────────────

    def _draw_compass(self, course: float):
        c = self._compass
        c.delete("all")
        cx, cy, r = 80, 78, 62

        c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=BLACK, outline=MUTED, width=2)

        for deg in range(0, 360, 10):
            rad = math.radians(deg - 90)
            inner = r - (9 if deg % 30 == 0 else 4)
            x1 = cx + inner * math.cos(rad)
            y1 = cy + inner * math.sin(rad)
            x2 = cx + r  * math.cos(rad)
            y2 = cy + r  * math.sin(rad)
            c.create_line(x1, y1, x2, y2, fill=MUTED if deg % 30 else OVERLAY)

        for label, deg in [("N", 0), ("E", 90), ("S", 180), ("W", 270)]:
            rad = math.radians(deg - 90)
            x = cx + (r - 18) * math.cos(rad)
            y = cy + (r - 18) * math.sin(rad)
            c.create_text(x, y, text=label,
                          fill=RED if label == "N" else FG,
                          font=("Segoe UI", 8, "bold"))

        rad = math.radians(course - 90)
        tip_x  = cx + (r - 10) * math.cos(rad)
        tip_y  = cy + (r - 10) * math.sin(rad)
        tail_x = cx - 20 * math.cos(rad)
        tail_y = cy - 20 * math.sin(rad)
        c.create_line(tail_x, tail_y, tip_x, tip_y,
                      fill=ACCENT, width=3, arrow=tk.LAST, arrowshape=(12, 14, 4))
        c.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, fill=ACCENT, outline="")
        c.create_text(cx, cy + r + 16, text=f"{course:.1f} deg",
                      fill=YELLOW, font=("Courier New", 9, "bold"))

    # ── Callbacks ──────────────────────────────────────────

    def _on_course(self, val):
        self._course = float(val)
        self._course_lbl.config(text=f"  {self._course:05.1f} deg")
        self._draw_compass(self._course)

    def _on_speed(self, val):
        self._speed = float(val)
        self._speed_lbl.config(text=f"  {self._speed:5.1f} kts")

    def _on_interval(self, _=None):
        try:
            self._interval_ms = int(float(self._int_var.get()) * 1000)
        except ValueError:
            self._interval_ms = 1000

    def _apply_pos(self):
        try:
            self._lat = _dms_to_decimal(self._lat_var.get(), is_lat=True)
            self._lon = _dms_to_decimal(self._lon_var.get(), is_lat=False)
            self._lat_var.set(_decimal_to_dms(self._lat, is_lat=True))
            self._lon_var.set(_decimal_to_dms(self._lon, is_lat=False))
        except ValueError:
            pass

    def _open_map(self):
        if self._map_win and self._map_win.alive:
            self._map_win.lift()
            return
        self._map_win = MapWindow(self, self._lat, self._lon)

    def _toggle(self):
        self._running = not self._running
        if self._running:
            self._apply_pos()
            self._btn.config(text="  STOP  ", bg=RED, activebackground="#f49aaa")
            self._tick()
        else:
            self._btn.config(text="  START  ", bg=GREEN, activebackground="#b6f3b1")
            if self._after_id:
                self.after_cancel(self._after_id)

    def _tick(self):
        if not self._running:
            return

        if self._auto_var.get() and self._speed > 0:
            dt = self._interval_ms / 1000
            self._lat, self._lon = dead_reckon(
                self._lat, self._lon, self._speed, self._course, dt)
            self._lat_var.set(_decimal_to_dms(self._lat, is_lat=True))
            self._lon_var.set(_decimal_to_dms(self._lon, is_lat=False))

        rmc = gprmc(self._lat, self._lon, self._speed, self._course)
        gga = gpgga(self._lat, self._lon)
        vtg = gpvtg(self._course, self._speed)
        gll = gpgll(self._lat, self._lon)

        self._live_lbl.config(
            text=f"Lat:  {self._lat:+.6f}\nLon:  {self._lon:+.6f}")

        self._out.config(state=tk.NORMAL)
        self._out.insert(tk.END, rmc + "\n", "rmc")
        self._out.insert(tk.END, gga + "\n", "gga")
        self._out.insert(tk.END, vtg + "\n", "vtg")
        self._out.insert(tk.END, gll + "\n", "gll")
        self._out.insert(tk.END, "-" * 72 + "\n", "sep")
        self._out.see(tk.END)
        self._out.config(state=tk.DISABLED)

        # Push to map window if open
        if self._map_win and self._map_win.alive:
            self._map_win.update_ship(self._lat, self._lon, self._course, self._speed)

        self._after_id = self.after(self._interval_ms, self._tick)

    def _clear(self):
        self._out.config(state=tk.NORMAL)
        self._out.delete(1.0, tk.END)
        self._out.config(state=tk.DISABLED)

    def _copy_last(self):
        text = self._out.get(1.0, tk.END)
        blocks = [b.strip() for b in text.split("-" * 72) if b.strip()]
        if blocks:
            self.clipboard_clear()
            self.clipboard_append(blocks[-1])


if __name__ == "__main__":
    app = NMEASimulator()
    app.mainloop()
