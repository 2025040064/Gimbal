#include "motor.h"

Motor_HandleTypeDef hmotor1 = {
    .PUL_GPIO_Port = GPIOA, .PUL_Pin = GPIO_PIN_0,
    .DIR_GPIO_Port = GPIOA, .DIR_Pin = GPIO_PIN_1,
    .ENA_GPIO_Port = GPIOA, .ENA_Pin = GPIO_PIN_2
};

Motor_HandleTypeDef hmotor2 = {
    .PUL_GPIO_Port = GPIOB, .PUL_Pin = GPIO_PIN_0,
    .DIR_GPIO_Port = GPIOB, .DIR_Pin = GPIO_PIN_1,
    .ENA_GPIO_Port = GPIOA, .ENA_Pin = GPIO_PIN_3
};

void Motor_GPIO_Init(Motor_HandleTypeDef *hmotor)
{
    GPIO_InitTypeDef GPIO_InitStruct = {0};
    if(hmotor->PUL_GPIO_Port == GPIOA)
        __HAL_RCC_GPIOA_CLK_ENABLE();
    else if(hmotor->PUL_GPIO_Port == GPIOB)
        __HAL_RCC_GPIOB_CLK_ENABLE();

    GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;

    GPIO_InitStruct.Pin = hmotor->PUL_Pin;
    HAL_GPIO_Init(hmotor->PUL_GPIO_Port, &GPIO_InitStruct);
    GPIO_InitStruct.Pin = hmotor->DIR_Pin;
    HAL_GPIO_Init(hmotor->DIR_GPIO_Port, &GPIO_InitStruct);
    GPIO_InitStruct.Pin = hmotor->ENA_Pin;
    HAL_GPIO_Init(hmotor->ENA_GPIO_Port, &GPIO_InitStruct);

    HAL_GPIO_WritePin(hmotor->ENA_GPIO_Port, hmotor->ENA_Pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(hmotor->PUL_GPIO_Port, hmotor->PUL_Pin, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(hmotor->DIR_GPIO_Port, hmotor->DIR_Pin, GPIO_PIN_RESET);
}

void Motor_Enable(Motor_HandleTypeDef *hmotor)
{
    HAL_GPIO_WritePin(hmotor->ENA_GPIO_Port, hmotor->ENA_Pin, GPIO_PIN_RESET);
}

void Motor_Disable(Motor_HandleTypeDef *hmotor)
{
    HAL_GPIO_WritePin(hmotor->ENA_GPIO_Port, hmotor->ENA_Pin, GPIO_PIN_SET);
}

void Motor_SetDir(Motor_HandleTypeDef *hmotor, uint8_t dir)
{
    HAL_GPIO_WritePin(hmotor->DIR_GPIO_Port, hmotor->DIR_Pin,
                      (dir == CW) ? GPIO_PIN_RESET : GPIO_PIN_SET);
    for (volatile uint32_t i = 0; i < 140; i++) {
        __NOP();
    }
}

void Motor_SinglePulse(Motor_HandleTypeDef *hmotor)
{
    HAL_GPIO_WritePin(hmotor->PUL_GPIO_Port, hmotor->PUL_Pin, GPIO_PIN_SET);
    for (volatile uint32_t i = 0; i < 140; i++) {
        __NOP();
    }
    HAL_GPIO_WritePin(hmotor->PUL_GPIO_Port, hmotor->PUL_Pin, GPIO_PIN_RESET);
    for (volatile uint32_t i = 0; i < 70; i++) {
        __NOP();
    }
}


void MotorCtrl_Init(MotorCtrl_TypeDef *mc, Motor_HandleTypeDef *hw)
{
    mc->hw = hw;
    mc->dir = CW;
    mc->target_steps = 0;
    mc->current_step = 0;
    mc->home_steps = 0;
    mc->next_pulse_tick = 0;
    // 可将7000减小至6000，增大初始速度
    mc->pulse_delay = 7000;
    mc->target_delay = 7000;
    mc->accel_rate = 0;
    mc->last_accel_time = 0; // 初始化独立时间戳
    mc->is_running = 0;
    Motor_Enable(hw);
}

void MotorCtrl_SetHome(MotorCtrl_TypeDef *mc)
{
    mc->home_steps = mc->current_step;
}

void MotorCtrl_GoHome(MotorCtrl_TypeDef *mc, uint16_t delay_us)
{
    int32_t steps_to_home = mc->home_steps - mc->current_step;
    if (steps_to_home == 0) {
        mc->is_running = 0;
        return;
    }
    MotorCtrl_SetTarget(mc, (float)steps_to_home / PULSE_PER_CIRCLE, delay_us,
                       (steps_to_home > 0) ? CW : CCW);
}


void MotorCtrl_SetTarget(MotorCtrl_TypeDef *mc, float circles, uint16_t delay_us, uint8_t dir)
{
    int32_t steps = (int32_t)(circles * PULSE_PER_CIRCLE);
    mc->target_steps = mc->current_step + steps;
    mc->target_delay = (delay_us > 500) ? delay_us : 500;
    
    
    if (mc->pulse_delay > mc->target_delay) {
        mc->accel_rate = -2; // 每毫秒加速2us
    } else if (mc->pulse_delay < mc->target_delay) {
        mc->accel_rate = 2;  // 每毫秒减速2us
    } else {
        mc->accel_rate = 0;
    }
    
    if (steps > 0) mc->dir = CW;
    else if (steps < 0) mc->dir = CCW;
    else mc->dir = dir;
    
    Motor_SetDir(mc->hw, mc->dir);
    Motor_Enable(mc->hw);
    mc->next_pulse_tick = DWT_GetTickUs();
    mc->is_running = 1;
}


void MotorCtrl_SetSpeed(MotorCtrl_TypeDef *mc, uint16_t delay_us, uint8_t dir)
{
    if (!mc->is_running) {
        int32_t steps = (dir == CW) ? 999999 : -999999;
        MotorCtrl_SetTarget(mc, (float)steps / PULSE_PER_CIRCLE, delay_us, dir);
    } else {
        if (mc->dir != dir) {
            mc->is_running = 0;
            mc->target_delay = 8000; 
            mc->accel_rate = 2;
            return;
        }
        
        mc->target_delay = (delay_us > 500) ? delay_us : 500;
        

        if (mc->pulse_delay > mc->target_delay) {
            mc->accel_rate = -2;
        } else if (mc->pulse_delay < mc->target_delay) {
            mc->accel_rate = 2;
        } else {
            mc->accel_rate = 0;
        }
        
        mc->target_steps = (dir == CW) ? 999999 : -999999;
    }
}

void MotorCtrl_Update(MotorCtrl_TypeDef *mc)
{
    uint32_t now = DWT_GetTickUs();
    
    // 每1ms调整一次速度（恒定加速度）
    if (now - mc->last_accel_time >= 1000) {
        mc->last_accel_time = now;
        
        if (mc->accel_rate != 0) {
            mc->pulse_delay += mc->accel_rate;
            
            if ((mc->accel_rate < 0 && mc->pulse_delay <= mc->target_delay) ||
                (mc->accel_rate > 0 && mc->pulse_delay >= mc->target_delay))
            {
                mc->pulse_delay = mc->target_delay;
                mc->accel_rate = 0;
            }
            
            if (mc->pulse_delay < 500) mc->pulse_delay = 500;
            if (mc->pulse_delay > 8000) mc->pulse_delay = 8000; 
        }
    }
    
    if (!mc->is_running) {
        if (mc->pulse_delay < 8000) {
            mc->accel_rate = 2; // 
        } else {
            mc->accel_rate = 0;
        }
        return;
    }

    if ((mc->target_steps >= 0 && mc->current_step >= mc->target_steps) ||
        (mc->target_steps < 0  && mc->current_step <= mc->target_steps))
    {
        mc->is_running = 0;
        return;
    }
    
    if ((int32_t)(now - mc->next_pulse_tick) > (int32_t)(mc->pulse_delay * 10)) {
        mc->next_pulse_tick = now;
    }

    if ((int32_t)(now - mc->next_pulse_tick) >= 0) {
        Motor_SinglePulse(mc->hw);
        mc->current_step += (mc->dir == CW) ? 1 : -1;
        mc->next_pulse_tick += mc->pulse_delay;
    }
}

float MotorCtrl_GetCircles(MotorCtrl_TypeDef *mc)
{
    return (float)mc->current_step / PULSE_PER_CIRCLE;
}

uint8_t MotorCtrl_IsRunning(MotorCtrl_TypeDef *mc)
{
    // 停止判断阈值
    return mc->is_running || (mc->pulse_delay < 8000);
}
