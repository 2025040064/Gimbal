#ifndef __APP_H
#define __APP_H

#include "main.h"
#include "motor.h"
#include "mpu6050.h"

// 全局变量声明
extern MotorCtrl_TypeDef motorCtrl1;
extern MotorCtrl_TypeDef motorCtrl2;
extern char oled_buf[32];
extern uint8_t m1_run;
extern uint8_t m2_run;
extern MPU6050_Data_TypeDef mpu_data;
extern uint32_t last_mpu_read;
extern TIM_HandleTypeDef htim2;

// 宏定义
#define SHOW_MODE    0

// 函数声明
void MX_TIM2_Init(void);
void Update_OLED_Display(void);
void Motor_All_Stop(void);
void SystemClock_Config(void);
void Error_Handler(void);

#endif /* __APP_H */
