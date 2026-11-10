#include "stabilizer.h"
#include "contest_config.h"
#include <string.h>

#define LINK_MS 500u
#define OBS_MS 1100u
#define CONTINUITY_MS 450u
#define ROWS (1u + (40u + SCAN_PITCH_STEP_DEG - 1u) / SCAN_PITCH_STEP_DEG)

#if SCAN_PITCH_STEP_DEG < 1 || SCAN_PITCH_STEP_DEG > 20
#error Invalid scan pitch step
#endif

static void Enter(Contest *t, enum TaskState state, uint32_t now)
{
    t->state = state;
    t->entered = now;
}

void Contest_Init(Contest *t, char mode, uint8_t id, uint32_t now)
{
    memset(t, 0, sizeof(*t));
    t->mode = mode;
    t->id = id;
    Enter(t, TASK_SYNC, now);
}

int Contest_Ended(const Contest *t)
{
    return t->state >= TASK_DONE;
}

const char *Contest_Command(const Contest *t)
{
    if (t->state == TASK_SYNC || Contest_Ended(t)) return "STOP\n";
    return t->mode == 'A' ? "SCAN\n" : "ID";
}

static int Matching(const Contest *t, const VisionFrame *f)
{
    if (!f) return 0;
    if (t->mode == 'A') return f->mode == VISION_SCAN;
    return f->mode == VISION_TRACK && f->id == t->id;
}

static void Scan(Contest *t, int arrived)
{
    unsigned row;
    int pitch;
    if (t->scan_issued && arrived) {
        ++t->scan_point;
        if (t->scan_point == ROWS * 2u) t->scan_point = 0;
    }
    row = t->scan_point / 2u;
    pitch = -20 + (int)row * SCAN_PITCH_STEP_DEG;
    t->pitch_deg = pitch > 20 ? 20 : pitch;
    t->yaw_deg = ((row + t->scan_point % 2u) % 2u) ? 60 : -60;
    t->scan_issued = 1;
    t->motion = MOTION_SCAN;
}

static int Centered(const VisionFrame *f)
{
    int dx = f->x - f->width / 2;
    int dy = f->y - f->height / 2;
    return f->x >= 0 && dx >= -CENTER_TOLERANCE_PX && dx <= CENTER_TOLERANCE_PX &&
           dy >= -CENTER_TOLERANCE_PX && dy <= CENTER_TOLERANCE_PX;
}

static int UpdateCenter(Contest *t, uint32_t now)
{
    uint32_t gap = now - t->last_sample;
    int was_centered = t->centered;
    t->centered = Centered(&t->frame);
    if (!was_centered || gap > CONTINUITY_MS || !t->centered) t->center_since = now;
    if (t->state == TASK_HOLD && t->mode == 'B' && was_centered &&
        t->centered && gap <= CONTINUITY_MS) {
        uint32_t remaining = 5000u - (t->last_sample - t->entered);
        t->hold_ms += gap < remaining ? gap : remaining;
    }
    t->last_sample = now;
    return t->centered && now - t->center_since >= 1000u;
}

static void FinishDTrial(Contest *t, uint32_t now, int success)
{
    ++t->d_trials;
    t->d_passes += success;
    t->d_last_ms = success ? now - t->reveal_at : 0;
    t->centered = 0;
    if (t->d_trials == 3) Enter(t, TASK_DONE, now);
    else Enter(t, success ? TASK_WAIT_LOSS : TASK_REARM, now);
}

