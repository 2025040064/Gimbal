#ifndef MOTOR_H
#define MOTOR_H

#include "main.h"

#define CW 0
#define CCW 1

typedef struct {
    GPIO_TypeDef *PUL_GPIO_Port;
    uint16_t PUL_Pin;
    GPIO_TypeDef *DIR_GPIO_Port;
    uint16_t DIR_Pin;
    GPIO_TypeDef *ENA_GPIO_Port;
    uint16_t ENA_Pin;
} Motor_HandleTypeDef;

typedef struct {
    Motor_HandleTypeDef *hw;
    volatile int32_t position;
    volatile int32_t goal;
    volatile uint16_t period_ticks;
    volatile uint16_t remaining_ticks;
    volatile int8_t direction;
    uint8_t positive_cw;
} MotorCtrl_TypeDef;

extern Motor_HandleTypeDef hmotor1, hmotor2;

void MotorCtrl_Init(MotorCtrl_TypeDef *motor, Motor_HandleTypeDef *hw, uint8_t positive_cw);
void MotorCtrl_Move(MotorCtrl_TypeDef *motor, int32_t goal, uint16_t period_us);
void MotorCtrl_Stop(MotorCtrl_TypeDef *motor);
void MotorCtrl_Update(MotorCtrl_TypeDef *motor);

#endif
