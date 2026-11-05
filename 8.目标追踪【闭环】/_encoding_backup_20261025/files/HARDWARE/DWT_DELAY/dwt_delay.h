#ifndef __DWT_DELAY_H
#define __DWT_DELAY_H

#include "stm32f1xx_hal.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief 初始化DWT内核计数器（微秒级高精度计时）
 * @note 72MHz系统时钟下，精度约14ns，溢出时间约59.6秒
 */
static inline void DWT_Init(void) {
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}

/**
 * @brief 获取当前系统运行的微秒数
 * @return 自启动以来的微秒计数
 */
static inline uint32_t DWT_GetTickUs(void) {
    return DWT->CYCCNT / (SystemCoreClock / 1000000);
}

#ifdef __cplusplus
}
#endif

#endif /* __DWT_DELAY_H */
