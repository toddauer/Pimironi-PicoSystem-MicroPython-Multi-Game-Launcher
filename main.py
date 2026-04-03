from picosystem import *
import os
import math
import random

# =================================
# Files
# =================================
files = sorted([f for f in os.listdir("/games") if f.endswith(".py")])
selected = 0
my_sprites = picosystem.Buffer(128, 128)
with open("sprites.16bpp", "rb") as f:
    f.readinto(my_sprites)
picosystem.spritesheet(my_sprites)

blip = Voice(10, 10, 10, 10, 40, 2)
ding = Voice(5, 5, 100, 500)
ding.effects(reverb=50)
ding.bend(500, 500)

filecount = len(files)
step_angle = 360.0 / max(1, filecount)
accumulated_angle = 0.0
current_angle = 0.0
voltage = battery()
flash_timer = 0

sprite_order = [0, 6, 7, 1, 2, 3, 5, 8, 4]

# =================================
# Config / Save
# =================================
CONFIG_PATH = "/save_files/config.txt"
SAVE_DIR    = "/save_files"

DEFAULTS = {
    "brightness": 8,
    "volume":     8,
    "sleep":      3,
}

def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, _, val = line.partition("=")
                    key = key.strip()
                    if key in cfg:
                        cfg[key] = int(val.strip())
    except OSError:
        pass
    return cfg

def save_config():
    try:
        with open(CONFIG_PATH, "w") as f:
            f.write("brightness={}\n".format(s_brightness))
            f.write("volume={}\n".format(s_volume))
            f.write("sleep={}\n".format(s_sleep))
    except OSError:
        pass

def load_save(game_name):
    """Returns a dict of key=value strings, or {} if no save exists."""
    path = "{}/{}.sav".format(SAVE_DIR, game_name)
    data = {}
    try:
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if "=" in line:
                    key, _, val = line.partition("=")
                    data[key.strip()] = val.strip()
    except OSError:
        pass
    return data

def write_save(game_name, data_dict):
    """Writes a dict of key=value pairs to /save_files/<game_name>.sav"""
    path = "{}/{}.sav".format(SAVE_DIR, game_name)
    try:
        with open(path, "w") as f:
            for key, val in data_dict.items():
                f.write("{}={}\n".format(key, val))
    except OSError:
        pass

# =================================
# Settings state  (loaded from config)
# =================================
_cfg        = load_config()
s_brightness = _cfg["brightness"]
s_volume     = _cfg["volume"]
s_sleep      = _cfg["sleep"]

# Apply loaded settings immediately
backlight(s_brightness * 6)

in_settings    = False
settings_index = 0

SLEEP_OPTIONS   = ["1 MIN", "5 MIN", "10 MIN", "OFF"]
SETTINGS_LABELS = ["BRIGHTNESS", "VOLUME", "SLEEP"]

# =================================
# Starfield
# =================================
NUM_STARS   = 40
stars       = [(random.randint(0, 119), random.randint(0, 119), random.randint(1, 3)) for _ in range(NUM_STARS)]
star_twinkle = [random.randint(0, 30) for _ in range(NUM_STARS)]

# =================================
# Helpers
# =================================
def get_item_angle(index):
    return 360.0 / filecount * index

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

# =================================
# Shared background
# =================================
def draw_stars(tick):
    for i, (sx, sy, sz) in enumerate(stars):
        star_twinkle[i] = (star_twinkle[i] + 1) % 32
        brightness = 8 + int(4 * math.sin(math.radians(star_twinkle[i] * 11.25)))
        if sz == 1:
            pen(brightness - 3, brightness - 3, brightness)
        elif sz == 2:
            pen(brightness, brightness, brightness)
        else:
            pen(brightness + 2, brightness, brightness + 1)
        pixel(sx, sy)

def draw_gradient_bg():
    for row in range(120):
        t = row / 120
        pen(int(1 + t * 3), int(1 + t * 2), int(4 + t * 8))
        frect(0, row, 120, 1)

def draw_ground_plane():
    pen(4, 3, 9); frect(0, 74, 120, 1)
    pen(3, 2, 7); frect(0, 75, 120, 1)
    pen(2, 1, 5); frect(0, 76, 120, 1)
    for col in range(0, 121, 12):
        pen(3, 2, 8)
        line(col, 119, 60, 74)
    for row_step in range(4):
        gy = 80 + row_step * 12
        if gy < 120:
            pen(3, 2, 8)
            frect(0, gy, 120, 1)

def draw_vignette():
    pen(0, 0, 1)
    for x in range(120):
        pixel(x, 0); pixel(x, 1)
    for y in range(120):
        pixel(0, y); pixel(1, y)
        pixel(118, y); pixel(119, y)

