#include "main.h"
#include "usart.h"
#include "gpio.h"
#include "oled.h"
#include "adc.h"
#include "stdio.h"
#include "motor.h"
#include "mpu6050.h"


#include "k230.h"//【包含K230头文件】
extern uint8_t k230_data_valid;

void SystemClock_Config(void);

int main(void)
{
  HAL_Init();
  SystemClock_Config();
  MX_GPIO_Init();
  MX_USART1_UART_Init();

  OLED_Init();
  OLED_Clear();
  MX_ADC1_Init();
  Motor_Init();
  MPU6050_Init();

  K230_Init();  //【初始化K230】

  char buf[24];
  uint16_t x, y;
  uint8_t current_page = 0;
  uint32_t last_key_time = 0;
  MPU6050_Data_TypeDef mpu_data;

  while (1)
  {
    
    K230_Process();//【循环处理K230数据】

    Joystick_Read(&x, &y);
    uint8_t key = Joystick_K_Read();

    if(key == 0 && HAL_GetTick() - last_key_time > 200)
    {
      while(Joystick_K_Read() == 0);
      current_page = (current_page + 1) % 3;//【3页面切换】
      OLED_Clear();
      last_key_time = HAL_GetTick();
    }

    // 页面0：摇杆
    if(current_page == 0)
    {
      OLED_ShowString(0, 0, (uint8_t*)"Joystick Motor", 16);
      sprintf(buf, "X:%2d Y:%2d K:%s", x, y, key?"OFF":"ON");
      OLED_ShowString(0, 2, (uint8_t*)buf, 16);
      OLED_ShowString(0, 4, (uint8_t*)"Page:1/3", 16);//【页面切换】
	
	  // 死区30-70：中间位置停止，防止摇杆漂移
      // X轴控制电机1，Y轴控制电机2，固定速度DEFAULT_SPEED
      // 每次转0.01圈≈1.8度，控制平滑无卡顿
      if(x > 70)      Motor_Run(1, 0.01f, 0, DEFAULT_SPEED);
      else if(x < 30) Motor_Run(1, 0.01f, 1, DEFAULT_SPEED);
      if(y > 70)      Motor_Run(2, 0.01f, 0, DEFAULT_SPEED);
      else if(y < 30) Motor_Run(2, 0.01f, 1, DEFAULT_SPEED);
    }

    // 页面1：MPU6050
    else if(current_page == 1)
    {
      MPU6050_ReadData(&mpu_data);
      MPU6050_Display(&mpu_data);
      OLED_ShowString(0,6,(uint8_t*)"Page:2/3   MPU6050",16);//【页面切换】
    }

    // 【页面2 - K230显示】
    else if(current_page == 2)
    {
      
      if(k230_data_valid)
        sprintf(buf,"Status: K230 Valid");
      else
        sprintf(buf,"Status: K230 No Data");
      OLED_ShowString(0,0,(uint8_t*)buf,16);

      sprintf(buf,"X:%4d  Y:%4d",target_x,target_y);
      OLED_ShowString(0,2,(uint8_t*)buf,16);
      sprintf(buf,"W:%4d  H:%4d",target_w,target_h);
      OLED_ShowString(0,4,(uint8_t*)buf,16);
      OLED_ShowString(0,6,(uint8_t*)"Page:3/3     K230",16);//【页面切换】
    }

    HAL_Delay(50);
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
