from picosystem import *
import random
import machine
import math

# =========================================================
# CONFIG / SAVE
# =========================================================
GAME_TITLE = "sub_mariner"
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
# ==========================
# Screen
# ==========================
SW, SH     = 120, 120
WATER_TOP  = 10
WATER_BOT  = 115

# ==========================
# Game states
# ==========================
STATE_START = 0
STATE_PLAY  = 1
STATE_DEAD  = 2
state = STATE_START

# ==========================
# Scores
# ==========================
score = 0
dist  = 0
hi_score= load_hi()

# ==========================
# Submarine
# ==========================
SUB_W, SUB_H = 22, 9
SUB_X_MIN    = 8
SUB_X_MAX    = SW // 2 - SUB_W   # can't push past centre
SUB_GRAV     = 0.07
SUB_THRUST   = 0.13
SUB_TERM     = 1.8
SUB_HSPEED   = 1.2   # horizontal speed

sub_x  = float(SUB_X_MIN + 10)
sub_y  = float(SH // 2)
sub_dx = 0.0
sub_dy = 0.0

lives      = 3
torpedoes  = 3
inv_frames = 0
INV_TIME   = 120
blink      = False
torp_cd    = 0

# ==========================
# Torpedoes
# ==========================
torps      = []
TORP_SPEED = 4

# ==========================
# Mines  — max 3 on screen
# ==========================
mines  = []
MINE_R = 5
MAX_MINES = 3

def mine_ok(y):
    """Ensure new mine isn't too close vertically to existing ones."""
    for m in mines:
        if abs(m[1] - y) < 20:
            return False
    return True

def spawn_mine():
    if len(mines) >= MAX_MINES:
        return
    y = random.randint(WATER_TOP + 14, WATER_BOT - 14)
    if mine_ok(y):
        mines.append([float(SW + 6), float(y), random.uniform(0, 6.28)])

# ==========================
# Enemies — max 2 on screen
# ==========================
enemies   = []
MAX_ENEMIES = 2
# [x, y, type, anim, gap_timer]
# type 0=fish  1=squid

def spawn_enemy():
    if len(enemies) >= MAX_ENEMIES:
        return
    # Don't spawn too close to existing enemies vertically
    y = random.randint(WATER_TOP + 10, WATER_BOT - 14)
    for e in enemies:
        if abs(e[1] - y) < 24:
            return
    etype = random.randint(0, 1)
    enemies.append([float(SW + 6), float(y), etype, 0, random.randint(0, 30)])

# ==========================
# Collectibles — strict caps
# ==========================
coins   = []   # max 1
bubbles = []   # max 2
ammo_p  = []   # max 1

def try_spawn(lst, cap, chance):
    if len(lst) >= cap:
        return
    if random.randint(0, chance) != 0:
        return
    x = float(SW + 4)
    y = float(random.randint(WATER_TOP + 10, WATER_BOT - 10))
    # Don't spawn inside a mine
    for m in mines:
        if abs(x - m[0]) < MINE_R + 8 and abs(y - m[1]) < MINE_R + 8:
            return
    lst.append([x, y])

# ==========================
# Explosions & particles
# ==========================
explosions = []   # [x, y, timer]
particles  = []   # [x, y, dx, dy, life, r, g, b]

def burst(x, y, r, g, b, n=4):
    for _ in range(n):
        dx = random.uniform(-1.2, 1.2)
        dy = random.uniform(-1.2, 1.2)
        particles.append([x, y, dx, dy, 7, r, g, b])

# ==========================
# Screen effects
# ==========================
shake_frames = 0
flash_frames = 0

# ==========================
# Hazard budget timer
# Mines and enemies share one spawn clock so they can't stack
# ==========================
hazard_timer    = 0
HAZARD_INTERVAL = 80   # ticks between hazard spawns

# ==========================
# Difficulty
# ==========================
def world_speed():
    return min(2.8, 1.0 + score * 0.005)

# ==========================
# Parallax (far only — 8 dim pixels)
# ==========================
par_far = [[float(random.randint(0, SW)),
            float(random.randint(WATER_TOP + 2, WATER_BOT - 2))]
           for _ in range(8)]

# ==========================
# Music
# ==========================
MELODY = [
    (220,16),(196,8),(220,8),(247,16),
    (220,16),(185,24),(196,16),(185,8),
    (165,24),(185,8),(196,16),(220,16),
    (196,16),(175,24),
]
music_voice = Voice(3, 3, 70, 300)
music_voice.effects(reverb=60)
music_idx   = 0
music_timer = 0

def music_tick():
    global music_idx, music_timer
    if state != STATE_PLAY:
        return
    if music_timer <= 0:
        freq, dur = MELODY[music_idx]
        tempo     = max(6, dur - score // 60)
        music_voice.play(freq, tempo * 14, 28)
        music_idx   = (music_idx + 1) % len(MELODY)
        music_timer = tempo
    music_timer -= 1

# ==========================
# Sound effects
# ==========================
torp_snd   = Voice(5,  3,  40, 150)
torp_snd.bend(200, 300)
coin_snd   = Voice(5,  5,  80, 100)
coin_snd.bend(200, 400)
bubble_snd = Voice(3,  3,  60, 80)
ammo_snd   = Voice(5,  5,  60, 200)
ammo_snd.bend(300, 600)
hit_snd    = Voice(10, 10, 80, 350)
hit_snd.effects(reverb=40)
kill_snd   = Voice(5,  5,  60, 200)
kill_snd.bend(400, 200)

# ==========================
# Reset
# ==========================
def reset_game():
    global sub_x, sub_y, sub_dx, sub_dy, torpedoes, torps, torp_cd
    global mines, coins, bubbles, ammo_p, enemies
    global explosions, particles, score, dist, lives
    global hazard_timer, shake_frames, flash_frames, inv_frames
    global music_idx, music_timer, blink

    sub_x        = float(SUB_X_MIN + 10)
    sub_y        = float(SH // 2)
    sub_dx       = 0.0
    sub_dy       = 0.0
    torpedoes    = 3
    torps        = []
    torp_cd      = 0
    mines        = []
    coins        = []
    bubbles      = []
    ammo_p       = []
    enemies      = []
    explosions   = []
    particles    = []
    score        = 0
    dist         = 0
    lives        = 3
    hazard_timer = 0
    shake_frames = 0
    flash_frames = 0
    inv_frames   = 0
    blink        = False
    music_idx    = 0
    music_timer  = 0

reset_game()

# ==========================
# Hit sub
# ==========================
def hit_sub():
    global lives, state, inv_frames, shake_frames, flash_frames, hi_score
    if inv_frames > 0:
        return
    lives       -= 1
    inv_frames   = INV_TIME
    shake_frames = 14
    flash_frames = 6
    hit_snd.play(180, 300, 100)
    if lives <= 0:
        hi_score = max(hi_score, score)
        save_hi()
        state = STATE_DEAD

# ==========================
# Update
# ==========================
prev_a = False

def update(tick):
    global sub_x, sub_y, sub_dx, sub_dy, torps, torp_cd
    global mines, coins, bubbles, ammo_p, enemies
    global explosions, particles, score, dist, hi_score
    global hazard_timer, shake_frames, flash_frames, inv_frames, blink
    global state, lives, torpedoes, prev_a

    music_tick()

    if shake_frames > 0: shake_frames -= 1
    if flash_frames > 0: flash_frames -= 1
    if torp_cd      > 0: torp_cd      -= 1
    if inv_frames   > 0:
        inv_frames -= 1
        blink = (inv_frames // 6) % 2 == 0
    else:
        blink = False

    if pressed(Y):
        machine.soft_reset()

    nb_a = button(A)

    if state == STATE_START:
        if nb_a and not prev_a:
            reset_game()
            state = STATE_PLAY
        prev_a = nb_a
        return

    if state == STATE_DEAD:
        if nb_a and not prev_a:
            state = STATE_START
        prev_a = nb_a
        return

    # -------- MOVEMENT (4-directional) --------
    if button(UP):
        sub_dy -= SUB_THRUST
    if button(DOWN):
        sub_dy += SUB_THRUST
    if button(LEFT):
        sub_dx -= SUB_HSPEED
    if button(RIGHT):
        sub_dx += SUB_HSPEED

    # Gravity + drag
    sub_dy += SUB_GRAV
    sub_dy  = max(-SUB_TERM, min(SUB_TERM, sub_dy))
    sub_dx *= 0.75   # stronger horizontal drag — snappy not floaty
    sub_dy *= 0.90

    sub_x += sub_dx
    sub_y += sub_dy

    sub_x = max(float(SUB_X_MIN), min(float(SUB_X_MAX), sub_x))
    sub_y = max(float(WATER_TOP + 1), min(float(WATER_BOT - SUB_H - 1), sub_y))

    # -------- TORPEDO FIRE --------
    if nb_a and not prev_a and torpedoes > 0 and torp_cd == 0:
        torps.append([sub_x + SUB_W + 1, sub_y + SUB_H // 2])
        torpedoes -= 1
        torp_cd    = 18
        torp_snd.play(800, 50, 60)

    prev_a = nb_a

    spd = world_speed()

    # -------- PARALLAX --------
    for p in par_far:
        p[0] -= 0.3
        if p[0] < 0:
            p[0] = float(SW)
            p[1] = float(random.randint(WATER_TOP + 2, WATER_BOT - 2))

    # -------- HAZARD BUDGET SPAWNER --------
    hazard_timer += 1
    interval = max(35, HAZARD_INTERVAL - score // 5)
    if hazard_timer >= interval:
        hazard_timer = 0
        # Alternate: bias toward mines early, enemies more common later
        mine_weight  = max(1, 6 - score // 20)
        enemy_weight = min(6, 1 + score // 20)
        total        = mine_weight + enemy_weight
        if random.randint(0, total) < mine_weight:
            spawn_mine()
        else:
            spawn_enemy()

    # Collectibles on their own slower timers
    try_spawn(bubbles, 2, 35)
    try_spawn(coins,   1, 55)
    try_spawn(ammo_p,  1, 90)

    # -------- MOVE MINES --------
    next_mines = []
    for m in mines:
        m[0] -= spd * 0.65
        m[2] += 0.035
        m[1] += math.sin(m[2]) * 0.25
        m[1]  = max(float(WATER_TOP + MINE_R + 2),
                    min(float(WATER_BOT - MINE_R - 2), m[1]))
        if m[0] + MINE_R > 0:
            next_mines.append(m)
    mines[:] = next_mines

    # -------- MOVE ENEMIES --------
    next_enemies = []
    for e in enemies:
        e[0] -= spd * 0.55
        e[3]  = (e[3] + 1) % 20
        if e[0] + 14 > 0:
            next_enemies.append(e)
    enemies[:] = next_enemies

    # -------- MOVE COLLECTIBLES --------
    for lst in (coins, bubbles, ammo_p):
        i = len(lst) - 1
        while i >= 0:
            lst[i][0] -= spd * 0.7
            if lst[i][0] < -8:
                lst.pop(i)
            i -= 1

    # -------- MOVE TORPEDOES --------
    next_torps = []
    for t in torps:
        t[0] += TORP_SPEED
        if t[0] < SW + 4:
            next_torps.append(t)
    torps[:] = next_torps

    # -------- MOVE PARTICLES --------
    i = len(particles) - 1
    while i >= 0:
        p = particles[i]
        p[0] += p[2]; p[1] += p[3]; p[4] -= 1
        if p[4] <= 0:
            particles.pop(i)
        i -= 1

    # -------- COLLISIONS: MINES --------
    sx, sy = sub_x, sub_y
    cx2 = sx + SUB_W // 2
    cy2 = sy + SUB_H // 2
    for m in mines[:]:
        ddx = cx2 - m[0]
        ddy = cy2 - m[1]
        if ddx*ddx + ddy*ddy < (MINE_R + 6) * (MINE_R + 6):
            explosions.append([m[0], m[1], 16])
            mines.remove(m)
            hit_sub()
            break

    # -------- COLLISIONS: ENEMIES --------
    for e in enemies[:]:
        if sx + SUB_W > e[0] + 2 and sx < e[0] + 12 and \
           sy + SUB_H > e[1] + 1 and sy < e[1] + 9:
            enemies.remove(e)
            explosions.append([e[0] + 4, e[1] + 4, 14])
            hit_sub()
            break

    # -------- COLLISIONS: COLLECTIBLES --------
    for b in bubbles[:]:
        if sx < b[0]+5 and sx+SUB_W > b[0] and sy < b[1]+5 and sy+SUB_H > b[1]:
            bubbles.remove(b)
            score += 5
            burst(b[0], b[1], 5, 8, 15, 3)
            bubble_snd.play(660, 20, 45)

    for co in coins[:]:
        if sx < co[0]+5 and sx+SUB_W > co[0] and sy < co[1]+5 and sy+SUB_H > co[1]:
            coins.remove(co)
            score += 15
            burst(co[0], co[1], 15, 12, 0, 4)
            coin_snd.play(880, 25, 55)

    for a in ammo_p[:]:
        if sx < a[0]+6 and sx+SUB_W > a[0] and sy < a[1]+5 and sy+SUB_H > a[1]:
            ammo_p.remove(a)
            torpedoes = min(torpedoes + 1, 9)
            burst(a[0], a[1], 12, 0, 15, 3)
            ammo_snd.play(440, 60, 55)

    # -------- TORPEDO HITS --------
    for t in torps[:]:
        hit = False
        for e in enemies[:]:
            if t[0] < e[0]+12 and t[0]+3 > e[0] and t[1] < e[1]+9 and t[1]+3 > e[1]:
                torps.remove(t)
                enemies.remove(e)
                score += 20
                explosions.append([e[0]+4, e[1]+2, 14])
                kill_snd.play(500, 80, 65)
                hit = True
                break
        if hit:
            continue
        for m in mines[:]:
            ddx = t[0] - m[0]; ddy = t[1] - m[1]
            if ddx*ddx + ddy*ddy < (MINE_R + 3) * (MINE_R + 3):
                torps.remove(t)
                mines.remove(m)
                score += 10
                explosions.append([m[0], m[1], 18])
                kill_snd.play(350, 100, 70)
                break

    # -------- EXPLOSIONS --------
    explosions[:] = [[x, y, t-1] for x, y, t in explosions if t > 0]

    # -------- SCORE --------
    dist += 1
    if dist % 10 == 0:
        score += 1
    hi_score = max(hi_score, score)

# ==========================
# Water gradient bands (4 draws instead of 27)
# ==========================
WATER_BANDS = [
    (WATER_TOP,                              25, (0, 0, 10)),
    (WATER_TOP + 25,                         25, (0, 0,  8)),
    (WATER_TOP + 50,                         25, (0, 0,  6)),
    (WATER_TOP + 75,  WATER_BOT - WATER_TOP - 75, (0, 0,  5)),
]

# ==========================
# Draw
# ==========================
def draw(tick):
    ox = random.randint(-2, 2) if shake_frames > 0 else 0
    oy = random.randint(-2, 2) if shake_frames > 0 else 0

    if flash_frames > 0:
        pen(15, 0, 0)
        clear()
    else:
        pen(0, 0, 5)
        clear()

    # -------- WATER BANDS --------
    for band_y, band_h, (br, bg, bb) in WATER_BANDS:
        pen(br, bg, bb)
        frect(0, band_y + oy, SW, band_h)

    # -------- PARALLAX --------
    pen(0, 1, 4)
    for p in par_far:
        pixel(int(p[0]) + ox, int(p[1]) + oy)

    # -------- MINES --------
    # Naval mine: round dark body, 8 protruding horns, bright centre
    for m in mines:
        mx, my = int(m[0]) + ox, int(m[1]) + oy
        # Body — approximated circle with frects
        pen(5, 5, 5)
        frect(mx-3, my-5, 7, 11)   # tall centre
        frect(mx-5, my-3, 11, 7)   # wide centre
        frect(mx-4, my-4, 9,  9)   # fill corners
        # Dark shading on lower half
        pen(3, 3, 3)
        frect(mx-3, my+1, 7, 3)
        frect(mx-4, my+2, 9, 2)
        # Horns — 8 directions, each a bright single pixel spike
        pen(12, 12, 4)
        pixel(mx,    my-6)          # N
        pixel(mx,    my+6)          # S
        pixel(mx-6,  my)            # W
        pixel(mx+6,  my)            # E
        pixel(mx-4,  my-4)          # NW
        pixel(mx+4,  my-4)          # NE
        pixel(mx-4,  my+4)          # SW
        pixel(mx+4,  my+4)          # SE
        # Bright specular highlight top-left
        pen(14, 14, 10)
        frect(mx-2, my-2, 3, 3)
        pen(15, 15, 15)
        pixel(mx-1, my-1)

    # -------- ENEMIES --------
    for e in enemies:
        ex2, ey2 = int(e[0]) + ox, int(e[1]) + oy
        fr = 1 if e[3] > 10 else 0

        if e[2] == 0:   # FISH — faces left (swimming toward player)
            # Tail (right side) — forked, animates open/close
            pen(10, 4, 0)
            if fr == 0:
                frect(ex2+10, ey2,   3, 3)   # top lobe
                frect(ex2+10, ey2+5, 3, 3)   # bottom lobe
            else:
                frect(ex2+10, ey2+1, 3, 2)
                frect(ex2+10, ey2+5, 3, 2)
            # Body — tapered: narrower at snout end (left)
            pen(13, 6, 0)
            frect(ex2+1, ey2+1, 9, 6)        # main body
            frect(ex2+8, ey2+2, 3, 4)        # thicker mid-rear
            # Belly highlight
            pen(15, 10, 4)
            frect(ex2+2, ey2+3, 6, 2)
            # Dorsal fin — small triangle above body midpoint
            pen(10, 4, 0)
            frect(ex2+5, ey2-1, 3, 2)
            pixel(ex2+6, ey2-2)
            # Snout — pointed left tip
            pen(13, 6, 0)
            pixel(ex2, ey2+3)
            # Eye — dark with white glint
            pen(2, 2, 2)
            frect(ex2+2, ey2+2, 2, 2)
            pen(15, 15, 15)
            pixel(ex2+2, ey2+2)

        else:           # SQUID — mantle pointing right, tentacles left
            # Mantle (pointed rear, right side)
            pen(8, 0, 10)
            pixel(ex2+11, ey2+3)             # mantle tip
            frect(ex2+8,  ey2+1, 4, 5)       # mantle body
            # Head — wide oval
            pen(10, 0, 13)
            frect(ex2+2, ey2,   8, 7)
            frect(ex2+1, ey2+1, 10, 5)
            # Highlight
            pen(13, 4, 15)
            frect(ex2+3, ey2+1, 5, 2)
            # Eyes — two white dots
            pen(15, 15, 15)
            frect(ex2+3, ey2+3, 2, 2)
            frect(ex2+7, ey2+3, 2, 2)
            pen(0, 0, 0)
            pixel(ex2+4, ey2+4)
            pixel(ex2+8, ey2+4)
            # Tentacles (left side) — 4 two-pixel-wide strips, alternate long/short
            pen(8, 0, 10)
            if fr == 0:
                frect(ex2-3, ey2+1, 4, 2)    # top pair, long
                frect(ex2-1, ey2+3, 3, 2)    # second pair, short
                frect(ex2-3, ey2+5, 4, 2)    # third pair, long
                frect(ex2-1, ey2+7, 3, 2)    # fourth pair, short (dangle)
            else:
                frect(ex2-2, ey2+1, 3, 2)
                frect(ex2-4, ey2+3, 4, 2)
                frect(ex2-2, ey2+5, 3, 2)
                frect(ex2-4, ey2+7, 4, 2)

    # -------- COLLECTIBLES --------
    # Bubbles — circular outline with inner shimmer
    for b in bubbles:
        bx2, by2 = int(b[0])+ox, int(b[1])+oy
        pen(3, 6, 13)
        frect(bx2+1, by2,   4, 6)   # centre column
        frect(bx2,   by2+1, 6, 4)   # centre row
        pen(6, 10, 15)
        frect(bx2+1, by2+1, 4, 4)   # inner fill
        pen(12, 15, 15)
        pixel(bx2+1, by2+1)         # top-left glint
        pixel(bx2+2, by2+1)
        pen(2, 4, 10)
        pixel(bx2+3, by2+4)         # bottom-right shadow

    # Coins — ring shape: gold rim, dark hole suggestion, bright glint
    for co in coins:
        cx2, cy2 = int(co[0])+ox, int(co[1])+oy
        pen(14, 10, 0)
        frect(cx2+1, cy2,   4, 6)   # outer ring vertical
        frect(cx2,   cy2+1, 6, 4)   # outer ring horizontal
        pen(10, 7, 0)
        frect(cx2+2, cy2+2, 2, 2)   # dark centre (hole)
        pen(15, 15, 4)
        pixel(cx2+1, cy2+1)         # bright glint top-left
        pixel(cx2+2, cy2+1)
        pen(10, 8, 0)
        pixel(cx2+4, cy2+4)         # shadow bottom-right

    # Ammo — torpedo-shaped pickup: nose, body with band, tail fins
    for a in ammo_p:
        ax2, ay2 = int(a[0])+ox, int(a[1])+oy
        # Tail fins
        pen(5, 5, 8)
        frect(ax2,   ay2,   2, 2)   # top fin
        frect(ax2,   ay2+4, 2, 2)   # bottom fin
        # Body
        pen(9, 9, 11)
        frect(ax2+1, ay2+1, 6, 4)
        # Yellow band stripe
        pen(15, 13, 0)
        frect(ax2+3, ay2+1, 2, 4)
        # Nose cone (right)
        pen(12, 4, 0)
        frect(ax2+7, ay2+2, 2, 2)
        pixel(ax2+9, ay2+3)
        # Highlight
        pen(14, 14, 15)
        pixel(ax2+2, ay2+1)

    # -------- TORPEDOES --------
    for t in torps:
        tx, ty = int(t[0])+ox, int(t[1])+oy
        # Fading exhaust trail
        pen(8, 4, 0)
        frect(tx-5, ty, 2, 2)
        pen(12, 7, 0)
        frect(tx-3, ty, 3, 2)
        # Body
        pen(10, 10, 12)
        frect(tx,   ty, 5, 2)
        # Warhead tip — bright yellow point
        pen(15, 15, 0)
        frect(tx+4, ty, 2, 2)
        pixel(tx+6, ty)

    # -------- EXPLOSIONS --------
    for ex_e in explosions:
        ex2, ey2, t = int(ex_e[0])+ox, int(ex_e[1])+oy, ex_e[2]
        r = (16 - t) // 2 + 1
        pen(15, min(15, 4+t), 0)
        frect(ex2-r, ey2-1, r*2, 3)
        frect(ex2-1, ey2-r, 3,   r*2)
        pen(15, 15, 0)
        frect(ex2-1, ey2-1, 3, 3)

    # -------- PARTICLES --------
    for p in particles:
        pen(p[5], p[6], p[7])
        pixel(int(p[0])+ox, int(p[1])+oy)

    # -------- SUBMARINE --------
    if not blink:
        sx2, sy2 = int(sub_x)+ox, int(sub_y)+oy
        pen(0, 10, 13)
        frect(sx2,        sy2+3, SUB_W,     SUB_H-3)
        pen(0, 12, 14)
        frect(sx2+5,      sy2,   7,          5)
        pen(0, 14, 15)
        frect(sx2+1,      sy2+4, SUB_W-5,   2)
        pen(0, 8, 11)
        frect(sx2+SUB_W-2,sy2+4, 3,          SUB_H-7)
        pen(15, 15, 8)
        frect(sx2+3,      sy2+4, 3,          3)
        pen(0, 12, 15)
        pixel(sx2+4,      sy2+5)
        pen(0, 6, 9)
        frect(sx2-2,      sy2+3, 2,          2)
        frect(sx2-2,      sy2+7, 2,          2)

    # -------- SEABED --------
    pen(0, 4, 1)
    frect(ox, WATER_BOT+oy, SW, SH-WATER_BOT)

    # -------- HUD --------
    pen(0, 0, 4)
    frect(0, 0, SW, WATER_TOP)
    pen(15, 15, 15)
    text(f"{score}", 2, 2)
    pen(15, 13, 0)
    text(f"HI:{hi_score}", 40, 2)
    # Torpedo pips — mini torpedo silhouettes
    for i in range(torpedoes):
        tx2 = 84 + i * 9
        ty2 = 2
        pen(6, 6, 9)
        frect(tx2+1, ty2+1, 5, 3)   # body
        pen(10, 10, 13)
        frect(tx2+2, ty2+1, 4, 3)   # highlight
        pen(15, 13, 0)
        frect(tx2+5, ty2+1, 2, 3)   # warhead
        pixel(tx2+7, ty2+2)         # nose tip
        pen(4, 4, 6)
        frect(tx2,   ty2+1, 2, 1)   # top fin
        frect(tx2,   ty2+3, 2, 1)   # bottom fin

    # Lives — tiny top-down boat silhouettes
    for i in range(lives):
        lx = 2 + i * 13
        ly = SH - 9
        # Hull — long thin shape
        pen(4, 6, 8)
        frect(lx+1, ly+2, 9, 3)
        # Cabin/bridge — small raised block amidships
        pen(10, 12, 14)
        frect(lx+3, ly+1, 4, 3)
        # Bow point (right)
        pen(6, 8, 10)
        pixel(lx+10, ly+3)
        # Waterline stripe
        pen(0, 10, 12)
        frect(lx+1, ly+4, 9, 1)
        # Wake highlight on cabin
        pen(13, 15, 15)
        pixel(lx+4, ly+1)

    # -------- START SCREEN --------
    if state == STATE_START:
        pen(0, 0, 0)
        frect(10, SH//2-18, 100, 36)
        pen(15, 15, 15)
        text("A to dive",   34, SH//2-4)
        pen(8, 8, 8)
        text("Arrows:move", 22, SH//2+6)

    # -------- DEAD SCREEN --------
    if state == STATE_DEAD:
        pen(0, 0, 0)
        frect(10, SH//2-18, 100, 36)
        pen(15, 0, 0)
        text("SUNK!",        42, SH//2-12)
        pen(15, 15, 15)
        text(f"Score:{score}", 22, SH//2-2)
        pen(10, 10, 10)
        text("A: surface",   30, SH//2+8)

# ==========================
# Start
# ==========================
start()