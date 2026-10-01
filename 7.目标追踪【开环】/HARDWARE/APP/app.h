#ifndef __APP_H
#define __APP_H

#include "main.h"
#include "motor.h"
#include "mpu6050.h"

// 全局变量声明
extern MotorCtrl_TypeDef motorCtrl1;
extern MotorCtrl_TypeDef motorCtrl2;
extern char oled_buf[32];
extern uint16_t joystick_x;
extern uint16_t joystick_y;
extern uint8_t joy_key;
extern uint8_t m1_run;
extern uint8_t m2_run;
extern MPU6050_Data_TypeDef mpu_data;
extern uint32_t last_mpu_read;
extern uint8_t current_page;
extern uint8_t key_state;
extern uint32_t key_press_time;
extern uint32_t key_release_time;
extern uint8_t key_single_click;
extern uint8_t k230_data_valid;
extern TIM_HandleTypeDef htim2;

// 宏定义
#define SHOW_MODE    0
#define KEY_DEBOUNCE_TIME 20

// 函数声明
void MX_TIM2_Init(void);
void Update_OLED_Display(void);
void Motor_All_Stop(void);
void Key_Process(void);
void SystemClock_Config(void);
void Error_Handler(void);

#endif /* __APP_H */
