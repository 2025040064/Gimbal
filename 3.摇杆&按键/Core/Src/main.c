/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : 摇杆+按键测试
  ******************************************************************************
  */
/* USER CODE END Header */
#include "main.h"
#include "usart.h"
#include "gpio.h"
#include "oled.h"
#include "motor.h"
#include "adc.h"
#include "stdio.h"

void SystemClock_Config(void);

int main(void)
{
  HAL_Init();
  SystemClock_Config();
  MX_GPIO_Init();
  MX_USART1_UART_Init();
  
  // 初始化外设
  OLED_Init();
  OLED_Clear();
  Motor_Init();
  MX_ADC1_Init(); 
  
  char buf[20];
  uint16_t x, y;
  uint8_t current_page = 0;
  uint32_t last_key_time = 0;

  while (1)
  {
    // 读取摇杆和按键
    Joystick_Read(&x, &y);
    uint8_t key = Joystick_K_Read();

    // 按键切换页面（带200ms消抖）
    if(key == 0 && HAL_GetTick() - last_key_time > 200)
    {
      while(Joystick_K_Read() == 0); // 等待按键松开
      current_page = (current_page + 1) % 2;
      OLED_Clear();
      last_key_time = HAL_GetTick();
    }

    // 页面0：摇杆数据显示
    if(current_page == 0)
    {
      OLED_ShowString(0, 0, (uint8_t*)"Joystick Test", 16);
      // 摇杆数据一行显示：X:XX Y:XX K:OFF/ON
      sprintf(buf, "X:%2d Y:%2d K:%s", x, y, key?"OFF":"ON");
      OLED_ShowString(0, 2, (uint8_t*)buf, 16);
      OLED_ShowString(0, 4, (uint8_t*)"Press to switch", 16);
    }
    // 页面1：MPU6050预留页面
    else
    {
      OLED_ShowString(0, 0, (uint8_t*)"MPU6050 Page", 16);
      OLED_ShowString(0, 2, (uint8_t*)"Reserved", 16);
      OLED_ShowString(0, 4, (uint8_t*)"Press to back", 16);
    }

    HAL_Delay(50); // 20Hz刷新率
  }
}

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

void Error_Handler(void) 
{ 
	__disable_irq();
	while(1);

}
#ifdef USE_FULL_ASSERT
void assert_failed(uint8_t *file, uint32_t line) 
{

}
#endif
