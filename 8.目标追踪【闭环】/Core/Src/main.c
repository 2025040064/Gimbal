#include "app.h"

int main(void)
{
    HAL_Init();
    SystemClock_Config();
    App_Init();
    while (1) App_Update();
}
