#include "stabilizer.h"
#include "motor.h"
#include "mpu6050.h"
#include "adc.h"
#include "k230.h"
#include <math.h>   

#define DEADZONE            15
#define HYSTERESIS          6
#define MAX_DELAY           8000
#define MIN_DELAY           500
#define STAB_PERIOD_MS      10

/* 追踪参数 */
#define TRACK_DEADZONE      8       // 追踪死区（像素），适当增大避免抖动
#define MAX_TRACK_DELAY     5500    // 追踪最大延迟，可在此微调
#define TRACK_ACCEL_RATE    3       // 追踪加速度，比默认2稍快，比5更柔和
#define ERROR_FILTER_COEF   0.25f   // 误差低通滤波系数（0~1），越小越平滑但响应稍慢

extern uint16_t joystick_x;
extern uint16_t joystick_y;
extern MPU6050_Data_TypeDef mpu_data;
extern MotorCtrl_TypeDef motorCtrl1;
extern MotorCtrl_TypeDef motorCtrl2;
extern uint8_t k230_data_valid;

#define JOY_MID  50

static uint8_t m1_was_running = 0, m2_was_running = 0;
static uint32_t last_stab_time = 0;

// 误差低通滤波状态
static float filtered_error_x = 0.0f;
static float filtered_error_y = 0.0f;

uint16_t motor1_delay_display = 80;
uint16_t motor2_delay_display = 80;

// 摇杆速度曲线（不变）
static uint16_t delay_from_joystick(int16_t offset) {
    uint16_t abs_off = abs(offset);
    if (abs_off < 20) {
        return 8000 - (2000 * abs_off) / 20;
    } else if (abs_off < 40) {
        return 6000 - (2500 * (abs_off - 20)) / 20;
    } else {
        return 3500 - (3000 * (abs_off - 40)) / 10;
    }
}

/**
 * @brief  根据像素误差计算追踪脉冲延迟（三次平滑曲线）
 * @param  error      像素误差（绝对值）
 * @param  half_range 图像半宽/半高
 * @return 脉冲延迟(us)
 */
static uint16_t track_delay_from_error(int16_t error, int16_t half_range) {
    float norm = (float)abs(error) / (float)half_range;
    if (norm > 1.0f) norm = 1.0f;

    // 三次方曲线：误差大 → delay 小（高速）；误差接近0 → delay 急剧增大（平缓减速）
    float factor = (1.0f - norm) * (1.0f - norm) * (1.0f - norm);
    uint16_t delay = (uint16_t)(MIN_DELAY + (MAX_TRACK_DELAY - MIN_DELAY) * factor);
    
    if (delay < MIN_DELAY) delay = MIN_DELAY;
    if (delay > MAX_TRACK_DELAY) delay = MAX_TRACK_DELAY;
    return delay;
}

void Stabilizer_Init(void) {
    m1_was_running = 0;
    m2_was_running = 0;
    filtered_error_x = 0.0f;
    filtered_error_y = 0.0f;
    last_stab_time = HAL_GetTick();
}

