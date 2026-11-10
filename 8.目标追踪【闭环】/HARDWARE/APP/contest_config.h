#ifndef CONTEST_CONFIG_H
#define CONTEST_CONFIG_H

#define CONTEST_MODE 'T'       /* A-D, T for stationary link test, J for a calibration jog */
#define CONTEST_TARGET_ID 1

/* Pulses per full revolution of the OUTPUT axis, including reduction. */
#define YAW_PULSES_PER_TURN 0
#define PITCH_PULSES_PER_TURN 0
#define YAW_POSITIVE_CW 1
#define PITCH_POSITIVE_CW 0

/* Establish safe speeds and coverage on the assembled gimbal before enabling. */
#define MOTION_CALIBRATED 0
#define SCAN_PITCH_STEP_DEG 10
#define SCAN_PULSE_US 1000
#define TRACK_MIN_PULSE_US 700
#define CENTER_TOLERANCE_PX 12
#define TRACK_DEADZONE_PX 8

/* In J mode, verify one axis at a time, starting at the manual zero. */
#define JOG_AXIS 0
#define JOG_PULSES 100
#define JOG_PULSE_US 8000

#endif