def draw_battery(voltage_val):
    bx, by = 100, 3
    pen(3, 3, 5); frect(bx, by, 14, 7)
    pen(4, 4, 6); rect(bx, by, 14, 7)
    pen(4, 4, 6); frect(bx + 14, by + 2, 2, 3)
    segments = min(4, max(0, int(voltage_val)))
    for s in range(segments):
        if segments >= 3: pen(4, 12, 5)
        elif segments == 2: pen(13, 11, 2)
        else: pen(13, 3, 3)
        frect(bx + 1 + s * 3, by + 1, 2, 5)

def draw_header(tick, voltage_val, title="GAME SELECT"):
    pen(1, 1, 3); frect(0, 0, 120, 14)
    pen(5, 4, 12); frect(0, 13, 120, 1)
    pen(14, 12, 15) if (tick // 180) % 2 == 0 else pen(15, 14, 15)
    tw, _ = measure(title)
    text(title, int(60 - tw / 2), 3)
    draw_battery(voltage_val)

# =================================
# Main menu draws
# =================================
def draw_carousel_shadow(x, y, scale, depth):
    shadow_w = int(scale * 0.9)
    shadow_h = max(2, int(scale * 0.2))
    sx = int(x - shadow_w / 2)
    sy = int(y + scale * 0.4)
    pen(0, 0, max(0, min(5, int(depth * 5))))
    for row in range(shadow_h):
        t = row / max(1, shadow_h - 1)
        shrink = int(shadow_w * 0.15 * abs(t - 0.5) * 2)
        frect(sx + shrink, sy + row, shadow_w - shrink * 2, 1)

def draw_label_panel(label, flash):
    panel_y = 93
    pen(1, 1, 4); frect(0, panel_y, 120, 27)
    if flash > 0:
        glow = min(15, 8 + flash)
        pen(glow, int(glow * 0.7), 15)
    else:
        pen(6, 4, 14)
    frect(0, panel_y, 120, 1)
    pen(0, 0, 2)
    for row in range(panel_y + 1, 120, 2):
        frect(0, row, 120, 1)
    label_w, _ = measure(label)
    tx = int(60 - label_w / 2)
    ty = panel_y + 8
    pen(8, 6, 15); text(label, tx + 1, ty + 1)
    pen(15, 14, 15); text(label, tx, ty)
    pen(6, 4, 14)
    frect(2, panel_y + 2, 4, 1); frect(2, panel_y + 2, 1, 4)
    frect(113, panel_y + 2, 4, 1); frect(116, panel_y + 2, 1, 4)

def draw_nav_hints():
    pen(5, 4, 10)
    text("<", 4, 52)
    text(">", 111, 52)

# =================================
# Settings menu draws
# =================================
def _draw_bar(x, y, w, value, max_val, active):
    pen(2, 2, 5); frect(x, y, w, 5)
    fill_w = int(w * value / max_val)
    pen(9, 6, 15) if active else pen(5, 4, 10)
    frect(x, y, fill_w, 5)
    tx = x + fill_w
    pen(15, 14, 15); frect(tx - 1, y - 1, 2, 7)

def _draw_cycle(x, y, options, index, active):
    pen(9, 6, 15) if active else pen(5, 4, 10)
    text("<", x, y)
    lbl = options[index]
    lw, _ = measure(lbl)
    pen(15, 14, 15) if active else pen(10, 9, 15)
    text(lbl, x + 10, y)
    pen(9, 6, 15) if active else pen(5, 4, 10)
    text(">", x + 10 + lw + 3, y)

def draw_settings(tick):
    px, py, pw, ph = 8, 18, 104, 90
    pen(1, 1, 4); frect(px, py, pw, ph)
    pen(6, 4, 14); rect(px, py, pw, ph)
    pen(0, 0, 2)
    for row in range(py + 1, py + ph, 2):
        frect(px + 1, row, pw - 2, 1)
    pen(8, 6, 15)
    frect(px + 2, py + 2, 5, 1);     frect(px + 2, py + 2, 1, 5)
    frect(px + pw - 7, py + 2, 5, 1); frect(px + pw - 3, py + 2, 1, 5)
    frect(px + 2, py + ph - 3, 5, 1); frect(px + 2, py + ph - 7, 1, 5)
    frect(px + pw - 7, py + ph - 3, 5, 1); frect(px + pw - 3, py + ph - 7, 1, 5)

    row_start_y = py + 14
    row_h = 22

    for idx, label in enumerate(SETTINGS_LABELS):
        ry = row_start_y + idx * row_h
        if idx == settings_index:
            pen(3, 2, 9); frect(px + 2, ry - 2, pw - 4, row_h - 2)
            pen(6, 4, 14); frect(px + 2, ry - 2, pw - 4, 1)
        pen(15, 14, 15) if idx == settings_index else pen(10, 9, 15)
        text(label, px + 8, ry + 1)
        active = (idx == settings_index)
        if label == "BRIGHTNESS":
            _draw_bar(px + 8, ry + 10, 88, s_brightness, 15, active)
        elif label == "VOLUME":
            _draw_bar(px + 8, ry + 10, 88, s_volume, 15, active)
        elif label == "SLEEP":
            _draw_cycle(px + 8, ry + 10, SLEEP_OPTIONS, s_sleep, active)

    pen(5, 4, 10)
    hint = "< > ADJUST  B BACK"
    hw, _ = measure(hint)
    text(hint, int(60 - hw / 2), py + ph - 9)

# =================================
# Update
# =================================
def update(tick):
    global selected, accumulated_angle, voltage, flash_timer
    global in_settings, settings_index, s_brightness, s_volume, s_sleep

    if in_settings:
        if pressed(UP):
            settings_index = (settings_index - 1) % len(SETTINGS_LABELS)
            blip.play(1600, 20, 80)
        if pressed(DOWN):
            settings_index = (settings_index + 1) % len(SETTINGS_LABELS)
            blip.play(1600, 20, 80)

        label = SETTINGS_LABELS[settings_index]
        if pressed(LEFT):
            if label == "BRIGHTNESS":
                s_brightness = clamp(s_brightness - 1, 1, 15)
                backlight(s_brightness * 6)
                save_config()
            elif label == "VOLUME":
                s_volume = clamp(s_volume - 1, 0, 15)
                save_config()
            elif label == "SLEEP":
                s_sleep = clamp(s_sleep - 1, 0, len(SLEEP_OPTIONS) - 1)
                save_config()
            blip.play(1400, 20, s_volume * 6)

        if pressed(RIGHT):
            if label == "BRIGHTNESS":
                s_brightness = clamp(s_brightness + 1, 1, 15)
                backlight(s_brightness * 6)
                save_config()
            elif label == "VOLUME":
                s_volume = clamp(s_volume + 1, 0, 15)
                save_config()
            elif label == "SLEEP":
                s_sleep = clamp(s_sleep + 1, 0, len(SLEEP_OPTIONS) - 1)
                save_config()
            blip.play(1800, 20, s_volume * 6)

        if pressed(B):
            in_settings = False
            blip.play(1200, 30, 100)

    else:
        if pressed(LEFT):
            selected = (selected - 1) % filecount
            accumulated_angle += step_angle
            blip.play(1600, 30, 100)
            flash_timer = 12
        if pressed(RIGHT):
            selected = (selected + 1) % filecount
            accumulated_angle -= step_angle
            blip.play(1800, 30, 100)
            flash_timer = 12
        if pressed(A):
            ding.play(880, 30, 100)
            quit()
        if pressed(Y):
            in_settings = True
            settings_index = 0
            blip.play(1600, 30, 100)

    if tick % 1000 == 0:
        voltage = battery()
    if flash_timer > 0:
        flash_timer -= 1

# =================================
# Draw
# =================================
def draw(tick):
    global current_angle

    draw_gradient_bg()
    draw_stars(tick)
    draw_ground_plane()

    if in_settings:
        draw_header(tick, voltage, title="SETTINGS")
        draw_settings(tick)
    else:
        draw_header(tick, voltage, title="GAME SELECT")
        draw_nav_hints()

        pen(4, 3, 8)
        text("Y", 3, 3)

        current_angle += (accumulated_angle - current_angle) / 10.0

        order = sorted(
            range(filecount),
            key=lambda i: math.cos(math.radians(get_item_angle(i) + current_angle))
        )

        for i in order:
            item_angle = get_item_angle(i) + current_angle
            cos_a = math.cos(math.radians(item_angle))
            sin_a = math.sin(math.radians(item_angle))
            scale = ((cos_a + 1.0) * 8.0) + 7.0
            depth = (cos_a + 1.0) / 2.0
            cx = int(60 + sin_a * 45.0)
            cy = int(57 + cos_a * 20.0)

            draw_carousel_shadow(cx, cy, scale, depth)
            pen(6, 6, 8) if depth < 0.35 else pen(15, 15, 15)
            si = sprite_order[i] if i < len(sprite_order) else 0
            sprite(si, int(cx - scale / 2), int(cy - scale / 2), 1, 1, int(scale), int(scale))

        label = files[selected].replace(".py", "").replace("_", " ").upper()
        draw_label_panel(label, flash_timer)

    draw_vignette()

# =================================
# Start launcher
# =================================
start()
__launch_file__ = files[selected]
module_name = "games." + __launch_file__[:-3]  # strips ".py"
__import__(module_name)
# game_file = files[selected]
# os.chdir("/games")
# exec(open(game_file).read(), globals())