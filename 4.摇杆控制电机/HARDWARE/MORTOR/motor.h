#ifndef __MOTOR_H
#define __MOTOR_H
#include "stm32f1xx_hal.h"

#define PULSE_PER_REV 20000 // 每转20000脉冲
#define DEFAULT_SPEED 500   // 默认脉冲间隔(us) 约6rpm

void Motor_Init(void);
void Motor_Run(uint8_t motor, float rev, uint8_t dir, uint16_t delay_us);

#endif
