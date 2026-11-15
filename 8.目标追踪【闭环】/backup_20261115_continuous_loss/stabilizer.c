#include "stabilizer.h"
#include "contest_config.h"
#include <string.h>

#define CONTINUITY_MS TRACK_OBSERVATION_MS
#define ROWS (1u + (2u * PITCH_LIMIT_DEG + SCAN_PITCH_STEP_DEG - 1u) / SCAN_PITCH_STEP_DEG)

#if SCAN_PITCH_STEP_DEG < 1 || SCAN_PITCH_STEP_DEG > 20
#error Invalid scan pitch step
#endif
#if SEARCH_PITCH_LIMIT_DEG < 0 || SEARCH_PITCH_LIMIT_DEG > PITCH_LIMIT_DEG || SEARCH_PITCH_LIMIT_DEG % SCAN_PITCH_STEP_DEG != 0
#error Invalid search pitch range
#endif
#if YAW_LIMIT_DEG < 1 || YAW_LIMIT_DEG > 90 || PITCH_LIMIT_DEG < 1 || PITCH_LIMIT_DEG > 45 || ROWS * 2u > 255u
#error Invalid scan bounds
#endif
#if D_TRIALS != 3 || B_TOTAL_MS < ACQUIRE_MS + B_HOLD_MS || TRACK_OBSERVATION_MS >= OBS_TIMEOUT_MS
#error Invalid contest timing configuration
#endif
#if TRACK_RESTART_PX <= TRACK_DEADZONE_PX || TRACK_RESTART_PX > CENTER_TOLERANCE_PX
#error Invalid tracking hysteresis
#endif
#if TRACK_ACCEL_PPS2 < 1000 || TRACK_ACCEL_PPS2 > 20000 || TRACK_GAIN_PPS < 1 || TRACK_GAIN_PPS > 10000
#error Invalid tracking gain or acceleration
#endif

void TrackControl_Reset(TrackControl *c)
{
    memset(c, 0, sizeof(*c));
}

uint16_t ContestSequence_Encode(unsigned stage)
{
    if (stage > 7) stage = 0;
    return (uint16_t)(0xA500 | (stage << 4) | (stage ^ 15));
}

unsigned ContestSequence_Decode(uint16_t saved)
{
    unsigned stage = (saved >> 4) & 15;
    if (stage > 7 || saved != ContestSequence_Encode(stage)) return 0;
    return stage;
}

char ContestSequence_Mode(unsigned stage)
{
    const char modes[] = "ABBBCCDD";
    return modes[stage <= 7 ? stage : 0];
}

unsigned ContestSequence_Next(unsigned stage, enum TaskState state)
{
    if (stage > 7) return 0;
    if (stage < 7 && (state == TASK_DONE || state == TASK_TIMEOUT)) ++stage;
    return stage;
}

int32_t TrackControl_Update(TrackControl *c, int error, int half,
                           uint16_t sequence, uint32_t now)
{
    int32_t wanted, step, magnitude;
    uint32_t dt;
    if (half <= 0) { TrackControl_Reset(c); return 0; }
    if (!c->initialized) {
        c->initialized = 1;
        c->sequence = sequence;
        c->filtered_q8 = error * 256;
        c->updated = now;
    } else if (sequence != c->sequence) {
        c->sequence = sequence;
        /* Only new camera observations advance the filter. */
        c->filtered_q8 += (error * 256 - c->filtered_q8) * 3 / 4;
    }
    dt = now - c->updated;
    c->updated = now;
    if (dt > 50u) dt = 50u;
    magnitude = error < 0 ? -error : error;
    /* Raw center/sign gates avoid filter lag driving across the center. */
    if (magnitude <= TRACK_DEADZONE_PX) {
        c->moving = 0;
        c->speed = 0;
        c->filtered_q8 = error * 256;
        return 0;
    }
    if (!c->moving && magnitude <= TRACK_RESTART_PX) return 0;
    c->moving = 1;
    wanted = c->filtered_q8 / 256;
    if ((wanted > 0 && error < 0) || (wanted < 0 && error > 0)) wanted = 0;
    wanted = wanted * TRACK_GAIN_PPS / half;
    if (wanted > 1000000 / TRACK_MIN_PULSE_US) wanted = 1000000 / TRACK_MIN_PULSE_US;
    if (wanted < -1000000 / TRACK_MIN_PULSE_US) wanted = -1000000 / TRACK_MIN_PULSE_US;
    /* A direction change must pass through zero for at least one update. */
    if ((wanted < 0 && c->speed > 0) || (wanted > 0 && c->speed < 0)) wanted = 0;
    step = (int32_t)dt * TRACK_ACCEL_PPS2 / 1000;
    if (c->speed < wanted) {
        c->speed += step;
        if (c->speed > wanted) c->speed = wanted;
    } else if (c->speed > wanted) {
        c->speed -= step;
        if (c->speed < wanted) c->speed = wanted;
    }
    return c->speed;
}

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

