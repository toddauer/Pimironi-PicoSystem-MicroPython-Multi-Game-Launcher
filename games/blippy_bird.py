#from picosystem import *
import math
import random
import os
import machine

# =========================================================
# CONFIGURATION
# =========================================================

# -- File paths --
GAME_TITLE  = "blippy_bird"
CONFIG_PATH = "/save_files/config.txt"
SAVE_PATH   = "/save_files/" + GAME_TITLE + "_hi.txt"

# -- Screen --
SW       = 120
SH       = 120
CENTER_X = SW // 2
CENTER_Y = SH // 2
GROUND_Y = SH - 10

# -- Bird --
BIRD_X  = 30
GRAVITY = 0.20
FLAP    = -2.1

# -- Pipes --
PIPE_W    = 15
PIPE_CAP  = 3
PIPE_GAP  = 34
PIPE_DIST = 65

# -- Difficulty scaling --
# Speed formula breakpoints (score thresholds → speed and deltas)
SPEED_TIERS = [
    (0,   1.10,  0,      0.035),   # score <  5
    (5,   1.10,  5,      0.035),
    (15,  1.45,  15,     0.025),
    (30,  1.83,  30,     0.020),
    (50,  2.23,  50,     0.015),
]
MIN_PIPE_DIST = 48
MIN_PIPE_GAP  = 22
DIST_SCALE    = 0.9
GAP_SCALE     = 0.55

# -- Milestone messages (score → label) --
MILESTONES = {10: "NICE!", 25: "GREAT!", 50: "AMAZING!", 100: "LEGENDARY!"}

# -- Timing --
SHAKE_DURATION     = 18   # frames
FLASH_DURATION     = 6    # frames
MILESTONE_DURATION = 90   # frames

# -- Music sequence (frequency Hz, duration in ticks) --
MELODY = [
    (523, 12), (587, 12), (659, 12), (523, 12),
    (659, 12), (698, 18), (784, 18),
    (784, 12), (698, 12), (659, 12), (523, 12),
    (587, 24), (523, 24),
    (392, 12), (440, 12), (494, 12), (523, 18),
    (659, 12), (587, 12), (523, 24),
]

# =========================================================
# GAME STATES
# =========================================================
READY = 0
PLAY  = 1
DEAD  = 2

# =========================================================
# HI-SCORE PERSISTENCE
# =========================================================

def load_hi():
    """Read the saved hi-score from disk; return 0 if none exists."""
    try:
        with open(SAVE_PATH, "r") as f:
            return int(f.read().strip())
    except OSError:
        return 0

def save_hi(score):
    """Write a new hi-score to disk only when the player beats the record."""
    try:
        with open(SAVE_PATH, "w") as f:
            f.write(str(score))
    except OSError:
        pass

# =========================================================
# SOUND SETUP
# =========================================================
blip  = Voice(5, 5, 50, 50)

ding  = Voice(10, 10, 100, 500)
ding.effects(reverb=50)
ding.bend(500, 500)

crash = Voice(5, 5, 5, 80)

music_voice = Voice(3, 3, 60, 200)
music_voice.effects(reverb=30)

# =========================================================
# WORLD DECORATIONS  (initialised once, scrolled every frame)
# =========================================================
clouds_far  = [(random.randint(0, SW), random.randint(8,  30), random.randint(10, 22)) for _ in range(4)]
clouds_near = [(random.randint(0, SW), random.randint(35, 55), random.randint(6,  14)) for _ in range(3)]
stars       = [(random.randint(0, SW), random.randint(0,  60)) for _ in range(12)]

# =========================================================
# MUTABLE GAME STATE  (reset() re-initialises all of these)
# =========================================================
bird_y        = float(CENTER_Y)
bird_v        = 0.0
wing          = 0
squash        = 0

pipes         = []

state         = READY
score         = 0
hi_score      = load_hi()
new_high      = False

shake_frames  = 0
flash_frames  = 0
milestone_msg = ""
milestone_ttl = 0

music_idx     = 0
music_timer   = 0

# =========================================================
# HELPERS
# =========================================================

def difficulty(score):
    """Return (speed, pipe_distance, pipe_gap) for the current score."""
    if score < 5:
        speed = 1.10
    elif score < 15:
        speed = 1.10 + (score - 5)  * 0.035
    elif score < 30:
        speed = 1.45 + (score - 15) * 0.025
    elif score < 50:
        speed = 1.83 + (score - 30) * 0.020
    else:
        speed = 2.23 + (score - 50) * 0.015

    dist = max(MIN_PIPE_DIST, PIPE_DIST - score * DIST_SCALE)
    gap  = max(MIN_PIPE_GAP,  PIPE_GAP  - score * GAP_SCALE)
    return speed, int(dist), int(gap)


