#ifndef STABILIZER_H
#define STABILIZER_H

#include "k230.h"

enum TaskState { TASK_SYNC, TASK_ARM, TASK_SEARCH, TASK_TRACK, TASK_HOLD,
                 TASK_WAIT_LOSS, TASK_OCCLUDED, TASK_REARM, TASK_DONE, TASK_TIMEOUT, TASK_FAULT };
enum Motion { MOTION_STOP, MOTION_SCAN, MOTION_TRACK };

typedef struct {
    char mode;
    uint8_t id;
    enum TaskState state;
    enum Motion motion;
    uint8_t scan_point, scan_issued, locked, centered, d_trials, d_passes, left_view;
    int8_t yaw_deg, pitch_deg;
    uint16_t ids;
    uint32_t started, entered, last_rx, last_obs, center_since, lock_ms, hold_ms;
    uint32_t lost_at, reveal_at, last_sample, d_last_ms;
    uint16_t sequence;
    uint8_t have_sequence;
    VisionFrame frame;
} Contest;

void Contest_Init(Contest *task, char mode, uint8_t id, uint32_t now);
void Contest_Update(Contest *task, const VisionFrame *frame, uint32_t now, int arrived);
int Contest_Ended(const Contest *task);
const char *Contest_Command(const Contest *task);

#endif
