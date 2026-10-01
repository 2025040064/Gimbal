#include "main.h"
#include "usart.h"
#include "gpio.h"
#include "motor.h"
#include "oled.h"
#include "k230.h"
#include "adc.h"
#include "mpu6050.h"
#include "stabilizer.h"
#include "dwt_delay.h"
#include "app.h"

int main(void)
{
    // 系统初始化
    HAL_Init();
    DWT_Init();
    SystemClock_Config();
    
    // 外设初始化
    MX_GPIO_Init();
    MX_USART1_UART_Init();
    MX_TIM2_Init();
    MX_ADC1_Init();
    
    // 模块初始化
    K230_Init();
    MPU6050_Init();
    OLED_Init();
    OLED_Clear();
    
    // 电机初始化
    Motor_GPIO_Init(&hmotor1);
    Motor_GPIO_Init(&hmotor2);
    MotorCtrl_Init(&motorCtrl1, &hmotor1);
    MotorCtrl_Init(&motorCtrl2, &hmotor2);
    
    // 稳定器初始化
    Stabilizer_Init();
    Motor_All_Stop();
    
    // 启动提示
    OLED_ShowString(0, 0, (uint8_t*)"System Ready...", 16);
    OLED_ShowString(0, 2, (uint8_t*)"Click to switch", 16);
    OLED_ShowString(0, 4, (uint8_t*)"display page", 16);
    HAL_Delay(1500);
    OLED_Clear();
    
    // 启动定时器中断
    HAL_TIM_Base_Start_IT(&htim2);
    
    // 主循环
    uint32_t last_oled_update = 0;
    uint32_t last_dwt_reset = 0;
    
    while (1)
    {
        // DWT溢出自动重置（每50秒）
        if (HAL_GetTick() - last_dwt_reset >= 50000) {
            __disable_irq();
            uint32_t offset = DWT->CYCCNT;
            DWT->CYCCNT = 0;
            motorCtrl1.next_pulse_tick -= offset;
            motorCtrl2.next_pulse_tick -= offset;
            __enable_irq();
            last_dwt_reset = HAL_GetTick();
        }

        // 读取输入
        Joystick_Read(&joystick_x, &joystick_y);
        joy_key = Joystick_K_Read();
        Key_Process();

        // 处理按键事件
        if (key_single_click) {
            current_page = (current_page + 1) % 2;
            OLED_Clear();
            key_single_click = 0;
        }

        // 读取MPU6050数据（100ms一次）
        if (HAL_GetTick() - last_mpu_read >= 100) {
            MPU6050_ReadData(&mpu_data);
            last_mpu_read = HAL_GetTick();
        }

        // 更新稳定器和K230数据
        Stabilizer_Update();
        K230_Process();

        // 更新OLED显示（200ms一次）
        if (HAL_GetTick() - last_oled_update >= 200) {
            Update_OLED_Display();
            last_oled_update = HAL_GetTick();
        }

        // LED状态指示
        if (MotorCtrl_IsRunning(&motorCtrl1) || MotorCtrl_IsRunning(&motorCtrl2))
            HAL_GPIO_TogglePin(LED_GPIO_Port, LED_Pin);
        else
            HAL_GPIO_WritePin(LED_GPIO_Port, LED_Pin, GPIO_PIN_RESET);
    }
}
