#ifndef STABILIZER_H
#define STABILIZER_H

#include "k230.h"

enum TaskState { TASK_SYNC, TASK_ARM, TASK_SEARCH, TASK_TRACK, TASK_HOLD,
                 TASK_WAIT_LOSS, TASK_OCCLUDED, TASK_REARM, TASK_DONE, TASK_TIMEOUT, TASK_FAULT };
enum Motion { MOTION_STOP, MOTION_SCAN, MOTION_TRACK };
enum TaskFault { FAULT_NONE, FAULT_VISION, FAULT_SYNC, FAULT_ARM,
                 FAULT_IDENTITY, FAULT_LINK, FAULT_OBSERVATION, FAULT_TX, FAULT_CONTROL, FAULT_SEQUENCE };

typedef struct {
    char mode;
    uint8_t id;
    enum TaskState state;
    enum Motion motion;
    uint8_t scan_point, scan_issued, locked, centered, d_trials, d_passes, left_view;
    int16_t yaw_deg, pitch_deg;
    uint16_t ids;
    uint32_t started, entered, last_rx, last_obs, center_since, lock_ms, hold_ms;
    uint32_t lost_at, reveal_at, last_sample, d_last_ms;
    uint16_t sequence;
    uint8_t have_sequence;
    VisionFrame frame;
    uint32_t last_target;
    uint8_t seen_target;
    uint8_t acquire_failed, scoring;
    enum TaskFault fault;
    uint32_t hold_started;
    uint32_t d_times[3]; /* Time after estimated reveal; timeout stored as 8000 ms. */
    uint8_t d_success_mask;
} Contest;

typedef struct {
    int32_t filtered_q8, speed;
    uint32_t updated;
    uint16_t sequence;
    uint8_t initialized, moving;
} TrackControl;

void TrackControl_Reset(TrackControl *control);
int32_t TrackControl_Update(TrackControl *control, int error, int half,
                           uint16_t sequence, uint32_t now);

void Contest_Init(Contest *task, char mode, uint8_t id, uint32_t now);
void Contest_Update(Contest *task, const VisionFrame *frame, uint32_t now, int arrived);
int Contest_Ended(const Contest *task);
const char *Contest_Command(const Contest *task);
void Contest_Fail(Contest *task, enum TaskFault fault, uint32_t now);
uint16_t ContestSequence_Encode(unsigned stage);
unsigned ContestSequence_Decode(uint16_t saved);
char ContestSequence_Mode(unsigned stage);
unsigned ContestSequence_Next(unsigned stage, enum TaskState state);

#endif
