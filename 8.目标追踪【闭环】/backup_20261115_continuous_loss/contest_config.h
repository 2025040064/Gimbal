#ifndef CONTEST_CONFIG_H
#define CONTEST_CONFIG_H

/* Competition operator changes only this target ID (0-9). */
#define CONTEST_TARGET_ID 1

/* Internal setup: S = fixed A/B1/B2/B3/C-horizontal/C-diagonal/D sequence. */
#define CONTEST_MODE 'S'
#define VISION_ONE_WAY 1 /* K230 TX -> PB11 RX only; target selection stays on STM32. */

/* Pulses per full revolution of the OUTPUT axis, including reduction. */
/* Confirmed 2026-11-12: both Yingpengfei 42 motors, 20000 pulses/rev, direct drive. */
#define YAW_PULSES_PER_TURN 20000
#define PITCH_PULSES_PER_TURN 20000
#define YAW_POSITIVE_CW 1
#define PITCH_POSITIVE_CW 0

/* Establish safe speeds and coverage on the assembled gimbal before enabling. */
#define MOTION_CALIBRATED 1
#define SCAN_PITCH_STEP_DEG 10
#define SEARCH_PITCH_LIMIT_DEG 10 /* search B/C/D/F around reset zero; A keeps full scan range */
#define SCAN_PULSE_US 1000
#define TRACK_MIN_PULSE_US 700
#define CENTER_TOLERANCE_PX 12
#define TRACK_DEADZONE_PX 8
#define TRACK_RESTART_PX 12
#define TRACK_OBSERVATION_MS 350u
#define TRACK_LOSS_WAIT_MS 450u
#define TRACK_ACCEL_PPS2 2400
#define TRACK_GAIN_PPS 2000 /* speed at one half-frame error, before saturation */

/* Manual forward zero at EVERY reset. Limits are relative to that zero. */
#define YAW_LIMIT_DEG 60
#define PITCH_LIMIT_DEG 20
#define A_SCAN_MS 60000u
#define ACQUIRE_MS 15000u
#define CENTER_REQUIRED_MS 1000u
#define B_TOTAL_MS 20000u
#define B_HOLD_MS 5000u
#define C_SCORE_MS 15000u
#define D_OCCLUSION_MS 2000u
#define D_RECAPTURE_MS 8000u
#define D_WAIT_LOSS_MS 30000u
#define D_TRIALS 3
#define LINK_TIMEOUT_MS 500u
#define OBS_TIMEOUT_MS 1100u
#define SYNC_TIMEOUT_MS 30000u
#define ARM_TIMEOUT_MS 5000u
#define CONTROL_STALL_MS 100u

/* In J mode, verify one axis at a time, starting at the manual zero. */
#define JOG_AXIS 0
#define JOG_PULSES 100
#define JOG_PULSE_US 8000

#endif