def new_pipe(x, gap_size):
    """Return a pipe list: [x, gap_top_y, passed_flag, gap_size]."""
    gap_y = random.randint(18, GROUND_Y - gap_size - 5)
    return [x, gap_y, False, gap_size]


def music_tick():
    """Advance the background music sequencer by one frame."""
    global music_idx, music_timer
    if state != PLAY:
        return
    if music_timer <= 0:
        freq, dur = MELODY[music_idx]
        music_voice.play(freq, dur * 10, 35)
        music_idx   = (music_idx + 1) % len(MELODY)
        music_timer = dur
    music_timer -= 1

# =========================================================
# RESET
# =========================================================

def reset():
    """Restore all mutable game state to its starting values."""
    global bird_y, bird_v, pipes, score, state, wing
    global squash, shake_frames, flash_frames
    global milestone_msg, milestone_ttl, new_high
    global music_idx, music_timer

    bird_y        = float(CENTER_Y)
    bird_v        = 0.0
    wing          = 0
    squash        = 0
    score         = 0
    state         = READY
    new_high      = False
    shake_frames  = 0
    flash_frames  = 0
    milestone_msg = ""
    milestone_ttl = 0
    music_idx     = 0
    music_timer   = 0

    pipes.clear()
    _, dist, gap = difficulty(0)
    pipes.append(new_pipe(SW + 20,           gap))
    pipes.append(new_pipe(SW + 20 + dist,    gap))
    pipes.append(new_pipe(SW + 20 + dist * 2, gap))

reset()

# =========================================================
# UPDATE
# =========================================================

