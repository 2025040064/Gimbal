#ifndef __MOTOR_H
#define __MOTOR_H

#include "main.h"
#include "dwt_delay.h"

#define CW  0
#define CCW 1
#define PULSE_PER_CIRCLE 20000

typedef struct {
    GPIO_TypeDef *PUL_GPIO_Port;
    uint16_t      PUL_Pin;
    GPIO_TypeDef *DIR_GPIO_Port;
    uint16_t      DIR_Pin;
    GPIO_TypeDef *ENA_GPIO_Port;
    uint16_t      ENA_Pin;
} Motor_HandleTypeDef;

typedef struct {
    Motor_HandleTypeDef *hw;
    uint8_t  dir;
    int32_t  target_steps;
    int32_t  current_step;
    int32_t  home_steps;
    uint32_t next_pulse_tick;
    uint16_t pulse_delay;      // 当前实际脉冲间隔(us)
    uint16_t target_delay;     // 目标脉冲间隔(us)
    int16_t  accel_rate;       // 加减速速率(us/ms)
    uint32_t last_accel_time;  // 每个电机独立的加减速时间戳
    uint8_t  is_running;
} MotorCtrl_TypeDef;

extern Motor_HandleTypeDef hmotor1;
extern Motor_HandleTypeDef hmotor2;

void Motor_GPIO_Init(Motor_HandleTypeDef *hmotor);
void Motor_Enable(Motor_HandleTypeDef *hmotor);
void Motor_Disable(Motor_HandleTypeDef *hmotor);
void Motor_SetDir(Motor_HandleTypeDef *hmotor, uint8_t dir);
void Motor_SinglePulse(Motor_HandleTypeDef *hmotor);

void MotorCtrl_Init(MotorCtrl_TypeDef *mc, Motor_HandleTypeDef *hw);
void MotorCtrl_SetTarget(MotorCtrl_TypeDef *mc, float circles, uint16_t delay_us, uint8_t dir);
void MotorCtrl_SetSpeed(MotorCtrl_TypeDef *mc, uint16_t delay_us, uint8_t dir);
void MotorCtrl_Update(MotorCtrl_TypeDef *mc);
float MotorCtrl_GetCircles(MotorCtrl_TypeDef *mc);
uint8_t MotorCtrl_IsRunning(MotorCtrl_TypeDef *mc);
void MotorCtrl_SetHome(MotorCtrl_TypeDef *mc);
void MotorCtrl_GoHome(MotorCtrl_TypeDef *mc, uint16_t delay_us);

#endif
