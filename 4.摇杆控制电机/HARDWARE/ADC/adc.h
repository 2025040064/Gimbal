#ifndef __ADC_H
#define __ADC_H
#include "stm32f1xx_hal.h"

// 输出范围：X/Y=0~100，按键=0=按下/1=松开
void MX_ADC1_Init(void);
void Joystick_Read(uint16_t *x, uint16_t *y);
uint8_t Joystick_K_Read(void);

#endif