def update(tick):
    global bird_y, bird_v, wing, squash, state, score
    global hi_score, new_high
    global shake_frames, flash_frames, milestone_msg, milestone_ttl

    music_tick()

    # --- Button input ---
    if pressed(A):
        if state == READY:
            state  = PLAY
            bird_v = FLAP
            wing   = 8
            squash = -3
        elif state == PLAY:
            bird_v = FLAP
            wing   = 8
            squash = -3
            blip.play(1400, 20)
        elif state == DEAD:
            reset()

    if pressed(Y):
        machine.soft_reset()

    # --- Idle bobbing (non-play states) ---
    if state != PLAY:
        bird_y = CENTER_Y + math.sin(tick * 0.05) * 8
        return

    # --- Physics ---
    bird_v  = min(bird_v + GRAVITY, 4.5)
    bird_y += bird_v

    wing   = max(0, wing - 1)
    if squash != 0:
        squash = squash + 1 if squash < 0 else squash - 1

    # --- Scroll pipes ---
    speed, dist, gap = difficulty(score)
    for p in pipes:
        p[0] -= speed

    # --- Recycle off-screen pipes ---
    for p in pipes:
        if p[0] < -PIPE_W:
            max_x   = max(pp[0] for pp in pipes)
            new_gap = max(MIN_PIPE_GAP, int(PIPE_GAP - score * GAP_SCALE))
            p[0] = max_x + dist
            p[1] = random.randint(18, GROUND_Y - new_gap - 5)
            p[2] = False
            p[3] = new_gap

    # --- Score + hi-score ---
    for p in pipes:
        px, gy, passed, pg = p
        if not passed and BIRD_X > int(px + PIPE_W // 2):
            score += 1
            blip.play(1200, 50)
            p[2] = True

            if score in MILESTONES:
                milestone_msg = MILESTONES[score]
                milestone_ttl = MILESTONE_DURATION

            if score > hi_score:
                hi_score = score
                save_hi(hi_score)          # persist immediately
                if not new_high:
                    ding.play(1500, 200)
                    new_high = True

    # --- Collision detection ---
    hit = bird_y < 0 or bird_y + 8 > GROUND_Y
    if not hit:
        for px, gy, _, pg in pipes:
            if BIRD_X + 7 > px and BIRD_X < px + PIPE_W:
                if bird_y < gy or bird_y + 8 > gy + pg:
                    hit = True
                    break

    if hit:
        state        = DEAD
        shake_frames = SHAKE_DURATION
        flash_frames = FLASH_DURATION
        squash       = 4
        crash.play(200, 300)

    # --- Countdown timers ---
    if shake_frames > 0: shake_frames -= 1
    if flash_frames > 0: flash_frames -= 1
    if milestone_ttl > 0: milestone_ttl -= 1

# =========================================================
# DRAW
# =========================================================

def draw(tick):
    global clouds_far, clouds_near

    # Screen-shake offset
    ox = random.randint(-2, 2) if shake_frames > 0 else 0
    oy = random.randint(-2, 2) if shake_frames > 0 else 0

    # --- Sky ---
    pen(0, 5, 14)
    clear()

    # --- Stars ---
    pen(15, 15, 12)
    for sx, sy in stars:
        pixel(sx + ox, sy + oy)

    # --- Far clouds ---
    pen(2, 7, 15)
    for i, (cx, cy, w) in enumerate(clouds_far):
        frect(int(cx) + ox, cy + oy, w, 5)
        frect(int(cx) + 3 + ox, cy - 2 + oy, w - 6, 4)
        clouds_far[i] = ((cx - 0.15) % SW, cy, w)

    # --- Near clouds ---
    pen(3, 8, 15)
    for i, (cx, cy, w) in enumerate(clouds_near):
        frect(int(cx) + ox, cy + oy, w, 4)
        clouds_near[i] = ((cx - 0.30) % SW, cy, w)

    # --- Pipes ---
    for px, gy, _, pg in pipes:
        px = int(px) + ox
        pen(0, 11, 2)
        frect(px, oy, PIPE_W, gy)                            # top shaft
        pen(0, 13, 3)
        frect(px - 1, gy - PIPE_CAP + oy, PIPE_W + 2, PIPE_CAP)  # top cap
        pen(0, 11, 2)
        frect(px, gy + pg + oy, PIPE_W, GROUND_Y - gy - pg) # bottom shaft
        pen(0, 13, 3)
        frect(px - 1, gy + pg + oy, PIPE_W + 2, PIPE_CAP)   # bottom cap

    # --- Ground ---
    pen(10, 7, 1)
    frect(ox, GROUND_Y + oy, SW, SH - GROUND_Y)
    pen(7, 5, 0)
    frect(ox, GROUND_Y + oy, SW, 2)

    # --- Bird ---
    bw     = 8 + squash
    bh     = 8 - squash
    bx_off = -squash // 2
    bx     = BIRD_X + ox + bx_off
    by     = max(0, min(int(bird_y) + oy, GROUND_Y - bh))

    pen(15, 14, 0)
    frect(bx, by, bw, bh)                              # body
    pen(15, 11, 0)
    wy = -2 if wing > 4 else 2
    frect(bx + 1, by + wy, bw - 2, 3)                 # wing
    pen(0, 0, 0)
    frect(bx + bw - 3, by + 2, 2, 2)                  # eye (dark)
    pen(15, 15, 15)
    pixel(bx + bw - 3, by + 2)                        # eye shine
    pen(15, 6, 0)
    frect(bx + bw - 1, by + bh - 3, 2, 2)             # beak

    # --- HUD: score + hi-score ---
    pen(0, 0, 0)
    text("{}".format(score), CENTER_X - 3, 3)
    pen(15, 15, 15)
    text("{}".format(score), CENTER_X - 4, 2)
    pen(13, 13, 13)
    hi_label = "HI {}".format(hi_score)
    w, _ = measure(hi_label)
    text(hi_label, SW - w - 2, 2)

    # --- New high banner ---
    if new_high and state == PLAY:
        pen(15, 13, 0)
        text("NEW HIGH!", CENTER_X - 22, 14)

    # --- Milestone popup ---
    if milestone_ttl > 0:
        pen(15, 15, 0)
        w, _ = measure(milestone_msg)
        text(milestone_msg, CENTER_X - w // 2, CENTER_Y - 30)

    # --- Ready screen ---
    if state == READY:
        pen(0, 0, 0, 2)
        frect(CENTER_X - 42, CENTER_Y + 8, 90, 16)
        pen(15, 15, 15)
        text("PRESS A TO FLY", CENTER_X - 36, CENTER_Y + 12)

    # --- Game-over screen ---
    if state == DEAD:
        pen(0, 0, 0)
        frect(CENTER_X - 44, CENTER_Y - 22, 88, 44)
        pen(15, 4, 4)
        text("GAME OVER", CENTER_X - 33, CENTER_Y - 16)
        pen(15, 15, 15)
        text("Score: {}".format(score), CENTER_X - 22, CENTER_Y - 5)
        text("Best:  {}".format(hi_score), CENTER_X - 22, CENTER_Y + 5)

# =========================================================
# ENTRY POINT
# =========================================================
start()