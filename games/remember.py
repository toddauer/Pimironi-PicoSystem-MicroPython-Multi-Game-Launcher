from picosystem import *
import random, machine

# =========================================================
# CONFIG / SAVE
# =========================================================
GAME_TITLE = "simon"
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

# Four directions mapped to quadrants
# UP=0 (top, green), RIGHT=1 (right, blue), DOWN=2 (bottom, yellow), LEFT=3 (left, red)
DIR_UP    = 0
DIR_RIGHT = 1
DIR_DOWN  = 2
DIR_LEFT  = 3

# Timing (in ticks, ~60fps)
FLASH_ON    = 28   # how long a quadrant lights up during playback
FLASH_OFF   = 10   # gap between flashes during playback
INPUT_GRACE = 180  # ticks player has to press before timeout

# Tone frequencies for each direction (classic Simon pitches)
TONES = [
    415,   # UP    — G#4 (green)
    310,   # RIGHT — Eb4 (blue)
    252,   # DOWN  — B3  (yellow)
    209,   # LEFT  — Ab3 (red)
]
TONE_DUR = 24   # ticks to hold tone during playback

# Colours — dim and bright versions for each quadrant
# (r_dim,g_dim,b_dim, r_bright,g_bright,b_bright)
QUAD_COLS = [
    (2,7,2,   5,15,4),    # UP    green
    (2,2,9,   4,6,15),    # RIGHT blue
    (9,9,2,   15,15,3),   # DOWN  yellow
    (9,2,2,   15,3,3),    # LEFT  red
]

# Direction labels shown in centre
DIR_LABELS = ["UP", "RT", "DN", "LT"]

# =================================
# Voices
# =================================
simon_voice = Voice(5, 10, 90, 20)
blip        = Voice(5, 5, 50, 10)
fail_voice  = Voice(2, 40, 80, 60)

# =================================
# State machine
# =================================
STATE_TITLE    = 0
STATE_PLAYBACK = 1   # Simon plays the sequence
STATE_INPUT    = 2   # player repeats it
STATE_CORRECT  = 3   # brief flash on correct full sequence
STATE_FAIL     = 4   # wrong press
STATE_OVER     = 5   # game over screen
STATE_WIN      = 6   # completed a round, adding next step

state      = STATE_TITLE
sequence   = []
player_pos = 0       # how far through sequence player has typed
round_num  = 0       # current round (= len(sequence))

# Playback state
pb_index   = 0       # which item in sequence we're flashing
pb_timer   = 0       # countdown for current flash phase
pb_phase   = 0       # 0=on, 1=off

# Active flash (for both playback and player input feedback)
active_dir   = -1    # which quadrant is lit (-1 = none)
active_timer = 0     # how long it stays lit

# Timeout
input_timer  = 0

# Score / hi_score
score = 0
hi_score  = 0

# Fail state
fail_timer = 0

# Correct flash
correct_timer = 0

# =================================
# Helpers
# =================================
def reset_game():
    global sequence, player_pos, round_num, pb_index, pb_timer, pb_phase
    global active_dir, active_timer, input_timer, score, fail_timer, correct_timer
    sequence    = []
    player_pos  = 0
    round_num   = 0
    pb_index    = 0
    pb_timer    = 0
    pb_phase    = 0
    active_dir  = -1
    active_timer= 0
    input_timer = 0
    score       = 0
    fail_timer  = 0
    correct_timer = 0

def add_step():
    sequence.append(random.randint(0, 3))

def start_playback():
    global state, pb_index, pb_timer, pb_phase, player_pos
    state      = STATE_PLAYBACK
    pb_index   = 0
    pb_timer   = FLASH_ON
    pb_phase   = 0
    player_pos = 0
    # Light first item immediately
    set_active(sequence[0])
    simon_voice.play(TONES[sequence[0]], TONE_DUR * 16, 70)

def set_active(d):
    global active_dir, active_timer
    active_dir   = d
    active_timer = FLASH_ON

def clear_active():
    global active_dir, active_timer
    active_dir   = -1
    active_timer = 0

def start_input():
    global state, player_pos, input_timer
    state       = STATE_INPUT
    player_pos  = 0
    input_timer = INPUT_GRACE
    clear_active()

