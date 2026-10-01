#include "app.h"
#include "oled.h"
#include "k230.h"
#include "adc.h"
#include "stabilizer.h"
#include "stdio.h"

// 全局变量定义
MotorCtrl_TypeDef motorCtrl1;
MotorCtrl_TypeDef motorCtrl2;
char oled_buf[32];

uint16_t joystick_x = 50;
uint16_t joystick_y = 50;
uint8_t joy_key = 1;

uint8_t m1_run = 0;
uint8_t m2_run = 0;

MPU6050_Data_TypeDef mpu_data;
uint32_t last_mpu_read = 0;
uint8_t current_page = 0;

uint8_t key_state = 0;
uint32_t key_press_time = 0;
uint32_t key_release_time = 0;
uint8_t key_single_click = 0;

uint8_t k230_data_valid = 0;

TIM_HandleTypeDef htim2;

// 定时器初始化
void MX_TIM2_Init(void)
{
    TIM_ClockConfigTypeDef sClockSourceConfig = {0};
    htim2.Instance = TIM2;
    htim2.Init.Prescaler = 71;
    htim2.Init.CounterMode = TIM_COUNTERMODE_UP;
    htim2.Init.Period = 49;      // 50us中断一次
    htim2.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
    htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
    if (HAL_TIM_Base_Init(&htim2) != HAL_OK) {
        Error_Handler();
    }
    sClockSourceConfig.ClockSource = TIM_CLOCKSOURCE_INTERNAL;
    if (HAL_TIM_ConfigClockSource(&htim2, &sClockSourceConfig) != HAL_OK) {
        Error_Handler();
    }
    HAL_NVIC_SetPriority(TIM2_IRQn, 2, 0);
    HAL_NVIC_EnableIRQ(TIM2_IRQn);
}

// 定时器中断回调
void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim)
{
    if (htim->Instance == TIM2) {
        MotorCtrl_Update(&motorCtrl1);
        MotorCtrl_Update(&motorCtrl2);
    }
}

// 按键处理
void Key_Process(void)
{
    uint32_t now = HAL_GetTick();
    switch (key_state) {
        case 0:
            if (joy_key == 0) { key_state = 1; key_press_time = now; }
            break;
        case 1:
            if (now - key_press_time >= KEY_DEBOUNCE_TIME) {
                if (joy_key == 0) key_state = 2;
                else key_state = 0;
            }
            break;
        case 2:
            if (joy_key == 1) { key_state = 3; key_release_time = now; }
            break;
        case 3:
            if (now - key_release_time >= KEY_DEBOUNCE_TIME) {
                if (joy_key == 1) { key_single_click = 1; key_state = 0; }
                else key_state = 2;
            }
            break;
        default: key_state = 0; break;
    }
}

// 所有电机停止
void Motor_All_Stop(void)
{
    Motor_Enable(&hmotor1);
    Motor_Enable(&hmotor2);
    motorCtrl1.is_running = 0;
    motorCtrl2.is_running = 0;
    m1_run = 0;
    m2_run = 0;
}

// OLED显示更新
void Update_OLED_Display(void)
{
    if (current_page == 0) {
        if (joy_key == 0) sprintf(oled_buf, "Joy Key: Pressed ");
        else sprintf(oled_buf, "Joy Key: Release ");
        OLED_ShowString(0, 0, (uint8_t*)oled_buf, 16);

        if(k230_data_valid == 0) sprintf(oled_buf, "X:----  Y:----   ");
        else sprintf(oled_buf, "X:%-4d Y:%-4d", target_x, target_y);
        OLED_ShowString(0, 2, (uint8_t*)oled_buf, 16);

        if(k230_data_valid == 0) sprintf(oled_buf, "W:----  H:----   ");
        else sprintf(oled_buf, "W:%-4d H:%-4d", target_w, target_h);
        OLED_ShowString(0, 4, (uint8_t*)oled_buf, 16);

        sprintf(oled_buf, "D1:%-3d D2:%-3d", motor1_delay_display, motor2_delay_display);
        OLED_ShowString(0, 6, (uint8_t*)oled_buf, 16);
    } else {
        MPU6050_Display(&mpu_data);
    }
}

// 系统时钟配置
void SystemClock_Config(void)
{
    RCC_OscInitTypeDef RCC_OscInitStruct = {0};
    RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};
    RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
    RCC_OscInitStruct.HSEState = RCC_HSE_ON;
    RCC_OscInitStruct.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
    RCC_OscInitStruct.HSIState = RCC_HSI_ON;
    RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
    RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
    RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL9;
    if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK) Error_Handler();
    RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                                |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
    RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
    RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
    RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
    RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;
    if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK) Error_Handler();
}

// 错误处理
void Error_Handler(void)
{
    __disable_irq();
    while (1) {}
}

#ifdef USE_FULL_ASSERT
void assert_failed(uint8_t *file, uint32_t line)
{
}
#endif /* USE_FULL_ASSERT */
