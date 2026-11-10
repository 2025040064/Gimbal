#ifndef APP_H
#define APP_H

#include "main.h"

extern TIM_HandleTypeDef htim2;
void App_Init(void);
void App_Update(void);
void SystemClock_Config(void);

#endif