void Contest_Update(Contest *t, const VisionFrame *f, uint32_t now, int arrived)
{
    int fresh = 0;
    int stable = 0;
    int target;

    t->motion = MOTION_STOP;
    if (Contest_Ended(t)) return;
    if (f && f->mode == VISION_FAULT) {
        Enter(t, TASK_FAULT, now);
        return;
    }
    if (t->state == TASK_SYNC) {
        if (f && f->mode == VISION_IDLE) Enter(t, TASK_ARM, now);
        else if (now - t->entered >= 30000u) Enter(t, TASK_FAULT, now);
        return;
    }
    if (t->state == TASK_ARM) {
        if (Matching(t, f)) {
            t->started = t->last_rx = t->last_obs = now;
            Enter(t, TASK_SEARCH, now);
        } else {
            if (now - t->entered >= 5000u) Enter(t, TASK_FAULT, now);
            return;
        }
    }
    if (Matching(t, f)) {
        t->last_rx = now;
        if (!t->have_sequence || f->sequence != t->sequence) {
            t->have_sequence = 1;
            t->sequence = f->sequence;
            t->last_obs = now;
            t->frame = *f;
            fresh = 1;
        }
    } else if (f && f->mode != VISION_LEGACY) {
        Enter(t, TASK_FAULT, now);
        return;
    }
    if (now - t->last_rx >= LINK_MS || now - t->last_obs >= OBS_MS) {
        Enter(t, TASK_FAULT, now);
        return;
    }

    if (t->mode == 'A') {
        if (now - t->started >= 60000u) {
            Enter(t, TASK_DONE, now);
            return;
        }
        if (fresh) t->ids |= t->frame.ids & 0x03FFu;
        Scan(t, arrived);
        return;
    }

    target = t->frame.x >= 0;
    if (fresh) stable = UpdateCenter(t, now);

    if (t->mode == 'B') {
        if (t->state == TASK_HOLD && now - t->entered >= 5000u) {
            Enter(t, TASK_DONE, now);
            return;
        }
        if (t->state != TASK_HOLD) {
            if (now - t->started > 15000u || (now - t->started == 15000u && !stable)) {
                Enter(t, TASK_TIMEOUT, now);
                return;
            }
            if (stable) {
                t->locked = 1;
                t->lock_ms = now - t->started;
                Enter(t, TASK_HOLD, now);
            }
        }
    } else if (t->mode == 'C') {
        if (now - t->started >= 30000u) {
            Enter(t, TASK_DONE, now);
            return;
        }
        if (now - t->started >= 15000u && !target) t->left_view = 1;
        if (stable && !t->locked) {
            t->locked = 1;
            t->lock_ms = now - t->started;
        }
    } else if (t->mode == 'D') {
        if (!t->locked) {
            if (now - t->started > 15000u || (now - t->started == 15000u && !stable)) {
                Enter(t, TASK_TIMEOUT, now);
                return;
            }
            if (stable) {
                t->locked = 1;
                t->lock_ms = now - t->started;
                Enter(t, TASK_WAIT_LOSS, now);
            }
        } else if (t->state == TASK_REARM) {
            if (stable) Enter(t, TASK_WAIT_LOSS, now);
            else if (now - t->entered >= 15000u) {
                Enter(t, TASK_TIMEOUT, now);
                return;
            }
        } else if (t->state == TASK_WAIT_LOSS) {
            if (!target) {
                t->lost_at = now;
                t->reveal_at = now + 2000u;
                t->scan_issued = 0;
                Enter(t, TASK_OCCLUDED, now);
                return;
            }
            if (now - t->entered >= 30000u) {
                Enter(t, TASK_TIMEOUT, now);
                return;
            }
        } else if (t->state == TASK_OCCLUDED) {
            if (now - t->lost_at < 2000u && !target) return;
            if (now - t->lost_at < 2000u) t->reveal_at = now;
            Enter(t, TASK_SEARCH, now);
        }
        if (t->locked && (t->state == TASK_SEARCH || t->state == TASK_TRACK)) {
            uint32_t elapsed = now - t->reveal_at;
            if (stable && elapsed <= 8000u) FinishDTrial(t, now, 1);
            else if (elapsed >= 8000u) FinishDTrial(t, now, 0);
            if (Contest_Ended(t)) return;
        }
    }

    if (target) {
        t->motion = MOTION_TRACK;
        t->scan_issued = 0;
        if (t->state == TASK_SEARCH) Enter(t, TASK_TRACK, now);
    } else {
        if (t->state == TASK_TRACK) {
            Enter(t, TASK_SEARCH, now);
            return;
        }
        Scan(t, arrived);
    }
}
