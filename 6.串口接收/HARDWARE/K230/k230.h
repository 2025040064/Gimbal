#ifndef __K230_H__
#define __K230_H__

#include "main.h"



// 目标检测结果（像素坐标）
extern int16_t target_x;    // 目标中心点X坐标
extern int16_t target_y;    // 目标中心点Y坐标
extern int16_t target_w;    // 目标宽度
extern int16_t target_h;    // 目标高度

// 摄像头屏幕分辨率
extern int16_t screen_w;    // 图像宽度（K230输出320）
extern int16_t screen_h;    // 图像高度（K230输出240）

// 数据有效标志
// =1：最近500ms内收到有效数据
// =0：超过500ms没收到数据，显示"No Data"
extern uint8_t k230_data_valid;


/**
 * @brief  K230模块初始化
 * @note   必须在main函数里调用一次，会自动初始化USART3并启动中断接收
 */
void K230_Init(void);

/**
 * @brief  K230数据处理函数
 * @note   必须在主循环while(1)里**每秒调用至少2次**，负责解析帧和超时检测
 */
void K230_Process(void);

#endif // __K230_H__
