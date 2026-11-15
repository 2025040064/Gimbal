#include "adc.h"

#define JOY_FILTER_WIN 4

static uint16_t joy_x_buf[JOY_FILTER_WIN] = {50,50,50,50};
static uint16_t joy_y_buf[JOY_FILTER_WIN] = {50,50,50,50};
static uint8_t joy_buf_idx = 0;

static uint16_t FilterJoy(uint16_t new_val, uint16_t *buf) {
    buf[joy_buf_idx] = new_val;
    uint32_t sum = 0;
    for (int i = 0; i < JOY_FILTER_WIN; i++) sum += buf[i];
    return (uint16_t)(sum / JOY_FILTER_WIN);
}

void MX_ADC1_Init(void)
{
    __HAL_RCC_ADC1_CLK_ENABLE();
    __HAL_RCC_GPIOA_CLK_ENABLE();

    GPIO_InitTypeDef GPIO_InitStruct = {0};
    GPIO_InitStruct.Pin = GPIO_PIN_4 | GPIO_PIN_5;
    GPIO_InitStruct.Mode = GPIO_MODE_ANALOG;
    HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

    GPIO_InitStruct.Pin = GPIO_PIN_7;
    GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
    GPIO_InitStruct.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

    RCC->APB2RSTR |= RCC_APB2RSTR_ADC1RST;
    RCC->APB2RSTR &= ~RCC_APB2RSTR_ADC1RST;

    ADC1->CR1 = 0;
    ADC1->CR2 = ADC_CR2_ADON;
    HAL_Delay(1);

    ADC1->CR2 |= ADC_CR2_CAL;
    while (ADC1->CR2 & ADC_CR2_CAL);

    ADC1->SMPR2 = 0x0000000F;
}

static uint16_t ADC_ReadRaw(uint8_t ch)
{
    ADC1->SQR3 = ch;
    ADC1->CR2 |= ADC_CR2_ADON;
    while (!(ADC1->SR & ADC_SR_EOC));
    return (uint16_t)ADC1->DR;
}

static uint8_t ADC_ConvertTo100(uint16_t val)
{
    uint32_t res = (uint32_t)val * 100 / 4095;
    if (res > 100) res = 100;
    return (uint8_t)res;
}

uint8_t Joystick_K_Read(void)
{
    return HAL_GPIO_ReadPin(GPIOA, GPIO_PIN_7);
}

void Joystick_Read(uint16_t *x, uint16_t *y)
{
    uint16_t raw_x = ADC_ReadRaw(4);
    uint16_t raw_y = ADC_ReadRaw(5);
    *x = ADC_ConvertTo100(raw_x);
    *y = ADC_ConvertTo100(raw_y);

    *x = FilterJoy(*x, joy_x_buf);
    *y = FilterJoy(*y, joy_y_buf);
    joy_buf_idx = (joy_buf_idx + 1) % JOY_FILTER_WIN;
}