# =================================
# Drawing
# =================================
def draw_quadrant(qx, qy, qw, qh, col_idx, lit):
    cd = QUAD_COLS[col_idx]
    if lit:
        r, g, b = cd[3], cd[4], cd[5]
    else:
        r, g, b = cd[0], cd[1], cd[2]
    pen(r, g, b)
    frect(qx, qy, qw, qh)

    # Inner highlight edge when lit
    if lit:
        pen(min(15,r+3), min(15,g+3), min(15,b+3))
        frect(qx, qy, qw, 1)
        frect(qx, qy, 1, qh)
    else:
        pen(max(0,r-1), max(0,g-1), max(0,b-1))
        frect(qx, qy, qw, 1)

def draw_board():
    gap = 4
    hw  = (SCREEN_W - gap) // 2   # half width
    hh  = (SCREEN_H - gap) // 2   # half height (leaving room for HUD)

    # Adjust for HUD strip at bottom
    board_h = SCREEN_H - 14
    hh = (board_h - gap) // 2

    # UP (top-left + top-right merged as top half — but split left/right for L/R)
    # Layout: 4 quadrants in a 2x2 grid
    # TL = LEFT (red), TR = UP (green), BL = DOWN (yellow), BR = RIGHT (blue)
    # Wait — map to directions intuitively:
    # TOP centre-ish = UP, RIGHT = RIGHT, BOTTOM = DOWN, LEFT = LEFT
    # We'll do it as a cross: top strip, right strip, bottom strip, left strip

    cx = SCREEN_W // 2
    cy = board_h  // 2

    arm = 52   # arm half-length
    aw  = 44   # arm width

    # UP quadrant (top)
    lit = (active_dir == DIR_UP)
    draw_quadrant(cx - aw//2, 0, aw, cy - gap//2, DIR_UP, lit)

    # DOWN quadrant (bottom of board)
    lit = (active_dir == DIR_DOWN)
    draw_quadrant(cx - aw//2, cy + gap//2, aw, board_h - cy - gap//2, DIR_DOWN, lit)

    # LEFT quadrant
    lit = (active_dir == DIR_LEFT)
    draw_quadrant(0, cy - aw//2, cx - gap//2, aw, DIR_LEFT, lit)

    # RIGHT quadrant
    lit = (active_dir == DIR_RIGHT)
    draw_quadrant(cx + gap//2, cy - aw//2, SCREEN_W - cx - gap//2, aw, DIR_RIGHT, lit)

    # Centre circle (dark hub)
    pen(2, 2, 3)
    frect(cx - 12, cy - 12, 24, 24)
    pen(3, 3, 5)
    frect(cx - 11, cy - 11, 22, 1)
    frect(cx - 11, cy - 11, 1, 22)

    # Round number in hub
    pen(10, 10, 12)
    rstr = str(round_num)
    rw, _ = measure(rstr)
    text(rstr, cx - rw//2, cy - 3)

def draw_hud():
    hy = SCREEN_H - 13
    pen(1, 1, 2); frect(0, hy, SCREEN_W, 13)
    pen(4, 3, 8); frect(0, hy, SCREEN_W, 1)

    pen(13, 13, 15)
    sw, _ = measure(str(score))
    text(str(score), int(60 - sw/2), hy + 3)

    pen(8, 7, 12)
    text("B"+str(hi_score), 88, hy + 3)

    # Input timer bar
    if state == STATE_INPUT:
        bar_w = int((input_timer / INPUT_GRACE) * 60)
        pen(3, 2, 8); frect(0, hy - 3, 60, 3)
        pen(8, 5, 15); frect(0, hy - 3, bar_w, 3)

def draw_state_label():
    # Small status text at bottom of board area
    cy = (SCREEN_H - 14) // 2
    if state == STATE_PLAYBACK:
        pen(8, 8, 10)
        t = "WATCH"
        tw, _ = measure(t)
        text(t, int(60 - tw/2), cy - 3)
    elif state == STATE_INPUT:
        pen(10, 14, 10)
        t = "REPEAT"
        tw, _ = measure(t)
        text(t, int(60 - tw/2), cy - 3)

def draw_title():
    pen(2, 2, 4); frect(0, 0, SCREEN_W, SCREEN_H)

    # Draw dim quadrant previews
    draw_board()

    pen(1, 1, 3); frect(20, 36, 80, 48)
    pen(6, 4, 14); rect(20, 36, 80, 48)

    pen(15, 14, 15)
    t = "SIMON"
    tw, _ = measure(t)
    text(t, int(60 - tw/2), 42)

    pen(8, 7, 12)
    t2 = "D-PAD TO PLAY"
    t2w, _ = measure(t2)
    text(t2, int(60 - t2w/2), 56)

    pen(6, 5, 10)
    t3 = "PRESS A TO START"
    t3w, _ = measure(t3)
    text(t3, int(60 - t3w/2), 68)
    hi_score = load_hi()
    if hi_score > 0:
        pen(15, 13, 2)
        tb = "BEST: " + str(hi_score)
        tbw, _ = measure(tb)
        text(tb, int(60 - tbw/2), 78)

def draw_fail():
    pen(12, 2, 2); frect(22, 42, 76, 36)
    pen(15, 5, 5); rect(22, 42, 76, 36)
    pen(15, 12, 12)
    t = "WRONG!"
    tw, _ = measure(t); text(t, int(60-tw/2), 48)
    pen(13, 13, 13)
    t2 = "SCORE: " + str(score)
    t2w, _ = measure(t2); text(t2, int(60-t2w/2), 60)
    hi_score = load_hi()
    if score >= hi_score and score > 0:
        pen(15, 13, 2)
        t3 = "NEW BEST!"
        t3w, _ = measure(t3); text(t3, int(60-t3w/2), 70)
        save_hi(score)

def draw_over():
    draw_fail()
    pen(8, 7, 12)
    t = "A TO RETRY"
    tw, _ = measure(t); text(t, int(60-tw/2), 82)

# =================================
# Update
# =================================
def update(tick):
    global state, pb_index, pb_timer, pb_phase, active_dir, active_timer
    global player_pos, input_timer, score, hi_score, round_num
    global fail_timer, correct_timer, sequence
    
    if pressed(Y):
        machine.soft_reset()
    
    # Tick down active flash
    if active_timer > 0:
        active_timer -= 1
        if active_timer == 0:
            active_dir = -1

    if state == STATE_TITLE:
        if pressed(A):
            reset_game()
            add_step()
            round_num = len(sequence)
            start_playback()
        return

    if state == STATE_OVER:
        if pressed(A):
            reset_game()
            add_step()
            round_num = len(sequence)
            start_playback()
            state = STATE_PLAYBACK
        return

    # --- Playback ---
    if state == STATE_PLAYBACK:
        pb_timer -= 1
        if pb_timer <= 0:
            if pb_phase == 0:
                # End of ON phase — go to OFF
                pb_phase = 1
                pb_timer = FLASH_OFF
                clear_active()
            else:
                # End of OFF phase — advance to next item
                pb_index += 1
                pb_phase = 0
                if pb_index >= len(sequence):
                    # Finished playback — hand to player
                    start_input()
                else:
                    pb_timer = FLASH_ON
                    set_active(sequence[pb_index])
                    simon_voice.play(TONES[sequence[pb_index]], TONE_DUR * 16, 70)
        return

    # --- Player input ---
    if state == STATE_INPUT:
        input_timer -= 1
        if input_timer <= 0:
            # Timeout = wrong
            fail_voice.play(150, 60, 80)
            if score > hi_score: hi_score = score
            fail_timer = 60
            state = STATE_FAIL
            return

        pressed_dir = -1
        if pressed(UP):    pressed_dir = DIR_UP
        elif pressed(DOWN):  pressed_dir = DIR_DOWN
        elif pressed(LEFT):  pressed_dir = DIR_LEFT
        elif pressed(RIGHT): pressed_dir = DIR_RIGHT

        if pressed_dir >= 0:
            set_active(pressed_dir)
            blip.play(TONES[pressed_dir], 12 * 16, 60)
            input_timer = INPUT_GRACE   # reset grace timer on each press

            if pressed_dir == sequence[player_pos]:
                player_pos += 1
                score += 1
                if player_pos >= len(sequence):
                    # Completed sequence!
                    correct_timer = 30
                    state = STATE_WIN
            else:
                # Wrong!
                fail_voice.play(150, 60, 80)
                if score > hi_score: hi_score = score
                fail_timer = 60
                state = STATE_FAIL
        return

    # --- Brief win flash before next round ---
    if state == STATE_WIN:
        correct_timer -= 1
        if correct_timer <= 0:
            add_step()
            round_num = len(sequence)
            start_playback()
        return

    # --- Fail animation ---
    if state == STATE_FAIL:
        fail_timer -= 1
        if fail_timer <= 0:
            state = STATE_OVER
        return

# =================================
# Draw
# =================================
def draw(tick):
    pen(2, 2, 4); frect(0, 0, SCREEN_W, SCREEN_H)

    if state == STATE_TITLE:
        draw_title()
        return

    draw_board()
    draw_state_label()
    draw_hud()

    if state == STATE_FAIL:
        draw_fail()
    elif state == STATE_OVER:
        draw_over()

# =================================
# Start
# =================================
start()