void Contest_Fail(Contest *t, enum TaskFault fault, uint32_t now)
{
    t->fault = fault;
    t->centered = 0;
    t->motion = MOTION_STOP;
    Enter(t, TASK_FAULT, now);
}

const char *Contest_Command(const Contest *t)
{
    if (t->state == TASK_SYNC || Contest_Ended(t)) return "STOP\n";
    return t->mode == 'A' ? "SCAN\n" : "ID";
}

static int Matching(const Contest *t, const VisionFrame *f)
{
    if (!f) return 0;
    if (VISION_ONE_WAY && f->mode == VISION_BROADCAST)
        return t->mode == 'A' || f->id == t->id;
    if (t->mode == 'A') return f->mode == VISION_SCAN;
    return f->mode == VISION_TRACK && f->id == t->id;
}

static void Scan(Contest *t, int arrived)
{
    unsigned row;
    unsigned rows = t->mode == 'A' ? ROWS : 1 + 2 * (SEARCH_PITCH_LIMIT_DEG / SCAN_PITCH_STEP_DEG);
    int pitch;
    if (t->scan_issued && arrived) {
        ++t->scan_point;
        if (t->scan_point >= rows * 2) t->scan_point = 0;
    }
    row = t->scan_point / 2u;
    if (t->mode == 'A') pitch = -PITCH_LIMIT_DEG + (int)row * SCAN_PITCH_STEP_DEG;
    else if (row == 0) pitch = 0;
    else pitch = (int)((row + 1) / 2) * SCAN_PITCH_STEP_DEG * ((row & 1) ? -1 : 1);
    t->pitch_deg = pitch > PITCH_LIMIT_DEG ? PITCH_LIMIT_DEG : pitch;
    t->yaw_deg = ((row + t->scan_point % 2u) % 2u) ? YAW_LIMIT_DEG : -YAW_LIMIT_DEG;
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
    if (!was_centered || gap >= CONTINUITY_MS || !t->centered) t->center_since = now;
    if (t->locked && t->mode == 'B' && was_centered &&
        t->centered && gap < CONTINUITY_MS) {
        uint32_t from = t->last_sample - t->hold_started;
        uint32_t to = now - t->hold_started;
        if (from < B_HOLD_MS) {
            if (to > B_HOLD_MS) to = B_HOLD_MS;
            t->hold_ms += to - from;
        }
    }
    t->last_sample = now;
    return t->centered && now - t->center_since >= CENTER_REQUIRED_MS;
}

