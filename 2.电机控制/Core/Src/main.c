/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : 电机测试
  ******************************************************************************
  */
/* USER CODE END Header */
#include "main.h"
#include "usart.h"
#include "gpio.h"
#include "motor.h"
#include "oled.h"


// 声明
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
  
  // 显示标题
  OLED_ShowString(0, 0, (uint8_t*)"KFJ Motor Test", 16);
  OLED_ShowString(0, 2, (uint8_t*)"Running...", 16);

  while (1)
  {
    // 电机1正转1圈
    OLED_ShowString(0, 4, (uint8_t*)"M1 Forward 1R ", 16);
    Motor_Run(1, 1.0f, 0, DEFAULT_SPEED);
    HAL_Delay(500);
    
    // 电机1反转1圈
    OLED_ShowString(0, 4, (uint8_t*)"M1 Backward 1R", 16);
    Motor_Run(1, 1.0f, 1, DEFAULT_SPEED);
    HAL_Delay(500);
    
    // 电机2正转0.5圈
    OLED_ShowString(0, 4, (uint8_t*)"M2 Forward 0.5R", 16);
    Motor_Run(2, 0.5f, 0, DEFAULT_SPEED);
    HAL_Delay(500);
    
    // 电机2反转0.5圈
    OLED_ShowString(0, 4, (uint8_t*)"M2 Backward 0.5R", 16);
    Motor_Run(2, 0.5f, 1, DEFAULT_SPEED);
    HAL_Delay(1000);
    
    // LED状态指示
    HAL_GPIO_TogglePin(LED_GPIO_Port, LED_Pin);
  }
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL9;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  __disable_irq();
  while (1)
  {
  }
}

#ifdef  USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
}
#endif /* USE_FULL_ASSERT */
