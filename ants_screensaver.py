import tkinter as tk
import ctypes
import math
import random
import time
import sys
import cv2
import numpy as np
import os
import json
from PIL import ImageGrab, ImageTk


def app_dir():
    """Directory for read/write files (config.json, error.log). Next to the .exe
    when frozen by PyInstaller, otherwise next to this source file."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

# Windows API Structures and constants
class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

# Enable DPI awareness to prevent coordinate scaling issues on high-res screens
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2) # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

def get_system_idle_time():
    """Returns the time the system has been idle in seconds."""
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
        millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
        return millis / 1000.0
    return 0.0

def get_cursor_pos():
    """Returns the current mouse cursor position (x, y)."""
    pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

def set_cursor_pos(x, y):
    """Sets the mouse cursor position (x, y)."""
    ctypes.windll.user32.SetCursorPos(int(x), int(y))

# Configuration  ----  EASY-TO-TUNE KNOBS  ----
FPS = 45                  # Target frame rate
DEBUG_MODE = False        # Set to True to see state debug logs
SPEED_SCALE = 0.7         # Global movement speed (lower = slower/calmer; try 0.8-0.85 for faster)
TURN_SPEED = 0.10         # How sharply worker ants turn (lower = smoother/calmer, higher = twitchier)
NEST_SIZE = 1.0           # Nest mound size multiplier (1.0 = default; higher = bigger anthill)
QUEEN_SPEED_MULT = 1.5    # Queen hauls food this many times faster than normal worker carrying
QUEEN_FOOD_SIZE = 100     # On each timed outing the queen forages an irregular chunk roughly this big (px)
QUEEN_FOLLOWERS = 10      # How many workers follow the queen on a foraging outing

# ---- Ant colour palettes (each is a full shade set so any colour looks good) ----
# Keys: base (abdomen), thx (thorax), hd (head), legs (legs/antennae), stripe (highlights)
ANT_PALETTES = {
    "Red":    {"base": "#C62828", "thx": "#E53935", "hd": "#EF5350", "legs": "#880E4F", "stripe": "#FF8A80"},
    "Green":  {"base": "#2E7D32", "thx": "#43A047", "hd": "#66BB6A", "legs": "#1B5E20", "stripe": "#CCFF90"},
    "Blue":   {"base": "#1565C0", "thx": "#1E88E5", "hd": "#42A5F5", "legs": "#0D47A1", "stripe": "#90CAF9"},
    "Purple": {"base": "#6A1B9A", "thx": "#8E24AA", "hd": "#AB47BC", "legs": "#4A148C", "stripe": "#E1BEE7"},
    "Orange": {"base": "#E65100", "thx": "#F57C00", "hd": "#FF9800", "legs": "#BF360C", "stripe": "#FFCC80"},
    "Gold":   {"base": "#D89B32", "thx": "#E5A93C", "hd": "#FFC107", "legs": "#C5881F", "stripe": "#FFE082"},
    "Black":  {"base": "#212121", "thx": "#37474F", "hd": "#546E7A", "legs": "#000000", "stripe": "#90A4AE"},
    "White":  {"base": "#CFD8DC", "thx": "#ECEFF1", "hd": "#FFFFFF", "legs": "#90A4AE", "stripe": "#FFFFFF"},
}
DEFAULT_PALETTE_NAMES = {"worker": "Red", "scout": "Green", "queen": "Gold"}
# Live palettes, overwritten from config.json at startup.
CURRENT_PALETTES = {
    "worker": ANT_PALETTES["Red"],
    "scout": ANT_PALETTES["Green"],
    "queen": ANT_PALETTES["Gold"],
}

# Colors - Vibrant Neon Colors for High Contrast on Dark/Light Screens
COLOR_WORKER = "#FF3333"   # Bright Neon Red (Worker ants)
COLOR_SCOUT = "#39FF14"    # Bright Neon Green (Scout ants)

# Ant State Constants
STATE_SCOUT_WANDERING = "scout_wandering"
STATE_SCOUT_RECRUITING = "scout_recruiting"
STATE_SPAWNING = "spawning"
STATE_SEEKING = "seeking"
STATE_SURROUNDING = "surrounding"
STATE_CARRYING = "carrying"
STATE_SCATTERING = "scattering"

class Ant:
    def __init__(self, start_x, start_y, screen_w, screen_h, is_scout=False, assigned_target=None):
        self.x = start_x
        self.y = start_y
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.is_scout = is_scout
        self.assigned_target = assigned_target
        
        # Physics / Movement
        self.angle = random.uniform(0, 2 * math.pi)
        # Scouts are significantly faster (speed 3.8 to 4.8)
        self.speed = random.uniform(3.8, 4.8) if is_scout else random.uniform(2.2, 3.2)
        self.max_turn_speed = TURN_SPEED # see TURN_SPEED knob at top of file
        self.state = STATE_SCOUT_WANDERING if is_scout else STATE_SPAWNING
        
        # Visual animation parameters
        self.phase = random.uniform(0, 2 * math.pi)
        self.size_scale = random.uniform(1.2, 1.35) if is_scout else random.uniform(0.78, 0.92)
        
        # Surrounding parameters (each worker ant takes a unique slot around the
        # food; orbit_radius is the gap it keeps OUTSIDE the food's edge so it
        # surrounds the item instead of standing on top of it).
        self.orbit_angle = random.uniform(0, 2 * math.pi)
        self.orbit_radius = random.uniform(8.0, 16.0)
        
        # Target coordinate
        self.target_x = start_x
        self.target_y = start_y
        
        # Scout specific manager variables
        self.help_target = None
        self.helper_ant = None
        self.last_waypoint_time = 0

        # Persistent canvas item ids (created once, then moved via coords() for
        # performance instead of being destroyed and recreated every frame).
        self.items = None

    def update(self, app):
        # Frame-rate compensation: movement and animation are scaled by how long
        # the last frame actually took, so ants travel at a constant real-world
        # speed even when many ants on screen lower the frame rate.
        sf = app.speed_factor
        # Update animation phase (leg wiggle stays in sync with actual travel speed)
        self.phase += self.speed * 0.15 * sf * SPEED_SCALE
        
        is_idle = app.is_idle
        nest_x, nest_y = app.scout_spawn_x, app.scout_spawn_y
        
        # State Transitions and Target Selection
        if not is_idle or (not self.is_scout and not self.assigned_target):
            # System active: Scatter off screen immediately
            self.state = STATE_SCATTERING
            self.speed = random.uniform(6.0, 8.5) # Run away quickly!
            # Target is the nearest screen edge
            edges = [
                (-35, self.y),                      # Left
                (self.screen_w + 35, self.y),       # Right
                (self.x, -35),                      # Top
                (self.x, self.screen_h + 35)        # Bottom
            ]
            nearest_edge = min(edges, key=lambda p: (p[0] - self.x)**2 + (p[1] - self.y)**2)
            self.target_x, self.target_y = nearest_edge
        else:
            if self.state == STATE_SCATTERING:
                # Reset speed if transitioned back to idle
                self.state = STATE_SCOUT_WANDERING if self.is_scout else STATE_SEEKING
                self.speed = random.uniform(3.8, 4.8) if self.is_scout else random.uniform(2.2, 3.2)
                
            if self.is_scout:
                # Scout (Green) Manager Logic
                if self.state == STATE_SCOUT_WANDERING:
                    # Validate current locked help target
                    target_valid = False
                    if self.help_target:
                        still_exists = any(t["id"] == self.help_target["id"] for t in app.targets)
                        if still_exists and not self.help_target["carrying"]:
                            target_valid = True
                            
                    if not target_valid:
                        self.help_target = None
                        struggling_targets = [t for t in app.targets if not t["carrying"]]
                        if struggling_targets:
                            # DISPERSAL & PRIORITY SCORING:
                            # Prioritize larger targets and targets that are close to their carrying threshold
                            # Score formula: area_val / (needed_ants + 0.1)
                            weights = []
                            for t in struggling_targets:
                                if t["type"] == "mouse":
                                    threshold = 15
                                else:
                                    area = t["w"] * t["h"]
                                    threshold = min(20, max(2, int(area / 280)))
                                    
                                ants_near = app.target_near_counts.get(t["id"], 0)
                                needed = max(1, threshold - ants_near)
                                
                                area_val = 1225 if t["type"] == "mouse" else (t["w"] * t["h"])
                                score = area_val / (needed + 0.1)
                                weights.append(score)
                                
                            # Dispersed weighted selection: scouts prefer hot/large targets, but choose independently
                            self.help_target = random.choices(struggling_targets, weights=weights, k=1)[0]
                            
                    if self.help_target:
                        # Head directly towards this locked struggling target
                        self.target_x = self.help_target["curr_x"]
                        self.target_y = self.help_target["curr_y"]
                        self.speed = random.uniform(3.8, 4.8)
                        
                        tdx = self.target_x - self.x
                        tdy = self.target_y - self.y
                        tdist_sq = tdx**2 + tdy**2
                        
                        # Compare squared distance (60.0^2 = 3600.0)
                        if tdist_sq < 3600.0:
                            helper = self.find_nearest_available_worker(app, self.help_target)
                            if helper:
                                self.state = STATE_SCOUT_RECRUITING
                                self.helper_ant = helper
                                self.speed = 5.8 # Dash to recruit helper
                            else:
                                self.help_target = None
                    else:
                        # Fallback to random wander
                        dx = self.target_x - self.x
                        dy = self.target_y - self.y
                        dist_sq = dx**2 + dy**2
                        
                        if dist_sq < 1600.0 or time.time() - self.last_waypoint_time > 6.0: # 40.0^2 = 1600.0
                            self.target_x = random.randint(100, self.screen_w - 100)
                            self.target_y = random.randint(100, self.screen_h - 100)
                            self.last_waypoint_time = time.time()
                            self.speed = random.uniform(3.8, 4.8)
                                    
                elif self.state == STATE_SCOUT_RECRUITING:
                    # Validate targets still need help
                    still_exists = any(t["id"] == self.help_target["id"] for t in app.targets) if self.help_target else False
                    if not self.help_target or not still_exists or self.help_target["carrying"]:
                        self.state = STATE_SCOUT_WANDERING
                        self.helper_ant = None
                        self.help_target = None
                        self.speed = random.uniform(3.8, 4.8)
                    # Validate helper ant is still alive and not already assigned to help_target (compare by ID)
                    elif not self.helper_ant or self.helper_ant not in app.ants or self.helper_ant.assigned_target["id"] == self.help_target["id"]:
                        helper = self.find_nearest_available_worker(app, self.help_target)
                        if helper:
                            self.helper_ant = helper
                        else:
                            self.state = STATE_SCOUT_WANDERING
                            self.helper_ant = None
                            self.help_target = None
                            self.speed = random.uniform(3.8, 4.8)
                    else:
                        # Chase helper ant
                        self.target_x = self.helper_ant.x
                        self.target_y = self.helper_ant.y
                        
                        hdx = self.helper_ant.x - self.x
                        hdy = self.helper_ant.y - self.y
                        hdist_sq = hdx**2 + hdy**2
                        
                        # Collision threshold check squared (32.0^2 = 1024.0)
                        if hdist_sq < 1024.0:
                            # Touch helper: Redirect it to help carrying!
                            self.helper_ant.assigned_target = self.help_target
                            self.helper_ant.state = STATE_SEEKING
                            
                            self.state = STATE_SCOUT_WANDERING
                            self.helper_ant = None
                            self.help_target = None
                            self.speed = random.uniform(3.8, 4.8)
                            
                            # Set waypoint target immediately to a remaining struggling target or random
                            struggling = [t for t in app.targets if not t["carrying"]]
                            if struggling:
                                self.help_target = random.choice(struggling)
                                self.target_x = self.help_target["curr_x"]
                                self.target_y = self.help_target["curr_y"]
                            else:
                                self.target_x = random.randint(100, self.screen_w - 100)
                                self.target_y = random.randint(100, self.screen_h - 100)
                            self.last_waypoint_time = time.time()
            else:
                # Worker (Red) Logic
                if not self.assigned_target:
                    self.state = STATE_SCATTERING
                    return True
                    
                tx = self.assigned_target["curr_x"]
                ty = self.assigned_target["curr_y"]
                dx = tx - self.x
                dy = ty - self.y
                dist = math.sqrt(dx**2 + dy**2)

                # Ring radius scales with the food's size, so ants gather AROUND
                # the item's edge (orbit_radius is the gap kept outside it) rather
                # than piling on top of larger items.
                ring_r = 0.5 * max(self.assigned_target["w"], self.assigned_target["h"]) + self.orbit_radius

                if self.state == STATE_SPAWNING:
                    self.target_x, self.target_y = tx, ty
                    if dist < 100:
                        self.state = STATE_SEEKING
                elif self.state == STATE_SEEKING:
                    self.target_x, self.target_y = tx, ty
                    if dist < ring_r + 20.0:
                        self.state = STATE_SURROUNDING
                elif self.state == STATE_SURROUNDING:
                    if dist > ring_r + 60.0:
                        self.state = STATE_SEEKING
                    elif self.assigned_target["carrying"]:
                        self.state = STATE_CARRYING
                    else:
                        # Slowly settle into a slot around the edge (gentle circling).
                        self.orbit_angle += 0.02
                        self.target_x = tx + ring_r * math.cos(self.orbit_angle)
                        self.target_y = ty + ring_r * math.sin(self.orbit_angle)
                elif self.state == STATE_CARRYING:
                    if not self.assigned_target["carrying"]:
                        self.state = STATE_SURROUNDING
                    else:
                        # While carrying: hold a FIXED slot around the food and move
                        # with it (no circling), so the group pushes/pulls steadily.
                        self.target_x = tx + ring_r * math.cos(self.orbit_angle)
                        self.target_y = ty + ring_r * math.sin(self.orbit_angle)

        # Steering math to target
        tdx = self.target_x - self.x
        tdy = self.target_y - self.y
        tdist_sq = tdx**2 + tdy**2
        
        if tdist_sq > 1.0:
            target_angle = math.atan2(tdy, tdx)
            angle_diff = (target_angle - self.angle + math.pi) % (2 * math.pi) - math.pi
            
            # Scouts turn MUCH sharper when in recruitment mode to successfully tag moving workers
            turn_speed = 0.35 if (self.is_scout and self.state == STATE_SCOUT_RECRUITING) else self.max_turn_speed
            self.angle += max(-turn_speed, min(turn_speed, angle_diff)) * sf

            self.x += self.speed * math.cos(self.angle) * sf * SPEED_SCALE
            self.y += self.speed * math.sin(self.angle) * sf * SPEED_SCALE
        else:
            if self.state == STATE_SCATTERING:
                # Reached off-screen target, safe to delete
                return False
                
        return True

    def find_nearest_available_worker(self, app, target):
        """Finds the best worker ant to recruit, prioritizing wandering/seeking ants, small targets, and few target ants."""
        best_worker = None
        best_score = -1.0
        
        for ant in app.ants:
            # Only check red worker ants that are active and not assigned to this target
            if not ant.is_scout and ant.state != STATE_SCATTERING and ant.assigned_target["id"] != target["id"]:
                
                # 1. Determine suitability weight based on worker's current state and target stats
                if ant.state not in (STATE_SURROUNDING, STATE_CARRYING):
                    # Free wandering/seeking worker ants are highly suitable for recruitment
                    suitability = 1000.0
                else:
                    t_ant = ant.assigned_target
                    area = t_ant["w"] * t_ant["h"]
                    ants_near = app.target_near_counts.get(t_ant["id"], 0)
                    # We prefer recruiting workers from smaller targets or targets with very few ants
                    suitability = 10000.0 / (area * ants_near + 1.0)
                    
                # 2. Add distance penalty (prefer recruiting closer workers)
                dx = ant.x - self.x
                dy = ant.y - self.y
                dist_sq = dx**2 + dy**2
                
                score = suitability / (dist_sq + 10.0)
                
                if score > best_score:
                    best_score = score
                    best_worker = ant
                    
        return best_worker

    def draw(self, canvas):
        """Draws red workers/green scouts with 3-tier realistic segmented body gradients and abdominal segments."""
        cos_t = math.cos(self.angle)
        sin_t = math.sin(self.angle)
        
        # Colour palette (configurable per ant type via the control panel).
        pal = CURRENT_PALETTES["scout" if self.is_scout else "worker"]
        c_base = pal["base"]
        c_thx = pal["thx"]
        c_hd = pal["hd"]
        c_legs = pal["legs"]
        stripe_color = pal["stripe"]
            
        # Helper to rotate local ant coordinates to screen coordinates
        def to_screen(lx, ly):
            lx *= self.size_scale
            ly *= self.size_scale
            rx = lx * cos_t - ly * sin_t
            ry = lx * sin_t + ly * cos_t
            return self.x + rx, self.y + ry

        # 1. Abdomen Base
        abd_pts = []
        for i in range(12):
            phi = 2 * math.pi * i / 12
            lx = -7.0 + 5.0 * math.cos(phi)
            ly = 0.0 + 3.5 * math.sin(phi)
            abd_pts.extend(to_screen(lx, ly))

        # Abdomen Segmented Gradient Stripes (2 concentric highlight bands)
        stripe_pts = []
        for offset_x in [-7.5, -4.5]:
            sp = []
            for i in range(12):
                phi = 2 * math.pi * i / 12
                lx = offset_x + 0.8 * math.cos(phi)
                ly = 0.0 + 3.1 * math.sin(phi)
                sp.extend(to_screen(lx, ly))
            stripe_pts.append(sp)

        # 2. Thorax
        thx_pts = []
        for i in range(12):
            phi = 2 * math.pi * i / 12
            lx = 0.0 + 3.5 * math.cos(phi)
            ly = 0.0 + 2.2 * math.sin(phi)
            thx_pts.extend(to_screen(lx, ly))

        # 3. Head
        hd_pts = []
        for i in range(12):
            phi = 2 * math.pi * i / 12
            lx = 6.0 + 2.5 * math.cos(phi)
            ly = 0.0 + 2.5 * math.sin(phi)
            hd_pts.extend(to_screen(lx, ly))

        # 4. Legs
        swing = 2.2 * math.sin(self.phase)
        leg_pts = [
            # Left legs (positive local y)
            [*to_screen(1.5, 1.2), *to_screen(3.0, 4.5), *to_screen(5.0 + swing, 7.5 + swing)],
            [*to_screen(0.0, 1.2), *to_screen(-0.5, 5.0), *to_screen(-1.0 - swing, 8.5 - swing)],
            [*to_screen(-1.5, 1.2), *to_screen(-3.5, 4.5), *to_screen(-6.0 + swing, 7.5 + swing)],
            # Right legs (negative local y)
            [*to_screen(1.5, -1.2), *to_screen(3.0, -4.5), *to_screen(5.0 - swing, -7.5 + swing)],
            [*to_screen(0.0, -1.2), *to_screen(-0.5, -5.0), *to_screen(-1.0 + swing, -8.5 - swing)],
            [*to_screen(-1.5, -1.2), *to_screen(-3.5, -4.5), *to_screen(-6.0 - swing, -7.5 + swing)],
        ]

        # 5. Antennae
        ant_wiggle = 0.8 * math.sin(self.phase * 2.0)
        antenna_pts = [
            [*to_screen(8.0, 0.8), *to_screen(10.5, 2.5), *to_screen(12.5, 4.0 + ant_wiggle)],
            [*to_screen(8.0, -0.8), *to_screen(10.5, -2.5), *to_screen(12.5, -4.0 - ant_wiggle)],
        ]

        # Build the full ordered list of point sequences for every body part.
        poly_pts = [abd_pts, stripe_pts[0], stripe_pts[1], thx_pts, hd_pts]
        line_pts = leg_pts + antenna_pts

        if self.items is None:
            # First draw for this ant: create each canvas item once. Colours are
            # fixed per ant, so they never need updating after creation.
            self.items = []
            poly_fills = [c_base, stripe_color, stripe_color, c_thx, c_hd]
            for pts, fill in zip(poly_pts, poly_fills):
                self.items.append(canvas.create_polygon(pts, fill=fill, outline="", tags="ant"))
            line_widths = [1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 1.2, 1.2]
            for pts, w in zip(line_pts, line_widths):
                self.items.append(canvas.create_line(*pts, fill=c_legs, width=w, tags="ant"))
        else:
            # Subsequent frames: just move the existing items. coords() is far
            # cheaper than destroying and recreating items every frame.
            for item, pts in zip(self.items, poly_pts + line_pts):
                canvas.coords(item, *pts)

    def clear_items(self, canvas):
        """Removes this ant's persistent canvas items (on death / overlay hide)."""
        if self.items:
            canvas.delete(*self.items)
            self.items = None


