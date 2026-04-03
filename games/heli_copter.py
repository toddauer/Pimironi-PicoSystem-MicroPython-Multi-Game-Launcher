from picosystem import *
import math
import random, machine

# =========================================================
# CONFIG / SAVE
# =========================================================
GAME_TITLE = "swing_copter"
CONFIG_PATH = "/save_files/config.txt"
SAVE_PATH   = "/save_files/"+GAME_TITLE+"_hi.txt"



def load_hi():
    try:
        with open(SAVE_PATH, "r") as f:
            return int(f.read().strip())
    except OSError:
        return 0

def save_hi(score):
    try:
        with open(SAVE_PATH, "w") as f:
            f.write(str(score))
    except OSError:
        pass
    
# =================================
# Constants
# =================================
SCREEN_W  = 120
SCREEN_H  = 120

SWING_SPEED = 0.8
PLAYER_Y    = 72

# Difficulty — all values are at score=0; they scale toward *_MAX as score rises
GAP_START    = 38    # opening width at start
GAP_MIN      = 24    # narrowest the gap ever gets
SPACING_START= 62    # world px between gates at start
SPACING_MIN  = 44    # closest gates ever get
HAMMER_START = 0.9   # deg/tick at start
HAMMER_MAX   = 2.2   # fastest hammers ever swing
SCROLL_START = 0.55
SCROLL_MAX   = 1.5

COPTER_W  = 8
COPTER_H  = 6
ROTOR_LEN = 5

GATE_H    = 6
HAMMER_ARM= 14

# =================================
# Palette
# =================================
BRICK_DARK  = (10, 5, 2)
BRICK_MID   = (13, 7, 3)
BRICK_LIGHT = (15, 10, 5)
GRASS_DARK  = (3, 10, 2)
GRASS_MID   = (5, 13, 3)
GRASS_LIGHT = (8, 15, 5)
GOLD        = (15, 13, 2)
HANDLE_C    = (10, 6, 2)
HEAD_C      = (9, 9, 9)
HEAD_H      = (13, 13, 13)

# =================================
# Music
# =================================
# Simple looping melody — (frequency_hz, duration_ticks)
# Inspired by a cheerful 8-bit feel; avoids anything copyrighted
MELODY = [
    (523, 8), (659, 8), (784, 8), (659, 8),
    (523, 8), (392, 8), (330, 12),(392, 4),
    (523, 8), (587, 8), (659, 8), (587, 8),
    (523, 8), (440, 8), (392, 16),
    (659, 8), (784, 8), (880, 8), (784, 8),
    (659, 8), (523, 8), (440, 12),(330, 4),
    (392, 8), (440, 8), (523, 8), (587, 8),
    (659, 16),(523, 8), (392, 16),
]
music_voice  = Voice(2, 4, 80, 8)   # fast attack, short decay, quiet sustain
music_note   = 0
music_timer  = 0
music_on     = True   # toggled with B

# =================================
# State
# =================================
STATE_TITLE = 0
STATE_PLAY  = 1
STATE_DEAD  = 2

state = STATE_TITLE
score = 0
best  = 0

