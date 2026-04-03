from picosystem import *
import random, machine

# =========================================================
# CONFIG / SAVE
# =========================================================
GAME_TITLE = "hopper"
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
SCREEN_W = 120
SCREEN_H = 120

TILE      = 16   # each lane is 16px tall, 7.5 tiles wide (we use px directly)
LANES     = 9    # 1 safe start + 3 traffic + 1 safe median + 2 river + 1 safe bank + 1 goal row
FROG_W    = 10
FROG_H    = 10
FROG_STEP = 16   # hops one lane at a time

# Lane Y positions (top of each lane), bottom to top on screen
# Screen layout (y=0 top, y=119 bottom):
#   y=  0-15  : goal row (lily pads)
#   y= 16-31  : river lane 2
#   y= 32-47  : river lane 1
#   y= 48-63  : safe bank (grass median)
#   y= 64-79  : traffic lane 3
#   y= 80-95  : traffic lane 2
#   y= 96-111 : traffic lane 1
#   y=112-119 : safe start strip

GOAL_Y      =  4
BANK_Y      = 48
START_Y     = 112

FROG_START_X = 56
FROG_START_Y = 112

LIVES_MAX = 3

# =================================
# Palette
# =================================
# Road
ROAD_C   = (4, 4, 4)
ROAD_LN  = (10, 10, 2)   # lane markings
# Grass / safe
GRASS_D  = (2, 8, 2)
GRASS_M  = (3, 11, 3)
GRASS_L  = (5, 14, 4)
# Water
WATER_D  = (1, 4, 12)
WATER_M  = (2, 6, 14)
WATER_L  = (4, 9, 15)
# Car colours cycling
CAR_COLS = [(14,3,2),(13,10,2),(2,10,13),(12,2,13),(14,9,2)]
# Log
LOG_D    = (8, 5, 2)
LOG_M    = (11, 7, 3)
LOG_L    = (13, 9, 4)
# Lily pad goal
LILY_D   = (2, 10, 2)
LILY_M   = (3, 13, 3)
# Frog
FROG_BD  = (3, 12, 3)
FROG_BM  = (5, 14, 5)
FROG_EY  = (15, 15, 15)
FROG_DD  = (2, 8, 2)   # dead frog

# =================================
# State
# =================================
STATE_TITLE  = 0
STATE_PLAY   = 1
STATE_DEAD   = 2   # brief death pause
STATE_WIN    = 3   # reached goal
STATE_OVER   = 4   # out of lives

state  = STATE_TITLE
lives  = LIVES_MAX
score  = 0
hi_score = load_hi()
level  = 1

fx = float(FROG_START_X)
fy = float(FROG_START_Y)

death_timer = 0
win_timer   = 0
goals_hit   = 0   # how many lily pads filled this level (max 3 per level)
goal_filled = [False, False, False]  # three goal slots

# Input debounce
last_up = last_down = last_left = last_right = False

# Sounds
blip  = Voice(5, 5, 40, 10)
croak = Voice(10, 20, 60, 30)
splat = Voice(2, 30, 80, 50)
ding  = Voice(5, 10, 100, 200)
ding.effects(reverb=40)

# Music
MELODY = [
    (523,6),(659,6),(784,6),(659,6),
    (523,6),(440,6),(392,12),
    (523,6),(587,6),(659,6),(587,6),
    (523,6),(392,6),(330,12),
    (659,6),(784,6),(880,6),(784,6),
    (659,6),(523,6),(440,12),
    (392,6),(440,6),(523,6),(587,6),
    (659,12),(523,6),(392,12),
]
music_voice = Voice(2, 6, 60, 10)
music_note  = 0
music_timer = 0
music_on    = True

def tick_music():
    global music_note, music_timer
    if not music_on:
        return
    music_timer -= 1
    if music_timer <= 0:
        freq, dur = MELODY[music_note]
        music_voice.play(freq, dur * 16, 35)
        music_timer = dur
        music_note = (music_note + 1) % len(MELODY)

# =================================
# Traffic lanes: [y, speed, direction, car_list]
# car_list: [x, width, color_index]
# direction: +1 = right, -1 = left
# =================================
def make_traffic(spd_scale):
    return [
        # lane_y, speed,              dir, cars
        [96, 0.55 * spd_scale,  1, []],  # traffic 1 (slow, right)
        [80, 0.80 * spd_scale, -1, []],  # traffic 2 (medium, left)
        [64, 1.05 * spd_scale,  1, []],  # traffic 3 (fast, right)
    ]

