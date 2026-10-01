#include "motor.h"

void Motor_Init(void)
{
    GPIO_InitTypeDef gpio = {0};
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();
    
    gpio.Mode = GPIO_MODE_OUTPUT_PP;
    gpio.Speed = GPIO_SPEED_FREQ_HIGH;
    
    // 初始化PA0-PA3(电机1全部引脚+电机2使能)
    gpio.Pin = GPIO_PIN_0 | GPIO_PIN_1 | GPIO_PIN_2 | GPIO_PIN_3;
    HAL_GPIO_Init(GPIOA, &gpio);
    
    // 初始化PB0-PB1(电机2脉冲+方向)
    gpio.Pin = GPIO_PIN_0 | GPIO_PIN_1;
    HAL_GPIO_Init(GPIOB, &gpio);
    
    // 默认使能电机(低电平有效)
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_2, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_3, GPIO_PIN_RESET);
}

void Motor_Run(uint8_t motor, float rev, uint8_t dir, uint16_t delay_us)
{
    uint32_t pulses = (uint32_t)(rev * PULSE_PER_REV + 0.5f);
    if(pulses == 0) return;
    
    // 设置方向
    if(motor == 1)
        HAL_GPIO_WritePin(GPIOA, GPIO_PIN_1, (GPIO_PinState)dir);
    else
        HAL_GPIO_WritePin(GPIOB, GPIO_PIN_1, (GPIO_PinState)dir);
    
    for(volatile int i=0; i<10; i++) __NOP();
    
    // 循环发送脉冲
    for(uint32_t i=0; i<pulses; i++)
    {
        // 输出高电平
        if(motor == 1)
            HAL_GPIO_WritePin(GPIOA, GPIO_PIN_0, GPIO_PIN_SET);
        else
            HAL_GPIO_WritePin(GPIOB, GPIO_PIN_0, GPIO_PIN_SET);
        
        for(volatile int j=0; j<10; j++) __NOP();
        
        // 输出低电平(产生下降沿)
        if(motor == 1)
            HAL_GPIO_WritePin(GPIOA, GPIO_PIN_0, GPIO_PIN_RESET);
        else
            HAL_GPIO_WritePin(GPIOB, GPIO_PIN_0, GPIO_PIN_RESET);
        
        // 脉冲间隔延时
        uint32_t delay = delay_us * 12;
        for(volatile int j=0; j<delay; j++) __NOP();
    }
}

