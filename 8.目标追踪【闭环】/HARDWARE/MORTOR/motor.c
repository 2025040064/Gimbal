#include "motor.h"

Motor_HandleTypeDef hmotor1 = {GPIOA, GPIO_PIN_0, GPIOA, GPIO_PIN_1, GPIOA, GPIO_PIN_2};
Motor_HandleTypeDef hmotor2 = {GPIOB, GPIO_PIN_0, GPIOB, GPIO_PIN_1, GPIOA, GPIO_PIN_3};

static void Output(GPIO_TypeDef *port, uint16_t pin, GPIO_PinState level)
{
    GPIO_InitTypeDef io = {0};
    HAL_GPIO_WritePin(port, pin, level);
    io.Pin = pin;
    io.Mode = GPIO_MODE_OUTPUT_PP;
    io.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(port, &io);
}

void MotorCtrl_Init(MotorCtrl_TypeDef *motor, Motor_HandleTypeDef *hw, uint8_t positive_cw)
{
    motor->hw = hw;
    motor->positive_cw = positive_cw;
    Output(hw->ENA_GPIO_Port, hw->ENA_Pin, GPIO_PIN_RESET);
    Output(hw->PUL_GPIO_Port, hw->PUL_Pin, GPIO_PIN_RESET);
    Output(hw->DIR_GPIO_Port, hw->DIR_Pin, GPIO_PIN_RESET);
}

void MotorCtrl_Move(MotorCtrl_TypeDef *motor, int32_t goal, uint16_t period_us)
{
    uint32_t irq = __get_PRIMASK();
    __disable_irq();
    motor->goal = goal;
    motor->period_ticks = (period_us + 49u) / 50u;
    if (motor->period_ticks < 10u) motor->period_ticks = 10u;
    __set_PRIMASK(irq);
}

void MotorCtrl_Stop(MotorCtrl_TypeDef *motor)
{
    uint32_t irq = __get_PRIMASK();
    __disable_irq();
    motor->goal = motor->position;
    motor->direction = 0;
    motor->remaining_ticks = 0;
    __set_PRIMASK(irq);
}

void MotorCtrl_Update(MotorCtrl_TypeDef *motor)
{
    Motor_HandleTypeDef *hw = motor->hw;
    int8_t direction;
    uint8_t cw;
    if (motor->position == motor->goal) {
        motor->direction = 0;
        motor->remaining_ticks = 0;
        return;
    }
    direction = motor->goal > motor->position ? 1 : -1;
    if (direction != motor->direction) {
        cw = (direction > 0) == motor->positive_cw;
        HAL_GPIO_WritePin(hw->DIR_GPIO_Port, hw->DIR_Pin, cw ? GPIO_PIN_RESET : GPIO_PIN_SET);
        motor->direction = direction;
        motor->remaining_ticks = motor->period_ticks;
        return;
    }
    if (motor->remaining_ticks && --motor->remaining_ticks) return;
    HAL_GPIO_WritePin(hw->PUL_GPIO_Port, hw->PUL_Pin, GPIO_PIN_SET);
    for (volatile uint32_t i = 0; i < 140; ++i) __NOP();
    HAL_GPIO_WritePin(hw->PUL_GPIO_Port, hw->PUL_Pin, GPIO_PIN_RESET);
    motor->position += direction;
    motor->remaining_ticks = motor->period_ticks;
}