def make_river(spd_scale):
    return [
        # lane_y, speed,              dir, logs
        [32, 0.45 * spd_scale,  1, []],  # river 1 (right)
        [16, 0.65 * spd_scale, -1, []],  # river 2 (left)
    ]

traffic = []
river   = []

def populate_lane(lane, is_log=False):
    lane[3] = []
    x = 0
    gap_min = 28 if is_log else 22
    gap_max = 60 if is_log else 48
    while x < SCREEN_W + 80:
        w = random.randint(22, 34) if is_log else random.randint(12, 20)
        ci = random.randint(0, len(CAR_COLS)-1)
        lane[3].append([float(x), w, ci])
        x += w + random.randint(gap_min, gap_max)

def reset_level():
    global traffic, river, fx, fy, goal_filled, goals_hit
    fx, fy = float(FROG_START_X), float(FROG_START_Y)
    goal_filled = [False, False, False]
    goals_hit   = 0
    sp = 1.0 + (level - 1) * 0.18
    traffic = make_traffic(sp)
    river   = make_river(sp)
    for lane in traffic:
        populate_lane(lane, is_log=False)
    for lane in river:
        populate_lane(lane, is_log=True)

def reset_game():
    global lives, score, level, death_timer, win_timer
    lives = LIVES_MAX
    score = 0
    level = 1
    death_timer = 0
    win_timer   = 0
    reset_level()

# =================================
# Goal slot X positions (3 lily pads)
# =================================
GOAL_XS = [14, 54, 94]
GOAL_W   = 18