static void FinishDTrial(Contest *t, uint32_t now, int success)
{
    t->d_last_ms = success ? now - t->reveal_at : D_RECAPTURE_MS;
    t->d_times[t->d_trials] = t->d_last_ms;
    if (success) t->d_success_mask |= 1u << t->d_trials;
    ++t->d_trials;
    t->d_passes += success;
    t->centered = 0;
    if (t->d_trials == D_TRIALS) Enter(t, TASK_DONE, now);
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
        Contest_Fail(t, FAULT_VISION, now);
        return;
    }
    if (t->state == TASK_SYNC) {
        if (f && (f->mode == VISION_IDLE || (VISION_ONE_WAY && Matching(t, f)))) Enter(t, TASK_ARM, now);
        else if (now - t->entered >= SYNC_TIMEOUT_MS) Contest_Fail(t, FAULT_SYNC, now);
        return;
    }
    if (t->state == TASK_ARM) {
        if (Matching(t, f)) {
            t->started = t->last_rx = t->last_obs = now;
            Enter(t, TASK_SEARCH, now);
        } else {
            if (now - t->entered >= ARM_TIMEOUT_MS) Contest_Fail(t, FAULT_ARM, now);
            return;
        }
    }
    if (Matching(t, f)) {
        t->last_rx = now;
        if (!t->have_sequence || (f->sequence != t->sequence &&
            (uint16_t)(f->sequence - t->sequence) < 32768u)) {
            t->have_sequence = 1;
            t->sequence = f->sequence;
            t->last_obs = now;
            t->frame = *f;
            fresh = 1;
        }
    } else if (f && f->mode != VISION_LEGACY) {
        Contest_Fail(t, FAULT_IDENTITY, now);
        return;
    }
    if (now - t->last_rx >= LINK_TIMEOUT_MS || now - t->last_obs >= OBS_TIMEOUT_MS) {
        Contest_Fail(t, now - t->last_rx >= LINK_TIMEOUT_MS ? FAULT_LINK : FAULT_OBSERVATION, now);
        return;
    }

    if (t->mode == 'A') {
        if (now - t->started >= A_SCAN_MS) {
            Enter(t, TASK_DONE, now);
            return;
        }
        if (fresh) t->ids |= t->frame.ids & 0x03FFu;
        if (now - t->last_obs >= TRACK_OBSERVATION_MS) return;
        Scan(t, arrived);
        return;
    }

    target = t->frame.x >= 0;
    if (fresh && target) { t->last_target = now; t->seen_target = 1; }
    if (now - t->last_obs >= TRACK_OBSERVATION_MS) {
        t->centered = 0;
        t->center_since = now;
        /* Keep the task deadline running, but never drive on stale data. */
        target = 0;
    }
    /* Do not accumulate centering while the nominal occlusion is in progress. */
    if (t->state == TASK_OCCLUDED) {
        t->centered = 0;
        t->center_since = now;
    }
    if (fresh && (t->state != TASK_OCCLUDED || now - t->lost_at >= D_OCCLUSION_MS))
        stable = UpdateCenter(t, now);

    if (t->mode == 'B') {
        uint32_t elapsed = now - t->started;
        if (elapsed >= B_TOTAL_MS) {
            Enter(t, t->locked ? TASK_DONE : TASK_TIMEOUT, now);
            return;
        }
        if (!t->locked && !t->acquire_failed) {
            if (stable && elapsed <= ACQUIRE_MS) {
                t->locked = 1;
                t->lock_ms = elapsed;
                t->hold_started = now;
                Enter(t, TASK_HOLD, now);
            } else if (elapsed >= ACQUIRE_MS) t->acquire_failed = 1;
        }
    } else if (t->mode == 'C') {
        t->scoring = now - t->started >= ACQUIRE_MS;
        if (now - t->started >= ACQUIRE_MS + C_SCORE_MS) {
            Enter(t, TASK_DONE, now);
            return;
        }
        if (t->scoring && !target) t->left_view = 1;
        if (stable && !t->locked) {
            t->locked = 1;
            t->lock_ms = now - t->started;
        }
    } else if (t->mode == 'D') {
        if (!t->locked) {
            if (now - t->started > ACQUIRE_MS || (now - t->started == ACQUIRE_MS && !stable)) {
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
            else if (now - t->entered >= ACQUIRE_MS) {
                Enter(t, TASK_TIMEOUT, now);
                return;
            }
        } else if (t->state == TASK_WAIT_LOSS) {
            if (fresh && !target) {
                t->lost_at = now;
                t->reveal_at = now + D_OCCLUSION_MS;
                t->scan_issued = 0;
                Enter(t, TASK_OCCLUDED, now);
                return;
            }
            if (now - t->entered >= D_WAIT_LOSS_MS) {
                Enter(t, TASK_TIMEOUT, now);
                return;
            }
        } else if (t->state == TASK_OCCLUDED) {
            if (now - t->lost_at < D_OCCLUSION_MS) return;
            Enter(t, TASK_SEARCH, now);
        }
        if (t->locked && (t->state == TASK_SEARCH || t->state == TASK_TRACK)) {
            uint32_t elapsed = now - t->reveal_at;
            if (stable && elapsed <= D_RECAPTURE_MS) FinishDTrial(t, now, 1);
            else if (elapsed >= D_RECAPTURE_MS) FinishDTrial(t, now, 0);
            if (Contest_Ended(t)) return;
        }
    }

    if (now - t->last_obs >= TRACK_OBSERVATION_MS) return;
    if (target) {
        t->motion = MOTION_TRACK;
        t->scan_issued = 0;
        t->scan_point = 0;
        if (t->state == TASK_SEARCH) Enter(t, TASK_TRACK, now);
    } else {
        if (t->seen_target && now - t->last_target < TRACK_LOSS_WAIT_MS) return;
        if (t->state == TASK_TRACK) {
            Enter(t, TASK_SEARCH, now);
        }
        Scan(t, arrived);
    }
}
