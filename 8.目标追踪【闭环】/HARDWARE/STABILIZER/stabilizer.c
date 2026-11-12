#include "stabilizer.h"
#include "motor.h"
#include "k230.h"
#include <stdlib.h>

#define MIN_DELAY              500
#define MAX_TRACK_DELAY        5500
#define TRACK_DEADZONE         12
#define STOP_DELAY_DISPLAY     80

// Existing direction settings. Verify both axes on the assembled gimbal.
#define TRACK_X_POSITIVE_DIR   CW
#define TRACK_Y_POSITIVE_DIR   CCW

extern MotorCtrl_TypeDef motorCtrl1;
extern MotorCtrl_TypeDef motorCtrl2;

uint16_t motor1_delay_display = STOP_DELAY_DISPLAY;
uint16_t motor2_delay_display = STOP_DELAY_DISPLAY;

/* 根据像素误差计算追踪脉冲间隔，误差越大，间隔越短。 */
static uint16_t track_delay_from_error(int16_t error, int16_t half_range)
{
    float norm = (float)abs(error) / (float)half_range;
    if (norm > 1.0f) norm = 1.0f;
    float remaining = 1.0f - norm;
    return (uint16_t)(MIN_DELAY + (MAX_TRACK_DELAY - MIN_DELAY) *
                      remaining * remaining * remaining);
}

static void update_axis(MotorCtrl_TypeDef *motor, uint16_t *display_delay,
                        int16_t error, int16_t half_range, uint8_t positive_dir)
{
    uint16_t delay = (abs(error) > TRACK_DEADZONE)
                   ? track_delay_from_error(error, half_range) : 0;
    uint8_t dir = (error >= 0) ? positive_dir : (positive_dir == CW ? CCW : CW);

    // The TIM2 interrupt reads the motor state while generating pulses.
    uint32_t irq_state = __get_PRIMASK();
    __disable_irq();
    if (delay == 0) {
        motor->is_running = 0;
    } else {
        MotorCtrl_SetSpeed(motor, delay, dir);
    }
    __set_PRIMASK(irq_state);
    *display_delay = (delay == 0) ? STOP_DELAY_DISPLAY : delay / 100;
}

void Stabilizer_Update(void)
{
    if (!K230_TargetIsFresh()) {
        motorCtrl1.is_running = 0;
        motorCtrl2.is_running = 0;
        motor1_delay_display = motor2_delay_display = STOP_DELAY_DISPLAY;
        return;
    }

    int16_t center_x = screen_w / 2;
    int16_t center_y = screen_h / 2;
    update_axis(&motorCtrl2, &motor2_delay_display, target_x - center_x,
                center_x, TRACK_X_POSITIVE_DIR);
    update_axis(&motorCtrl1, &motor1_delay_display, target_y - center_y,
                center_y, TRACK_Y_POSITIVE_DIR);
}