def goal_slot(x):
    """Return slot index 0-2 if x is over a goal, else -1."""
    for i, gx in enumerate(GOAL_XS):
        if abs(x + FROG_W//2 - (gx + GOAL_W//2)) < GOAL_W//2 + 2:
            return i
    return -1

# =================================
# Draw helpers
# =================================
def draw_grass_strip(y, h):
    pen(2,8,2); frect(0, y, SCREEN_W, h)
    pen(3,11,3); frect(0, y, SCREEN_W, 1)
    pen(5,14,4); frect(0, y+1, SCREEN_W, 1)

def draw_road_lane(y):
    pen(4,4,4);  frect(0, y, SCREEN_W, TILE)
    pen(10,10,2); frect(0, y + TILE//2, SCREEN_W, 1)
    pen(6,6,6);    frect(0, y, SCREEN_W, 1)
    pen(6,6,6);    frect(0, y+TILE-1, SCREEN_W, 1)

def draw_water_lane(y):
    pen(1,4,12); frect(0, y, SCREEN_W, TILE)
    pen(2,6,14)
    for wx in range(0, SCREEN_W, 8):
        frect(wx, y+4, 5, 2)
    pen(4,9,15); frect(0, y, SCREEN_W, 1)

def draw_goal_row():
    pen(1,4,12); frect(0, 0, SCREEN_W, TILE)
    for i, gx in enumerate(GOAL_XS):
        if goal_filled[i]:
            pen(3,12,3); frect(gx, 2, GOAL_W, TILE-4)
            pen(15,15,15); frect(gx+3, 4, 2, 2); frect(gx+13, 4, 2, 2)
        else:
            pen(2,10,2);  frect(gx, 4, GOAL_W, TILE-6)
            pen(3,13,3);  frect(gx+2, 5, GOAL_W-4, 2)

def draw_car(x, y, w, ci):
    x = int(x)
    col = CAR_COLS[ci % len(CAR_COLS)]
    pen(col[0],col[1],col[2]); frect(x, y+3, w, 8)
    pen(col[0]//2, col[1]//2, col[2]//2)
    frect(x+2, y+2, w-4, 4)    # windscreen recess
    pen(15,14,5)                # headlights
    frect(x,   y+5, 2, 3)
    frect(x+w-2, y+5, 2, 3)
    pen(3,3,3)                  # wheels
    frect(x+2,   y+10, 3, 2)
    frect(x+w-5, y+10, 3, 2)

def draw_log(x, y, w):
    x = int(x)
    pen(8,5,2);  frect(x, y+2, w, TILE-4)
    pen(11,7,3);  frect(x, y+2, w, 2)
    pen(13,9,4);  frect(x, y+3, w, 1)
    pen(8,5,2);  frect(x, y+TILE-4, w, 2)
    # Wood grain lines
    pen(8,5,2)
    for lx in range(x+4, x+w-2, 6):
        frect(lx, y+3, 1, TILE-6)

def draw_frog(x, y, alive=True):
    x, y = int(x), int(y)
    if not alive:
        pen(2,8,2); frect(x+1,y+3,8,5)
        pen(14,3,2);   frect(x+3,y+4,4,3)
        return
    # Body
    pen(3,12,3); frect(x+2, y+3, 6, 5)
    # Head
    pen(5,14,5); frect(x+3, y+1, 4, 3)
    # Eyes
    pen(15,15,15); pixel(x+3, y+1); pixel(x+6, y+1)
    # Back legs
    pen(3,12,3)
    frect(x,   y+6, 3, 3)
    frect(x+7, y+6, 3, 3)
    # Front legs
    frect(x+1, y+3, 2, 2)
    frect(x+7, y+3, 2, 2)

def draw_hud():
    pen(1,1,2); frect(0, 113, SCREEN_W, 7)
    pen(5,14,5)
    for i in range(lives):
        frect(2 + i*9, 114, 6, 5)
    pen(15,13,2)
    sw, _ = measure(str(score))
    text(str(score), int(60 - sw/2), 114)
    pen(10,10,12)
    text("B"+str(hi_score), 88, 114)
    pen(8,8,10)
    lv = "L"+str(level)
    text(lv, 108, 114)
    if not music_on:
        pen(13,5,5); text("M", 52, 114)

def draw_bg():
    draw_goal_row()
    for lane in river:
        draw_water_lane(lane[0])
    draw_grass_strip(BANK_Y, TILE)
    for lane in traffic:
        draw_road_lane(lane[0])
    draw_grass_strip(START_Y, 8)

def draw_title():
    draw_bg()
    pen(2,8,2);   frect(8,30,104,50)
    pen(5,14,4);  rect(8,30,104,50)
    pen(15,14,3)
    t="HOPPER"; tw,_=measure(t); text(t,int(60-tw/2),36)
    pen(5,14,5)
    draw_frog(54, 48)
    pen(10,14,10)
    t2="A TO START"; t2w,_=measure(t2); text(t2,int(60-t2w/2),62)
    pen(8,8,12)
    t3="arrows = move"; t3w,_=measure(t3); text(t3,int(60-t3w/2),72)

def draw_dead_flash(t):
    if t % 4 < 2:
        draw_frog(fx, fy, alive=False)

def draw_gameover():
    pen(10,2,2);  frect(15,42,90,44)
    pen(15,6,5);  rect(15,42,90,44)
    pen(15,12,5); t="GAME OVER"; tw,_=measure(t); text(t,int(60-tw/2),48)
    pen(15,14,15);t2="SCORE: "+str(score); t2w,_=measure(t2); text(t2,int(60-t2w/2),60)
    if score>=hi_score and score>0:
        pen(15,13,2);   t3="NEW BEST!"; t3w,_=measure(t3); text(t3,int(60-t3w/2),70)
    else:
        pen(12,12,12);t3="BEST:"+str(hi_score); t3w,_=measure(t3); text(t3,int(60-t3w/2),70)
    pen(3,11,3); t4="A TO RETRY"; t4w,_=measure(t4); text(t4,int(60-t4w/2),80)

# =================================
# Collision / riding
# =================================
def frog_on_log():
    """If frog is in river rows, return the log speed+dir it's riding, or None."""
    for lane in river:
        ly = lane[0]
        if abs(fy - ly) < TILE - 2:
            for log in lane[3]:
                lx = int(log[0])
                lw = log[1]
                if fx + 2 < lx + lw and fx + FROG_W - 2 > lx:
                    return lane[1] * lane[2]   # speed * direction
    return None

def frog_in_river():
    for lane in river:
        ly = lane[0]
        if abs(fy - ly) < TILE - 2:
            return True
    return False

def frog_hit_car():
    for lane in traffic:
        ly = lane[0]
        if abs(fy - ly) < TILE - 2:
            for car in lane[3]:
                cx = int(car[0])
                cw = car[1]
                if fx + 2 < cx + cw and fx + FROG_W - 2 > cx:
                    return True
    return False

# =================================
# Die / win helpers
# =================================
def kill_frog():
    global state, death_timer, lives, hi_score, score
    splat.play(120, 60, 80)
    death_timer = 40
    state = STATE_DEAD
    lives -= 1
    if lives < 0: lives = 0

def frog_win():
    global state, win_timer, score, goals_hit, goal_filled, level, hi_score
    slot = goal_slot(fx)
    if slot >= 0 and not goal_filled[slot]:
        goal_filled[slot] = True
        goals_hit += 1
        score += 10 + level * 5
        ding.play(880, 40, 100)
    win_timer = 30
    state = STATE_WIN

# =================================
# Update
# =================================
def update(tick):
    global state, fx, fy, death_timer, win_timer, lives, score, hi_score, level
    global last_up, last_down, last_left, last_right, music_on, music_note, music_timer

    tick_music()
    
    if pressed(Y):
        machine.soft_reset()
    
    if pressed(B):
        music_on = not music_on
        music_note = 0
        music_timer = 0

    up    = pressed(UP)
    down  = pressed(DOWN)
    left  = pressed(LEFT)
    right = pressed(RIGHT)

    if state == STATE_TITLE:
        if pressed(A): reset_game(); state = STATE_PLAY
        return

    if state == STATE_OVER:
        if pressed(A): reset_game(); state = STATE_PLAY
        return

    if state == STATE_DEAD:
        death_timer -= 1
        if death_timer <= 0:
            if lives <= 0:
                hi_score = load_hi()
                if score > hi_score:
                    hi_score = score
                    save_hi(score)
                state = STATE_OVER
            else:
                fx, fy = float(FROG_START_X), float(FROG_START_Y)
                state = STATE_PLAY
        return

    if state == STATE_WIN:
        win_timer -= 1
        if win_timer <= 0:
            if goals_hit >= 3:
                # Level complete — advance
                score += 20 + level * 10
                level += 1
                reset_level()
            else:
                fx, fy = float(FROG_START_X), float(FROG_START_Y)
            state = STATE_PLAY
        return

    # === Playing ===

    # Move on fresh press only
    moved = False
    if up    and not last_up:
        fy -= FROG_STEP; moved = True; blip.play(800, 10, 60)
    if down  and not last_down:
        fy += FROG_STEP; moved = True; blip.play(600, 10, 60)
    if left  and not last_left:
        fx -= FROG_STEP; moved = True; blip.play(700, 10, 60)
    if right and not last_right:
        fx += FROG_STEP; moved = True; blip.play(700, 10, 60)

    last_up, last_down, last_left, last_right = up, down, left, right

    # Clamp horizontal
    if fx < 0: fx = 0.0
    if fx > SCREEN_W - FROG_W: fx = float(SCREEN_W - FROG_W)
    # Clamp vertical — can't go below start or above goal
    if fy > START_Y: fy = float(START_Y)
    if fy < 0:       fy = 0.0

    # Scroll traffic
    for lane in traffic:
        spd = lane[1] * lane[2]
        for car in lane[3]:
            car[0] += spd
            if spd > 0 and car[0] > SCREEN_W + 10:
                car[0] = float(-car[1] - random.randint(10, 40))
            elif spd < 0 and car[0] + car[1] < -10:
                car[0] = float(SCREEN_W + random.randint(10, 40))

    # Scroll river logs + carry frog
    ride = frog_on_log()
    for lane in river:
        spd = lane[1] * lane[2]
        for log in lane[3]:
            log[0] += spd
            if spd > 0 and log[0] > SCREEN_W + 10:
                log[0] = float(-log[1] - random.randint(20, 50))
            elif spd < 0 and log[0] + log[1] < -10:
                log[0] = float(SCREEN_W + random.randint(20, 50))

    if ride is not None:
        fx += ride

    # Frog off screen sideways on log → drown
    if fx < -FROG_W or fx > SCREEN_W:
        kill_frog(); return

    # In river but not on log → drown
    if frog_in_river() and ride is None:
        kill_frog(); return

    # Hit by car
    if frog_hit_car():
        kill_frog(); return

    # Reached goal row
    if fy <= GOAL_Y:
        slot = goal_slot(fx)
        if slot < 0 or goal_filled[slot]:
            kill_frog()  # missed pad or already filled
        else:
            frog_win()

# =================================
# Draw
# =================================
def draw(tick):
    if state == STATE_TITLE:
        draw_title()
        return

    draw_bg()

    # Draw logs
    for lane in river:
        ly = lane[0]
        for log in lane[3]:
            draw_log(log[0], ly, log[1])

    # Draw cars
    for lane in traffic:
        ly = lane[0]
        for car in lane[3]:
            draw_car(car[0], ly, car[1], car[2])

    # Draw frog
    if state == STATE_PLAY or state == STATE_WIN:
        draw_frog(fx, fy)
    elif state == STATE_DEAD:
        draw_dead_flash(death_timer)

    draw_hud()

    if state == STATE_OVER:
        draw_gameover()

# =================================
# Start
# =================================
reset_game()
start()