void Stabilizer_Update(void) {
    if (HAL_GetTick() - last_stab_time < STAB_PERIOD_MS) return;
    last_stab_time = HAL_GetTick();

    int16_t dx = (int16_t)joystick_x - JOY_MID;
    int16_t dy = (int16_t)joystick_y - JOY_MID;
    uint8_t joystick_active = (abs(dx) > DEADZONE) || (abs(dy) > DEADZONE);

    uint8_t has_target = k230_data_valid && 
                         !(target_x == -1 && target_y == -1 && target_w == -1 && target_h == -1);

    if (joystick_active) {
        // 摇杆模式（最高优先级）
        // 恢复摇杆正常加速度
        motorCtrl1.accel_rate = 2;
        motorCtrl2.accel_rate = 2;

        // --- 电机1（Y轴） ---
        if (m1_was_running) {
            if (abs(dy) < DEADZONE - HYSTERESIS) {
                motorCtrl1.is_running = 0;
                m1_was_running = 0;
                motor1_delay_display = 80;
            }
        } else {
            if (abs(dy) > DEADZONE) {
                m1_was_running = 1;
            }
        }
        if (m1_was_running) {
            uint16_t delay = delay_from_joystick(dy);
            motor1_delay_display = delay / 100;
            uint8_t dir = (dy > 0) ? CCW : CW;
            MotorCtrl_SetSpeed(&motorCtrl1, delay, dir);
        }

        // --- 电机2（X轴） ---
        if (m2_was_running) {
            if (abs(dx) < DEADZONE - HYSTERESIS) {
                motorCtrl2.is_running = 0;
                m2_was_running = 0;
                motor2_delay_display = 80;
            }
        } else {
            if (abs(dx) > DEADZONE) {
                m2_was_running = 1;
            }
        }
        if (m2_was_running) {
            uint16_t delay = delay_from_joystick(dx);
            motor2_delay_display = delay / 100;
            uint8_t dir = (dx > 0) ? CCW : CW;
            MotorCtrl_SetSpeed(&motorCtrl2, delay, dir);
        }
    }
    else if (has_target) {
        // K230 目标追踪模式
        if (screen_w == 0 || screen_h == 0) {
            motorCtrl1.is_running = 0;
            motorCtrl2.is_running = 0;
            m1_was_running = 0;
            m2_was_running = 0;
            return;
        }

        // 设置追踪专用加速度
        motorCtrl1.accel_rate = TRACK_ACCEL_RATE;
        motorCtrl2.accel_rate = TRACK_ACCEL_RATE;

        int16_t center_x = screen_w / 2;
        int16_t center_y = screen_h / 2;
        int16_t raw_error_x = target_x - center_x;
        int16_t raw_error_y = target_y - center_y;

        // 一阶低通滤波，去除高频抖动
        filtered_error_x = ERROR_FILTER_COEF * raw_error_x + (1.0f - ERROR_FILTER_COEF) * filtered_error_x;
        filtered_error_y = ERROR_FILTER_COEF * raw_error_y + (1.0f - ERROR_FILTER_COEF) * filtered_error_y;

        int16_t error_x = (int16_t)filtered_error_x;
        int16_t error_y = (int16_t)filtered_error_y;

        // --- 电机2（X轴追踪）---
        if (abs(error_x) > TRACK_DEADZONE) {
            uint16_t delay = track_delay_from_error(error_x, center_x);
            motor2_delay_display = delay / 100;
            uint8_t dir = (error_x > 0) ? CW : CCW;  
            MotorCtrl_SetSpeed(&motorCtrl2, delay, dir);
            m2_was_running = 1;
        } else {
            if (m2_was_running) {
                motorCtrl2.is_running = 0;
                m2_was_running = 0;
                motor2_delay_display = 80;
            }
        }

        // --- 电机1（Y轴追踪）---
        if (abs(error_y) > TRACK_DEADZONE) {
            uint16_t delay = track_delay_from_error(error_y, center_y);
            motor1_delay_display = delay / 100;
            uint8_t dir = (error_y > 0) ? CCW : CW;
            MotorCtrl_SetSpeed(&motorCtrl1, delay, dir);
            m1_was_running = 1;
        } else {
            if (m1_was_running) {
                motorCtrl1.is_running = 0;
                m1_was_running = 0;
                motor1_delay_display = 80;
            }
        }
    }
    else {
        // 无摇杆且无目标 → 停止
        if (m1_was_running || motorCtrl1.is_running) {
            motorCtrl1.is_running = 0;
            m1_was_running = 0;
            motor1_delay_display = 80;
        }
        if (m2_was_running || motorCtrl2.is_running) {
            motorCtrl2.is_running = 0;
            m2_was_running = 0;
            motor2_delay_display = 80;
        }
    }
}