class ScreenAntsApp:
    def __init__(self):
        self.root = tk.Tk()
        
        # Get physical screen dimensions
        self.screen_w = ctypes.windll.user32.GetSystemMetrics(0)
        self.screen_h = ctypes.windll.user32.GetSystemMetrics(1)
        
        # Borderless, topmost overlay geometry setup
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.geometry(f"{self.screen_w}x{self.screen_h}+0+0")
        
        # Use transparent color key for click-through support
        self.trans_color = "#000001"
        self.root.configure(bg=self.trans_color)
        self.root.attributes("-transparentcolor", self.trans_color)
        
        # Overlay drawing canvas
        self.canvas = tk.Canvas(self.root, bg=self.trans_color, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # HWND registration for Win32 styles
        unique_title = f"ScreenAntsOverlay_{random.randint(1000, 9999)}"
        self.root.title(unique_title)
        self.root.update()
        
        self.hwnd = ctypes.windll.user32.FindWindowW(None, unique_title)
        if self.hwnd:
            self.make_click_through(self.hwnd)
        
        self.root.bind("<Escape>", lambda e: self.exit_program())
        
        # Simulation state
        self.ants = []
        self.is_active = False
        
        # Nest / Spawning Entrance Coordinates (Fixed permanently to bottom-left corner of the screen)
        self.scout_spawn_x = 0
        self.scout_spawn_y = self.screen_h
        self.nest_corner = "bottom-left"
        self.scout_reported = True
        self.last_spawn_time = 0
        
        # Queen Ant State variables
        self.queen_state = "queen_inactive"
        self.queen_x = 0
        self.queen_y = 0
        self.queen_angle = 0.0
        self.queen_phase = 0.0
        self.queen_target_item = None
        self.queen_timer_start = 0.0   # when the current idle session's queen countdown began
        self.queen_mode = None         # "eat" (came out for delivered food) or "haul" (timed big outing)
        self.queen_eat_start = 0.0

        # Hiding and permanent masking list for eaten/devoured items
        self.eaten_icons = []
        self.mouse_eaten = False

        # Load user configuration settings (idle delay, queen interval, colours)
        self.idle_limit = 5.0
        self.queen_interval = 60.0     # seconds of idle before the queen comes out (repeats)

        script_dir = app_dir()
        config_path = os.path.join(script_dir, "config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    cfg = json.load(f)
                    self.idle_limit = float(cfg.get("idle_timeout", 5.0))
                    # Accept both the new key and the old "deadlock_timeout" key.
                    self.queen_interval = float(cfg.get("queen_interval", cfg.get("deadlock_timeout", 60.0)))
                    for who in ("worker", "scout", "queen"):
                        name = cfg.get(f"{who}_color", DEFAULT_PALETTE_NAMES[who])
                        if name in ANT_PALETTES:
                            CURRENT_PALETTES[who] = ANT_PALETTES[name]
            except Exception:
                pass
        
        # Multiple carrying targets list
        self.targets = []
        self.detected_icons = []
        self.last_target_add_time = 0
        self.target_near_counts = {}
        
        self.target_x = 0
        self.target_y = 0
        
        # Tracking variables
        self.expected_mx, self.expected_my = get_cursor_pos()
        self.is_idle = False

        # Frame-rate compensation: speed_factor scales movement so ants keep a
        # constant real-world speed regardless of the actual frame rate. The
        # frame time is smoothed (smooth_dt) so the factor changes gradually
        # instead of lurching when individual frames are irregular.
        self.last_tick_time = time.time()
        self.smooth_dt = 1.0 / FPS
        self.speed_factor = 1.0

        # Initial overlay state
        self.hide_overlay()
        
        # Run loop
        self.tick()

    def make_click_through(self, hwnd):
        style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
        style |= 0x00080000  # WS_EX_LAYERED
        style |= 0x00000020  # WS_EX_TRANSPARENT
        ctypes.windll.user32.SetWindowLongW(hwnd, -20, style)

    def show_overlay(self):
        if not self.is_active:
            # Sync expected mouse coordinates with current cursor position
            self.expected_mx, self.expected_my = get_cursor_pos()
            # Fix nest coordinates to bottom-left and build its irregular shape
            self.select_random_nest()
            self.generate_nest()

            # Detect screen-wide icons (including inside apps)
            self.detected_icons = []
            self.capture_screen_icons()
            
            # Reset active targets list
            self.targets = []
            self.target_near_counts = {}
            self.queen_state = "queen_inactive"
            self.queen_target_item = None
            self.eaten_icons = []
            self.mouse_eaten = False
            # Start the queen's countdown for this idle session.
            self.queen_timer_start = time.time()

            # Show overlay
            self.root.deiconify()
            self.root.attributes("-topmost", True)
            self.is_active = True
            self.last_target_add_time = time.time()
            
            if DEBUG_MODE:
                print(f"Overlay Activated. Nest: ({self.scout_spawn_x}, {self.scout_spawn_y}). Detected {len(self.detected_icons)} icons.")

    def capture_screen_icons(self):
        """Uses OpenCV Canny edge & contour detection to detect UI icons across active windows."""
        try:
            # Capture full screen
            full_screenshot = ImageGrab.grab()
            img = np.array(full_screenshot)
            
            # Run OpenCV contour detection
            img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for c in contours:
                x, y, w, h = cv2.boundingRect(c)
                # Keep both small elements (14x14) and large icons/elements (180x180)
                if 14 <= w <= 180 and 14 <= h <= 180:
                    aspect = w / h
                    # Aspect ratio check
                    if 0.5 <= aspect <= 2.2:
                        # Skip 85% of tiny elements (< 24px) to ensure a balanced mix with large icons
                        if w < 24 and h < 24:
                            if random.random() > 0.15:
                                continue
                                
                        # Avoid screen borders
                        if 15 < x < self.screen_w - 200 and 15 < y < self.screen_h - 200:
                            # Sample top-left corner pixel as background mask color
                            clamped_y = max(0, min(self.screen_h - 1, y))
                            clamped_x = max(0, min(self.screen_w - 1, x))
                            b, g, r = img_bgr[clamped_y, clamped_x]
                            bg_color = f"#{r:02x}{g:02x}{b:02x}"
                            
                            # Crop PIL image
                            crop = full_screenshot.crop((x, y, x + w, y + h))
                            
                            self.detected_icons.append({
                                "x": x, "y": y, "w": w, "h": h,
                                "crop": crop, "bg_color": bg_color
                            })
                            
            # Randomize icon list for progressive spawning
            random.shuffle(self.detected_icons)
            
        except Exception as e:
            if DEBUG_MODE:
                print(f"Error in CV detection: {e}")

    def _consume_target(self, target):
        """Removes a food target (keeps its spot masked) and reassigns any ants
        that were carrying it to another remaining target (or scatter)."""
        eaten_id = target["id"]
        if target["type"] == "mouse":
            self.mouse_eaten = True
        else:
            self.eaten_icons.append({
                "orig_x": target["orig_x"], "orig_y": target["orig_y"],
                "w": target["w"], "h": target["h"], "bg_color": target["bg_color"],
            })
        self.targets = [t for t in self.targets if t["id"] != eaten_id]
        for ant in self.ants:
            if not ant.is_scout and ant.assigned_target and ant.assigned_target["id"] == eaten_id:
                new_t = self.select_size_biased_target()
                if new_t:
                    ant.assigned_target = new_t
                    ant.state = STATE_SEEKING
                else:
                    ant.assigned_target = None
                    ant.state = STATE_SCATTERING

    def capture_food_chunk(self, size):
        """Grabs a square chunk of the screen roughly `size` px across, choosing
        the most colourful of several random spots as the queen's foraged meal.
        Returns a ready-to-use food target, or None on failure."""
        try:
            shot = ImageGrab.grab()
            sw, sh = shot.size
            # Try several random spots and keep the most colourful / busy one, so
            # she doesn't haul a boring blank (e.g. plain white) patch of screen.
            best = None
            best_score = -1.0
            for _ in range(16):
                w = max(20, int(size * random.uniform(0.85, 1.15)))
                h = max(20, int(size * random.uniform(0.85, 1.15)))
                x = random.randint(120, max(121, sw - 120 - w))
                y = random.randint(120, max(121, sh - 120 - h))
                crop = shot.crop((x, y, x + w, y + h))
                arr = np.asarray(crop)[:, :, :3].astype(np.float32)
                # std = overall variation; spread = how colourful (per-pixel channel range).
                score = float(arr.std()) + 1.5 * float((arr.max(axis=2) - arr.min(axis=2)).mean())
                if score > best_score:
                    best_score = score
                    best = (x, y, w, h, crop)
            x, y, w, h, crop = best
            pr = crop.getpixel((0, 0))
            bg_color = f"#{pr[0]:02x}{pr[1]:02x}{pr[2]:02x}"
            # Square food -> square gap left behind (coherent with the carried crop).
            return {
                "id": random.randint(10000000, 99999999),
                "type": "icon",
                "orig_x": x, "orig_y": y,
                "curr_x": x + w / 2.0, "curr_y": y + h / 2.0,
                "w": w, "h": h,
                "tk_img": ImageTk.PhotoImage(crop),
                "bg_color": bg_color,
                "carrying": False,
                "carrying_angle": random.uniform(0, 2 * math.pi),
            }
        except Exception:
            return None

    def select_size_biased_target(self):
        """Selects a target from self.targets with probability proportional to target size."""
        if not self.targets:
            return None
        weights = []
        for t in self.targets:
            # Mouse has a virtual weight of 1225. Icons use their physical area.
            weight = t["w"] * t["h"]
            weights.append(weight)
            
        # Weighted random selection
        return random.choices(self.targets, weights=weights, k=1)[0]

    def spawn_ants_for_target(self, target, count=5):
        """Spawns a specific number of recruited worker ants assigned to a target."""
        for _ in range(count):
            ant = Ant(self.scout_spawn_x, self.scout_spawn_y, self.screen_w, self.screen_h, is_scout=False, assigned_target=target)
            self.ants.append(ant)

    def hide_overlay(self):
        if self.is_active or len(self.ants) > 0:
            self.root.withdraw()
            # Remove every persistent ant canvas item, plus any per-frame layers,
            # so nothing is left frozen on the canvas for the next activation.
            self.canvas.delete("ant")
            self.canvas.delete("dynbg")
            self.canvas.delete("dyntop")
            self.ants.clear()
            self.targets.clear()
            self.detected_icons.clear()
            self.target_near_counts.clear()
            self.eaten_icons.clear()
            self.queen_state = "queen_inactive"
            self.queen_target_item = None
            self.mouse_eaten = False
            self.queen_timer_start = 0.0
            self.is_active = False
            # Sync expected mouse position to current coordinates to prevent stale coordinate triggers
            self.expected_mx, self.expected_my = get_cursor_pos()
            if DEBUG_MODE:
                print("Overlay Hidden. States reset.")

    def select_random_nest(self):
        """Fixes the nest/anthill coordinate to the bottom-left of the screen."""
        self.scout_spawn_x = 0
        self.scout_spawn_y = self.screen_h
        self.nest_corner = "bottom-left"

    def generate_nest(self):
        """Builds an irregular, soil-like anthill mound in the bottom-left corner.
        The shape is generated once per activation so it does not flicker."""
        nx, ny = self.scout_spawn_x, self.scout_spawn_y
        base = 170.0 * NEST_SIZE

        # Irregular outer mound outline (a blobby polygon centred on the corner;
        # the off-screen half is simply clipped, leaving a pile in the corner).
        pts = []
        n = 26
        for i in range(n):
            ang = 2 * math.pi * i / n
            r = base * random.uniform(0.80, 1.15)
            pts.extend([nx + r * math.cos(ang), ny + r * math.sin(ang)])
        self.nest_pts = pts

        # Scattered soil clumps for texture.
        self.nest_spots = []
        soil = ["#4E342E", "#6D4C41", "#3E2723", "#5D4037", "#795548"]
        for _ in range(16):
            ang = random.uniform(0, 2 * math.pi)
            rr = base * random.uniform(0.12, 0.92)
            cx = nx + rr * math.cos(ang)
            cy = ny + rr * math.sin(ang)
            sr = base * random.uniform(0.04, 0.12)
            self.nest_spots.append((cx - sr, cy - sr, cx + sr, cy + sr, random.choice(soil)))

        # Irregular dark entrance hole a little way into the screen.
        hx = nx + base * 0.30
        hy = ny - base * 0.30
        hpts = []
        hn = 14
        for i in range(hn):
            ang = 2 * math.pi * i / hn
            r = base * 0.17 * random.uniform(0.7, 1.25)
            hpts.extend([hx + r * math.cos(ang), hy + r * math.sin(ang)])
        self.nest_hole_pts = hpts

    def draw_queen(self, canvas):
        """Draws a giant Sandy-Yellow Gradient (Striped) Queen Ant at self.queen_x, self.queen_y."""
        cos_t = math.cos(self.queen_angle)
        sin_t = math.sin(self.queen_angle)
        size_scale = 4.2 # Extra Giant queen size (Enlarged from 3.6 as requested!)
        
        # Queen colour palette (configurable via the control panel).
        qpal = CURRENT_PALETTES["queen"]
        color_base = qpal["base"]
        color_thorax = qpal["thx"]
        color_head = qpal["hd"]
        color_legs = qpal["legs"]
        
        # Helper to rotate local coordinates to screen
        def to_screen(lx, ly):
            lx *= size_scale
            ly *= size_scale
            rx = lx * cos_t - ly * sin_t
            ry = lx * sin_t + ly * cos_t
            return self.queen_x + rx, self.queen_y + ry

        # 1. Abdomen (Large base)
        abd_pts = []
        for i in range(12):
            phi = 2 * math.pi * i / 12
            lx = -8.0 + 8.0 * math.cos(phi)
            ly = 0.0 + 5.5 * math.sin(phi)
            abd_pts.extend(to_screen(lx, ly))
        canvas.create_polygon(abd_pts, fill=color_base, outline="", tags="dyntop")
        
        # Gradient stripes (concentric rings overlay on the abdomen)
        stripe_colors = [qpal["stripe"], qpal["hd"], qpal["stripe"]]
        for idx, offset_x in enumerate([-8.0, -4.0, 0.0]):
            stripe_pts = []
            for i in range(12):
                phi = 2 * math.pi * i / 12
                # Narrow vertical ellipse bands to simulate gradient stripes
                lx = offset_x + 1.2 * math.cos(phi)
                ly = 0.0 + 5.0 * math.sin(phi)
                stripe_pts.extend(to_screen(lx, ly))
            canvas.create_polygon(stripe_pts, fill=stripe_colors[idx], outline="", tags="dyntop")

        # 2. Thorax
        thx_pts = []
        for i in range(12):
            phi = 2 * math.pi * i / 12
            lx = 1.0 + 4.5 * math.cos(phi)
            ly = 0.0 + 3.0 * math.sin(phi)
            thx_pts.extend(to_screen(lx, ly))
        canvas.create_polygon(thx_pts, fill=color_thorax, outline="", tags="dyntop")

        # 3. Head
        hd_pts = []
        for i in range(12):
            phi = 2 * math.pi * i / 12
            lx = 7.5 + 3.0 * math.cos(phi)
            ly = 0.0 + 3.0 * math.sin(phi)
            hd_pts.extend(to_screen(lx, ly))
        canvas.create_polygon(hd_pts, fill=color_head, outline="", tags="dyntop")

        # 4. Legs (Thick royal legs)
        swing = 2.2 * math.sin(self.queen_phase)
        
        # Left legs
        ax1, ay1 = to_screen(1.5, 1.2)
        jx1, jy1 = to_screen(3.5, 4.5)
        tx1, ty1 = to_screen(5.5 + swing, 8.5 + swing)
        canvas.create_line(ax1, ay1, jx1, jy1, tx1, ty1, fill=color_legs, width=3.2, tags="dyntop")
        
        ax2, ay2 = to_screen(0.0, 1.2)
        jx2, jy2 = to_screen(-0.5, 5.0)
        tx2, ty2 = to_screen(-1.0 - swing, 9.5 - swing)
        canvas.create_line(ax2, ay2, jx2, jy2, tx2, ty2, fill=color_legs, width=3.2, tags="dyntop")
        
        ax3, ay3 = to_screen(-1.5, 1.2)
        jx3, jy3 = to_screen(-3.5, 4.5)
        tx3, ty3 = to_screen(-6.0 + swing, 8.5 + swing)
        canvas.create_line(ax3, ay3, jx3, jy3, tx3, ty3, fill=color_legs, width=3.2, tags="dyntop")

        # Right legs
        ax4, ay4 = to_screen(1.5, -1.2)
        jx4, jy4 = to_screen(3.5, -4.5)
        tx4, ty4 = to_screen(5.5 - swing, -8.5 + swing)
        canvas.create_line(ax4, ay4, jx4, jy4, tx4, ty4, fill=color_legs, width=3.2, tags="dyntop")
        
        ax5, ay5 = to_screen(0.0, -1.2)
        jx5, jy5 = to_screen(-0.5, -5.0)
        tx5, ty5 = to_screen(-1.0 + swing, -9.5 - swing)
        canvas.create_line(ax5, ay5, jx5, jy5, tx5, ty5, fill=color_legs, width=3.2, tags="dyntop")
        
        ax6, ay6 = to_screen(-1.5, -1.2)
        jx6, jy6 = to_screen(-3.5, -4.5)
        tx6, ty6 = to_screen(-6.0 - swing, -7.5 + swing)
        canvas.create_line(ax6, ay6, jx6, jy6, tx6, ty6, fill=color_legs, width=3.2, tags="dyntop")

        # 5. Antennae
        ant_wiggle = 0.8 * math.sin(self.queen_phase * 2.0)
        as1, at1 = to_screen(9.5, 0.8)
        aj1, ak1 = to_screen(12.5, 2.5)
        ae1, af1 = to_screen(15.5, 4.0 + ant_wiggle)
        canvas.create_line(as1, at1, aj1, ak1, ae1, af1, fill=color_legs, width=2.0, tags="dyntop")
        
        as2, at2 = to_screen(9.5, -0.8)
        aj2, ak2 = to_screen(12.5, -2.5)
        ae2, af2 = to_screen(15.5, -4.0 - ant_wiggle)
        canvas.create_line(as2, at2, aj2, ak2, ae2, af2, fill=color_legs, width=2.0, tags="dyntop")

    def tick(self):
        start_time = time.time()

        # Frame-rate compensation factor: how many "ideal frames" elapsed since
        # the last tick. 1.0 at the target FPS; >1 when the frame rate drops so
        # ants still move at a constant real-world speed. The frame time is
        # exponentially smoothed so a single slow frame doesn't make the ants
        # lurch (which looked like stutter); clamped to bound the extremes.
        dt = start_time - self.last_tick_time
        self.last_tick_time = start_time
        # Ignore one-off huge gaps (e.g. the initial icon capture) so they don't
        # poison the smoothed average.
        if dt > 0.5:
            dt = self.smooth_dt
        self.smooth_dt = 0.85 * self.smooth_dt + 0.15 * dt
        self.speed_factor = max(0.5, min(2.2, self.smooth_dt * FPS))

        # 1. Capture user mouse coordinates & system idle metrics
        idle_seconds = get_system_idle_time()
        mx, my = get_cursor_pos()
        
        # Spawning coordinates (Fixed permanently to bottom-left corner)
        nx, ny = self.scout_spawn_x, self.scout_spawn_y
        
        # If the mouse has been eaten, force physical mouse cursor to lock at the nest (visibly hidden)
        if self.is_active and self.mouse_eaten:
            set_cursor_pos(nx, ny)
            self.expected_mx, self.expected_my = nx, ny
            mx, my = nx, ny
            
        user_moved_mouse = False
        if self.is_active:
            # If mouse target is carrying (but not eaten yet), check mouse movement relative to where we moved it
            mouse_target = next((t for t in self.targets if t["type"] == "mouse"), None)
            if mouse_target and mouse_target["carrying"]:
                dx = mx - self.expected_mx
                dy = my - self.expected_my
                dist = math.sqrt(dx**2 + dy**2)
                if dist > 6.0:
                    user_moved_mouse = True
            elif self.mouse_eaten:
                # If mouse is eaten and locked at nest, check if user dragged it away to wake up
                dx = mx - nx
                dy = my - ny
                dist = math.sqrt(dx**2 + dy**2)
                if dist > 8.0: # Allow slight buffer for jitter, wake up on intentional drags
                    user_moved_mouse = True
            else:
                # Otherwise any physical movement wakes up
                dx = mx - self.expected_mx
                dy = my - self.expected_my
                dist = math.sqrt(dx**2 + dy**2)
                if dist > 3.0: # strict check
                    user_moved_mouse = True
                
        self.is_idle = (idle_seconds >= self.idle_limit) and not user_moved_mouse

        if self.is_idle:
            self.show_overlay()
            
            # Phase A: Spawn 4 green Scout Managers and create initial mouse target
            if len(self.ants) == 0:
                # Create mouse target first with unique ID
                mouse_target = {
                    "id": random.randint(10000000, 99999999),
                    "type": "mouse",
                    "orig_x": mx, "orig_y": my,
                    "curr_x": mx, "curr_y": my,
                    "w": 35, "h": 35,  # virtual size for mouse cursor
                    "tk_img": None, "bg_color": "",
                    "carrying": False,
                    "carrying_angle": random.uniform(0, 2*math.pi)
                }
                self.targets.append(mouse_target)
                
                # Spawn 4 green scout ants (which manage and direct workers)
                for _ in range(4):
                    self.ants.append(Ant(self.scout_spawn_x, self.scout_spawn_y, self.screen_w, self.screen_h, is_scout=True))
                
                # Spawn first 10 red worker ants assigned to the mouse target
                self.spawn_ants_for_target(mouse_target, count=10)
                
                self.last_target_add_time = time.time()
                
            # Phase C: Add new targets progressively (Worker ants capped at 50)
            else:
                workers_count = sum(1 for a in self.ants if not a.is_scout)
                if workers_count < 50:
                    current_time = time.time()
                    # Spawn a new target every 1.5 seconds
                    if current_time - self.last_target_add_time >= 1.5:
                        if len(self.detected_icons) > 0:
                            icon_data = self.detected_icons.pop(0)
                            tk_img = ImageTk.PhotoImage(icon_data["crop"])
                            
                            new_target = {
                                "id": random.randint(10000000, 99999999),
                                "type": "icon",
                                "orig_x": icon_data["x"], "orig_y": icon_data["y"],
                                "curr_x": icon_data["x"] + icon_data["w"]/2,
                                "curr_y": icon_data["y"] + icon_data["h"]/2,
                                "w": icon_data["w"], "h": icon_data["h"],
                                "tk_img": tk_img, "bg_color": icon_data["bg_color"],
                                "carrying": False,
                                "carrying_angle": random.uniform(0, 2*math.pi)
                            }
                            self.targets.append(new_target)
                            
                            # Size-biased random selection: new workers pick a target preferring larger items
                            selected_target = self.select_size_biased_target()
                            if not selected_target:
                                selected_target = new_target
                                
                            # Spawn 5 worker ants assigned to the selected target
                            self.spawn_ants_for_target(selected_target, count=5)
                            self.last_target_add_time = current_time
        else:
            # Sync expected mouse position continuously while screensaver is inactive
            self.expected_mx, self.expected_my = mx, my
            self.hide_overlay()
            # CRITICAL: keep the animation loop alive. Without rescheduling here,
            # the very first non-idle tick (which happens right at startup, and
            # after every mouse move) would stop tick() forever and the ants
            # would never appear again.
            self.root.after(int(1000 / FPS), self.tick)
            return

        # Update Mouse target coordinate to match current physical cursor if not carrying yet
        for target in self.targets:
            if target["type"] == "mouse" and not target["carrying"]:
                target["curr_x"], target["curr_y"] = mx, my

        # HIGH PERFORMANCE OPTIMIZATION: Compute nearby worker count once per frame O(N)
        self.target_near_counts = {t["id"]: 0 for t in self.targets}
        for ant in self.ants:
            if not ant.is_scout and ant.state != STATE_SCATTERING and ant.assigned_target:
                t = ant.assigned_target
                dx = t["curr_x"] - ant.x
                dy = t["curr_y"] - ant.y
                # "Near" radius scales with the food's size so ants standing around
                # a large item's edge still count toward its carrying threshold.
                near_r = 0.5 * max(t["w"], t["h"]) + 30.0
                if (dx**2 + dy**2) < near_r * near_r:
                    self.target_near_counts[t["id"]] += 1

        # 2. Count worker ants near their respective targets and update carrying physics
        for target in self.targets:
            ants_near = self.target_near_counts.get(target["id"], 0)
            
            # Determine carrying threshold:
            if target["type"] == "mouse":
                threshold = 15
            else:
                area = target["w"] * target["h"]
                threshold = min(20, max(2, int(area / 280)))
            
            queen_carried = target.get("queen_carried", False)
            if self.is_idle and (queen_carried or ants_near >= threshold):
                target["carrying"] = True

                # Steer carrying direction straight towards the fixed bottom-left nest!
                target_angle = math.atan2(ny - target["curr_y"], nx - target["curr_x"])

                # Interpolate smoothly to drag towards nest
                angle_diff = (target_angle - target["carrying_angle"] + math.pi) % (2 * math.pi) - math.pi
                target["carrying_angle"] += max(-0.12, min(0.12, angle_diff))
                # Add a touch of natural organic wiggle (kept small for steady dragging)
                target["carrying_angle"] += random.uniform(-0.02, 0.02)

                # Frame-rate compensated and globally scaled so the carried item
                # drifts toward the nest at the same steady pace as the ants. When
                # the queen is hauling it, she is stronger -> QUEEN_SPEED_MULT faster.
                speed_mult = QUEEN_SPEED_MULT if queen_carried else 1.0
                carry_speed = 1.15 * speed_mult * self.speed_factor * SPEED_SCALE
                carry_vx = carry_speed * math.cos(target["carrying_angle"])
                carry_vy = carry_speed * math.sin(target["carrying_angle"])
                
                new_tx = target["curr_x"] + carry_vx
                new_ty = target["curr_y"] + carry_vy
                
                new_tx = max(20, min(self.screen_w - 20, new_tx))
                new_ty = max(20, min(self.screen_h - 20, new_ty))
                
                target["curr_x"], target["curr_y"] = new_tx, new_ty
                
                if target["type"] == "mouse":
                    set_cursor_pos(new_tx, new_ty)
                    self.expected_mx, self.expected_my = new_tx, new_ty
                    mx, my = new_tx, new_ty
            else:
                target["carrying"] = False
                
        # Sync expected mouse position
        mouse_target = next((t for t in self.targets if t["type"] == "mouse"), None)
        if not mouse_target or not mouse_target["carrying"]:
            self.expected_mx, self.expected_my = mx, my

        # 3. Queen Ant — two behaviours that coexist:
        #    Mode A ("eat"): whenever the workers haul a food to the nest mouth,
        #      she pops out, walks to it and eats it. (the everyday behaviour)
        #    Mode B ("haul"): every queen_interval seconds of idle she charges
        #      out, grabs the single LARGEST block (>= QUEEN_MIN_FOOD) herself and
        #      hauls it home at 1.5x speed with ~half the colony following.
        qphase_step = max(0.18, 0.30 * self.speed_factor * SPEED_SCALE)
        if self.is_idle:
            if self.queen_state == "queen_inactive":
                timer_ready = (self.queen_timer_start > 0.0 and
                               time.time() - self.queen_timer_start >= self.queen_interval)
                if timer_ready:
                    # Mode B: timed foraging outing — grab an irregular ~50px chunk.
                    chunk = self.capture_food_chunk(QUEEN_FOOD_SIZE)
                    if chunk:
                        self.targets.append(chunk)  # so it gets masked/drawn/carried
                        self.queen_mode = "haul"
                        self.queen_state = "queen_charging"
                        self.queen_target_item = chunk
                        self.queen_x = nx
                        self.queen_y = ny
                        # A fixed squad of workers drop everything and follow her.
                        workers = [a for a in self.ants if not a.is_scout]
                        random.shuffle(workers)
                        for a in workers[:QUEEN_FOLLOWERS]:
                            a.assigned_target = chunk
                            a.state = STATE_SEEKING
                    else:
                        # Screen grab failed this time — try again shortly.
                        self.queen_timer_start = time.time() - self.queen_interval + 3.0
                else:
                    # Mode A: a food the workers have hauled to the nest mouth?
                    delivered = None
                    best_d2 = 130.0 * 130.0
                    for t in self.targets:
                        if not t.get("carrying"):
                            continue
                        d2 = (t["curr_x"] - nx) ** 2 + (t["curr_y"] - ny) ** 2
                        if d2 < best_d2:
                            best_d2 = d2
                            delivered = t
                    if delivered is not None:
                        self.queen_mode = "eat"
                        self.queen_state = "queen_emerging"
                        self.queen_target_item = delivered
                        self.queen_x = nx
                        self.queen_y = ny

            elif self.queen_state == "queen_emerging":
                # Walk out from the nest to the delivered food, then eat it.
                if self.queen_target_item not in self.targets:
                    self.queen_state = "queen_returning"
                else:
                    qdx = self.queen_target_item["curr_x"] - self.queen_x
                    qdy = self.queen_target_item["curr_y"] - self.queen_y
                    self.queen_angle = math.atan2(qdy, qdx)
                    if qdx * qdx + qdy * qdy > 225.0:  # 15px
                        step = 5.0 * self.speed_factor * SPEED_SCALE
                        self.queen_x += step * math.cos(self.queen_angle)
                        self.queen_y += step * math.sin(self.queen_angle)
                        self.queen_phase += qphase_step
                    else:
                        self.queen_state = "queen_eating"
                        self.queen_eat_start = time.time()

            elif self.queen_state == "queen_eating":
                self.queen_phase += qphase_step * 1.3  # quick chewing
                if time.time() - self.queen_eat_start > 0.7:
                    if self.queen_target_item in self.targets:
                        self._consume_target(self.queen_target_item)
                    self.queen_target_item = None
                    self.queen_state = "queen_returning"

            elif self.queen_state == "queen_charging":
                # Run from the nest to the food.
                if self.queen_target_item not in self.targets:
                    self.queen_state = "queen_returning"
                else:
                    qdx = self.queen_target_item["curr_x"] - self.queen_x
                    qdy = self.queen_target_item["curr_y"] - self.queen_y
                    self.queen_angle = math.atan2(qdy, qdx)
                    if qdx * qdx + qdy * qdy > 400.0:
                        step = 9.0 * self.speed_factor * SPEED_SCALE
                        self.queen_x += step * math.cos(self.queen_angle)
                        self.queen_y += step * math.sin(self.queen_angle)
                        self.queen_phase += qphase_step * 1.4
                    else:
                        # Grab it: from now on it is hauled by the queen.
                        self.queen_target_item["queen_carried"] = True
                        self.queen_state = "queen_hauling"

            elif self.queen_state == "queen_hauling":
                if self.queen_target_item not in self.targets:
                    self.queen_state = "queen_returning"
                else:
                    fx, fy = self.queen_target_item["curr_x"], self.queen_target_item["curr_y"]
                    if (fx - nx) ** 2 + (fy - ny) ** 2 < 3600.0:  # reached nest (60px)
                        # Eat it: remove the food and release the followers.
                        self._consume_target(self.queen_target_item)
                        self.queen_target_item = None
                        self.queen_state = "queen_returning"
                    else:
                        # Queen PUSHES from the far corner (the side away from the
                        # nest), so the food sits between her and the nest and she
                        # never visually covers it.
                        away = math.atan2(fy - ny, fx - nx)  # nest -> food (away from nest)
                        tw = self.queen_target_item["w"]
                        th = self.queen_target_item["h"]
                        push_dist = 0.5 * math.hypot(tw, th) + 55
                        self.queen_x = fx + push_dist * math.cos(away)
                        self.queen_y = fy + push_dist * math.sin(away)
                        # Face toward the nest (the direction she's shoving the food).
                        self.queen_angle = math.atan2(ny - self.queen_y, nx - self.queen_x)
                        self.queen_phase += qphase_step

            elif self.queen_state == "queen_returning":
                qdx = nx - self.queen_x
                qdy = ny - self.queen_y
                self.queen_angle = math.atan2(qdy, qdx)
                if qdx * qdx + qdy * qdy > 25.0:
                    step = 4.5 * self.speed_factor * SPEED_SCALE
                    self.queen_x += step * math.cos(self.queen_angle)
                    self.queen_y += step * math.sin(self.queen_angle)
                    self.queen_phase += qphase_step
                else:
                    self.queen_state = "queen_inactive"
                    self.queen_target_item = None
                    # Only the timed big outing resets the countdown; eating
                    # delivered food does not delay her next scheduled outing.
                    if self.queen_mode == "haul":
                        self.queen_timer_start = time.time()
                    self.queen_mode = None
        else:
            # If not idle, Queen retreats instantly off screen
            self.queen_state = "queen_inactive"
            self.queen_target_item = None
            self.queen_mode = None

        # 4. Canvas updates & redrawing loop.
        # Ants use PERSISTENT canvas items (moved via coords()), so we must NOT
        # clear them every frame. Only the per-frame background ("dynbg": nest,
        # eaten-icon masks, carried targets) and foreground ("dyntop": queen,
        # debug HUD) layers are rebuilt each frame.
        self.canvas.delete("dynbg")
        self.canvas.delete("dyntop")

        # A: Draw active overlays (background layer)
        if self.is_active:
            # Draw the irregular soil anthill: mound outline, soil-clump texture, dark entrance hole.
            self.canvas.create_polygon(self.nest_pts, fill="#5D4037", outline="#3E2723", width=3, smooth=True, tags="dynbg")
            for (x0, y0, x1, y1, col) in self.nest_spots:
                self.canvas.create_oval(x0, y0, x1, y1, fill=col, outline="", tags="dynbg")
            self.canvas.create_polygon(self.nest_hole_pts, fill="#1A0C00", outline="", smooth=True, tags="dynbg")

            # Draw solid background masks for all eaten icons to keep them permanently invisible!
            for icon in self.eaten_icons:
                self.canvas.create_rectangle(
                    icon["orig_x"], icon["orig_y"],
                    icon["orig_x"] + icon["w"],
                    icon["orig_y"] + icon["h"],
                    fill=icon["bg_color"], outline="", tags="dynbg"
                )

            # Draw masks and images for active carrying targets
            for target in self.targets:
                if target["type"] == "icon" and target["tk_img"]:
                    # Draw background mask at original location
                    self.canvas.create_rectangle(
                        target["orig_x"], target["orig_y"],
                        target["orig_x"] + target["w"],
                        target["orig_y"] + target["h"],
                        fill=target["bg_color"], outline="", tags="dynbg"
                    )
                    # Draw cropped icon centered around its curr_x, curr_y
                    cx = target["curr_x"] - target["w"] / 2
                    cy = target["curr_y"] - target["h"] / 2
                    self.canvas.create_image(cx, cy, image=target["tk_img"], anchor="nw", tags="dynbg")

        # B: Draw ants (persistent items; dead ones release their canvas items)
        alive_ants = []
        for ant in self.ants:
            is_alive = ant.update(self)
            if is_alive:
                ant.draw(self.canvas)
                alive_ants.append(ant)
            else:
                ant.clear_items(self.canvas)

        self.ants = alive_ants

        # Keep the background layer beneath the ants (ant items were created in
        # earlier frames, so freshly created dynbg items would otherwise cover them).
        self.canvas.tag_lower("dynbg")

        # Draw the majestic Queen Ant if active (foreground layer, above ants)
        if self.is_active and self.queen_state != "queen_inactive":
            self.draw_queen(self.canvas)

        # Once all scattering ants run off screen, disable GUI overlay mapping
        if not self.is_idle and len(self.ants) == 0:
            self.hide_overlay()

        if DEBUG_MODE:
            self.canvas.create_text(
                120, 30,
                text=f"Ants: {len(self.ants)} | Targets: {len(self.targets)} | Idle: {idle_seconds:.1f}s",
                fill="#FF0000", font=("Arial", 12), tags="dyntop"
            )

        # Loop delay
        elapsed = time.time() - start_time
        delay = max(1, int((1.0 / FPS - elapsed) * 1000))
        self.root.after(delay, self.tick)

    def exit_program(self):
        self.root.destroy()
        sys.exit()

def run_screensaver():
    try:
        app = ScreenAntsApp()
        app.root.mainloop()
    except Exception as e:
        import traceback
        log_path = os.path.join(app_dir(), "error.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"Crash Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Exception message: {str(e)}\n\n")
            traceback.print_exc(file=f)


if __name__ == "__main__":
    run_screensaver()