px        = float(SCREEN_W // 2)
vx        = SWING_SPEED
scroll_y  = 0.0
gates     = []
clouds    = []
death_flash = 0
rotor_tick  = 0

# =================================
# Difficulty helpers
# =================================
def diff():
    """0.0 at score=0, approaches 1.0 as score rises."""
    return min(1.0, score / 30.0)

def cur_gap():
    return int(GAP_START - (GAP_START - GAP_MIN) * diff())

def cur_spacing():
    return int(SPACING_START - (SPACING_START - SPACING_MIN) * diff())

def cur_hammer_speed():
    return HAMMER_START + (HAMMER_MAX - HAMMER_START) * diff()

def cur_scroll():
    return min(SCROLL_MAX, SCROLL_START + score * 0.015)

# =================================
# Helpers
# =================================
def gate_sy(world_y):
    return int(world_y + scroll_y)

def copter_rect():
    return (int(px) - COPTER_W//2, PLAYER_Y - COPTER_H//2, COPTER_W, COPTER_H)

def rects_overlap(ax, ay, aw, ah, bx, by, bw, bh):
    return ax < bx+bw and ax+aw > bx and ay < by+bh and ay+ah > by

def spawn_gate(world_y):
    gap   = cur_gap()
    margin = 14 + gap // 2
    cx = random.randint(margin, SCREEN_W - margin)
    la = float(random.randint(-30, 30))
    ra = float(random.randint(150, 210))
    gates.append([float(world_y), cx, la, ra, False, gap])

def reset():
    global px, vx, scroll_y, gates, clouds, score, death_flash, rotor_tick
    global music_note, music_timer
    px = float(SCREEN_W // 2)
    vx = SWING_SPEED
    scroll_y = 0.0
    score = 0
    death_flash = 0
    rotor_tick  = 0
    music_note  = 0
    music_timer = 0
    gates  = []
    clouds = []
    first_y = -SCREEN_H // 2
    for i in range(8):
        spawn_gate(first_y - i * SPACING_START)
    for _ in range(5):
        spawn_cloud(float(random.randint(-SCREEN_H * 2, 20)))

def spawn_cloud(world_y):
    cx = float(random.randint(5, 100))
    cw = random.randint(14, 26)
    clouds.append([cx, float(world_y), cw])

# =================================
# Music tick
# =================================
def tick_music():
    global music_note, music_timer
    if not music_on or state == STATE_DEAD:
        return
    music_timer -= 1
    if music_timer <= 0:
        freq, dur = MELODY[music_note]
        music_voice.play(freq, dur * 16, 40)
        music_timer = dur
        music_note  = (music_note + 1) % len(MELODY)

# =================================
# Draw: background (banded, not per-row)
# =================================
def draw_bg():
    # 4 bands instead of 120 individual rows — much faster
    pen(5, 10, 15); frect(0,   0,  SCREEN_W, 30)
    pen(6, 11, 15); frect(0,  30,  SCREEN_W, 30)
    pen(7, 12, 15); frect(0,  60,  SCREEN_W, 30)
    pen(7, 12, 15); frect(0,  90,  SCREEN_W, 30)

def draw_clouds():
    for c in clouds:
        sy = int(c[1] + scroll_y)
        if sy < -10 or sy > SCREEN_H + 10:
            continue
        cx, cw = int(c[0]), c[2]
        pen(15, 15, 15)
        frect(cx, sy, cw, 5)
        frect(cx+2, sy-3, cw-4, 3)
        pen(14, 14, 15)
        frect(cx+1, sy+1, cw-2, 3)

# =================================
# Draw: platform (no per-pixel loops)
# =================================
def draw_platform(x, y, w):
    if w <= 0:
        return
    # Brick body
    pen(*BRICK_MID);  frect(x, y, w, GATE_H)
    # Single mortar line
    pen(*BRICK_DARK); frect(x, y + GATE_H//2, w, 1)
    # Top highlight
    pen(*BRICK_LIGHT);frect(x, y, w, 1)
    # Bottom shadow
    pen(*BRICK_DARK); frect(x, y + GATE_H - 1, w, 1)
    # Grass cap (3 frects, no pixel loops)
    pen(*GRASS_MID);  frect(x, y - 3, w, 3)
    pen(*GRASS_LIGHT);frect(x, y - 3, w, 1)
    pen(*GRASS_DARK); frect(x, y - 4, w, 1)

# =================================
# Draw: hammer
# =================================
def draw_hammer(pivot_x, pivot_y, angle_deg):
    rad   = math.radians(angle_deg)
    tip_x = int(pivot_x + math.sin(rad) * HAMMER_ARM)
    tip_y = int(pivot_y + math.cos(rad) * HAMMER_ARM)
    pen(*HANDLE_C); line(pivot_x, pivot_y, tip_x, tip_y)
    pen(*HEAD_C);   frect(tip_x-3, tip_y-3, 7, 6)
    pen(*HEAD_H);   frect(tip_x-3, tip_y-3, 7, 1)
    pen(*HEAD_H);   frect(tip_x-3, tip_y-3, 1, 6)

# =================================
# Draw: gate row
# =================================
def draw_gate(world_y, gap_cx, la, ra, gap):
    sy = gate_sy(world_y)
    # Tight cull — skip anything not near screen
    if sy < -HAMMER_ARM - 10 or sy > SCREEN_H + 10:
        return
    half    = gap // 2
    left_w  = gap_cx - half
    right_x = gap_cx + half
    right_w = SCREEN_W - right_x
    draw_platform(0,       sy, left_w)
    draw_platform(right_x, sy, right_w)
    draw_hammer(gap_cx - half, sy + GATE_H, la)
    draw_hammer(gap_cx + half, sy + GATE_H, ra)

# =================================
# Draw: copter
# =================================
def draw_copter(x, rtick):
    y = PLAYER_Y
    x = int(x)
    phase = (rtick // 2) % 4
    pen(13, 13, 15)
    if phase in (0, 2):
        frect(x - ROTOR_LEN, y - COPTER_H//2 - 2, ROTOR_LEN*2, 2)
    else:
        frect(x - 1, y - COPTER_H//2 - ROTOR_LEN, 2, ROTOR_LEN*2)
    pen(10, 14, 12); frect(x - COPTER_W//2, y - COPTER_H//2, COPTER_W, COPTER_H)
    pen(6, 10, 15);  frect(x - 1, y - 1, 3, 3)
    pen(8, 12, 10);  frect(x + COPTER_W//2, y - 2, 3, 2)

# =================================
# Draw: HUD
# =================================
def draw_hud(sc, hi):
    pen(*GOLD)
    frect(2,2,5,7); frect(3,1,3,1); frect(3,8,3,1)
    pen(15,15,5);   frect(3,4,3,1)
    pen(15,14,15);  text("x"+str(sc), 9, 2)
    pen(13,13,13);  text("B"+str(hi), 88, 2)
    if not music_on:
        pen(13,5,5); text("M", 110, 2)

# =================================
# Draw: title
# =================================
def draw_title():
    draw_bg()
    draw_clouds()
    draw_platform(0, 108, SCREEN_W)
    pen(14,3,2);  frect(8,22,104,40)
    pen(15,10,5); rect(8,22,104,40)
    pen(15,14,3)
    t1="SWING COPTERS"; t1w,_=measure(t1); text(t1,int(60-t1w/2),28)
    pen(*GRASS_MID)
    t3="TAP A TO FLIP"; t3w,_=measure(t3); text(t3,int(60-t3w/2),74)
    pen(10,10,12)
    t4="B = MUSIC ON/OFF"; t4w,_=measure(t4); text(t4,int(60-t4w/2),84)
    pen(15,15,15)
    t5="PRESS A TO START"; t5w,_=measure(t5); text(t5,int(60-t5w/2),96)

# =================================
# Draw: death
# =================================
def draw_dead(sc, hi):
    pen(10,3,2);  frect(12,38,96,52)
    pen(15,8,5);  rect(12,38,96,52)
    pen(15,15,5); msg="GAME OVER"; mw,_=measure(msg); text(msg,int(60-mw/2),43)
    pen(15,14,15);s1="SCORE: "+str(sc); s1w,_=measure(s1); text(s1,int(60-s1w/2),56)
    if sc>=hi and sc>0:
        pen(*GOLD);   s2="NEW BEST!";  s2w,_=measure(s2); text(s2,int(60-s2w/2),67)
    else:
        pen(13,13,13);s2="BEST: "+str(hi); s2w,_=measure(s2); text(s2,int(60-s2w/2),67)
    pen(*GRASS_MID); s3="A TO RETRY"; s3w,_=measure(s3); text(s3,int(60-s3w/2),80)

# =================================
# Collision
# =================================
def check_collisions():
    global state, death_flash, best
    cx, cy, cw, ch = copter_rect()
    hspd = cur_hammer_speed()
    for gate in gates:
        gy, gcx, la, ra, scored, gap = gate
        sy  = gate_sy(gy)
        # Skip gates clearly not near the player's Y
        if sy > PLAYER_Y + 20 or sy < PLAYER_Y - 30:
            continue
        half = gap // 2
        # Platform bars
        if rects_overlap(cx,cy,cw,ch, 0, sy-4, gcx-half, GATE_H+5):
            if score>best: best=score
            death_flash=10; state=STATE_DEAD; return
        if rects_overlap(cx,cy,cw,ch, gcx+half, sy-4, SCREEN_W, GATE_H+5):
            if score>best: best=score
            death_flash=10; state=STATE_DEAD; return
        # Hammer heads
        lrad=math.radians(la)
        lhx=int((gcx-half)+math.sin(lrad)*HAMMER_ARM)
        lhy=int((sy+GATE_H)+math.cos(lrad)*HAMMER_ARM)
        if rects_overlap(cx,cy,cw,ch, lhx-3,lhy-3,7,6):
            if score>best: best=score
            death_flash=10; state=STATE_DEAD; return
        rrad=math.radians(ra)
        rhx=int((gcx+half)+math.sin(rrad)*HAMMER_ARM)
        rhy=int((sy+GATE_H)+math.cos(rrad)*HAMMER_ARM)
        if rects_overlap(cx,cy,cw,ch, rhx-3,rhy-3,7,6):
            if score>best: best=score
            death_flash=10; state=STATE_DEAD; return

# =================================
# Update
# =================================
def update(tick):
    global state, px, vx, scroll_y, score, death_flash, rotor_tick, music_on

    tick_music()
    
    if pressed(Y):
        machine.soft_reset()

    if state == STATE_TITLE:
        if pressed(A): reset(); state = STATE_PLAY
        if pressed(B): music_on = not music_on
        return

    if state == STATE_DEAD:
        if death_flash > 0: death_flash -= 1
        if pressed(A) and death_flash == 0: reset(); state = STATE_PLAY
        if pressed(B): music_on = not music_on
        return

    # === Playing ===
    rotor_tick += 1

    if pressed(B): music_on = not music_on

    if pressed(A): vx = -vx

    px += vx
    if px < COPTER_W//2:
        px = float(COPTER_W//2); vx = abs(vx)
    if px > SCREEN_W - COPTER_W//2:
        px = float(SCREEN_W - COPTER_W//2); vx = -abs(vx)

    scroll_y += cur_scroll()

    hs = cur_hammer_speed()
    for gate in gates:
        gate[2] += hs
        gate[3] -= hs
        if gate[2] >  360: gate[2] -= 360
        if gate[3] < -360: gate[3] += 360
        if not gate[4] and gate_sy(gate[0]) > PLAYER_Y:
            gate[4] = True
            score += 1

    # Spawn ahead of topmost gate
    sp = cur_spacing()
    if gates:
        topmost = min(g[0] for g in gates)
        while topmost + scroll_y > -sp * 2:
            topmost -= sp
            spawn_gate(topmost)

    # Cull gates below screen
    gates[:] = [g for g in gates if gate_sy(g[0]) < SCREEN_H + 50]

    # Recycle clouds
    for c in clouds:
        if c[1] + scroll_y > SCREEN_H + 10:
            c[1] -= SCREEN_H + 50
            c[0] = float(random.randint(5, 100))
            c[2] = random.randint(14, 26)

    check_collisions()

# =================================
# Draw
# =================================
def draw(tick):
    if state == STATE_TITLE:
        draw_title()
        return

    draw_bg()
    draw_clouds()

    for gate in gates:
        draw_gate(gate[0], gate[1], gate[2], gate[3], gate[5])

    if state == STATE_PLAY:
        draw_copter(px, rotor_tick)
    else:
        if death_flash > 0 and death_flash % 2 == 0:
            pen(15,4,2); frect(0,0,SCREEN_W,SCREEN_H)

    draw_hud(score, best)

    if state == STATE_DEAD:
        draw_dead(score, best)

# =================================
# Start
# =================================
reset()
start()
