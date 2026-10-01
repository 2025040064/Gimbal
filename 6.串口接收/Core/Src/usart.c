/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file    usart.c
  * @brief   This file provides code for the configuration
  *          of the USART instances.
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2023 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "usart.h"

/* USER CODE BEGIN 0 */
typedef struct __FILE FILE;
/* USER CODE END 0 */

UART_HandleTypeDef huart1;

UART_HandleTypeDef huart3;// 【定义USART3句柄】

/* USART1 init function */

void MX_USART1_UART_Init(void)
{

  /* USER CODE BEGIN USART1_Init 0 */

  /* USER CODE END USART1_Init 0 */

  /* USER CODE BEGIN USART1_Init 1 */

  /* USER CODE END USART1_Init 1 */
  huart1.Instance = USART1;
  huart1.Init.BaudRate = 115200;
  huart1.Init.WordLength = UART_WORDLENGTH_8B;
  huart1.Init.StopBits = UART_STOPBITS_1;
  huart1.Init.Parity = UART_PARITY_NONE;
  huart1.Init.Mode = UART_MODE_TX_RX;
  huart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart1.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart1) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN USART1_Init 2 */

  /* USER CODE END USART1_Init 2 */

}

// 【USART3初始化函数】
void MX_USART3_UART_Init(void)
{
  huart3.Instance = USART3;               // 使用USART3外设
  huart3.Init.BaudRate = 115200;          // 波特率115200（必须和K230一致）
  huart3.Init.WordLength = UART_WORDLENGTH_8B; // 8位数据位
  huart3.Init.StopBits = UART_STOPBITS_1; // 1位停止位
  huart3.Init.Parity = UART_PARITY_NONE;  // 无校验位
  huart3.Init.Mode = UART_MODE_TX_RX;     // 同时开启发送和接收
  huart3.Init.HwFlowCtl = UART_HWCONTROL_NONE; // 无硬件流控
  huart3.Init.OverSampling = UART_OVERSAMPLING_16; // 16倍过采样（提高抗干扰）

  if (HAL_UART_Init(&huart3) != HAL_OK) Error_Handler();

  //开启USART3中断
  HAL_NVIC_EnableIRQ(USART3_IRQn);
  HAL_NVIC_SetPriority(USART3_IRQn, 5, 0);
}


void HAL_UART_MspInit(UART_HandleTypeDef* uartHandle)
{

  GPIO_InitTypeDef GPIO_InitStruct = {0};
  if(uartHandle->Instance==USART1)
  {
  /* USER CODE BEGIN USART1_MspInit 0 */

  /* USER CODE END USART1_MspInit 0 */
    /* USART1 clock enable */
    __HAL_RCC_USART1_CLK_ENABLE();

    __HAL_RCC_GPIOA_CLK_ENABLE();
    /**USART1 GPIO Configuration
    PA9     ------> USART1_TX
    PA10     ------> USART1_RX
    */
    GPIO_InitStruct.Pin = GPIO_PIN_9;
    GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

    GPIO_InitStruct.Pin = GPIO_PIN_10;
    GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  /* USER CODE BEGIN USART1_MspInit 1 */

  /* USER CODE END USART1_MspInit 1 */
  }
  
  //【USART3 GPIO配置】
	else if(uartHandle->Instance==USART3)
	{
	  __HAL_RCC_USART3_CLK_ENABLE(); // 开启USART3时钟
	  __HAL_RCC_GPIOB_CLK_ENABLE();  // 开启GPIOB时钟

	  // PB10 = TX（发送引脚）
	  GPIO_InitStruct.Pin = GPIO_PIN_10;
	  GPIO_InitStruct.Mode = GPIO_MODE_AF_PP; // 复用推挽输出
	  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
	  HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

	  // PB11 = RX（接收引脚）
	  GPIO_InitStruct.Pin = GPIO_PIN_11;
	  GPIO_InitStruct.Mode = GPIO_MODE_INPUT; // 输入模式
	  GPIO_InitStruct.Pull = GPIO_PULLUP;     // 【关键】开启内部上拉
	  HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);
	}
  
}

void HAL_UART_MspDeInit(UART_HandleTypeDef* uartHandle)
{

  if(uartHandle->Instance==USART1)
  {
  /* USER CODE BEGIN USART1_MspDeInit 0 */

  /* USER CODE END USART1_MspDeInit 0 */
    /* Peripheral clock disable */
    __HAL_RCC_USART1_CLK_DISABLE();

    /**USART1 GPIO Configuration
    PA9     ------> USART1_TX
    PA10     ------> USART1_RX
    */
    HAL_GPIO_DeInit(GPIOA, GPIO_PIN_9|GPIO_PIN_10);

  /* USER CODE BEGIN USART1_MspDeInit 1 */

  /* USER CODE END USART1_MspDeInit 1 */
  }

}

/* USER CODE BEGIN 1 */
/**
* @brief 重定向printf (重定向fputc)，
					使用时候记得勾选上魔法棒->Target->UseMicro LIB 
					可能需要在C文件加typedef struct __FILE FILE;
					包含这个文件#include "stdio.h"
* @param 
* @return 
*/
int fputc(int ch,FILE *stream)
{
	HAL_UART_Transmit(&huart1,( uint8_t *)&ch,1,0xFFFF);
	return ch;
}
/* USER CODE END 1 */
