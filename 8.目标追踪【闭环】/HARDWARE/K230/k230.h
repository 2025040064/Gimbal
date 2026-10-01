#ifndef __K230_H__
#define __K230_H__

#include "main.h"

// 对外暴露的解析结果
extern int16_t target_x;
extern int16_t target_y;
extern int16_t target_w;
extern int16_t target_h;

/* 屏幕尺寸，用于计算图像中心 */
extern int16_t screen_w;
extern int16_t screen_h;

// 对外暴露的初始化和处理函数
void K230_Init(void);
void K230_Process(void);

#endif /* __K230_H__ */
