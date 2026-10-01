#ifndef __MPU6050_H
#define __MPU6050_H

#include "stm32f1xx_hal.h"
#include "oled.h"
#include "math.h"

#define M_PI 3.14159265358979323846f
#define MPU6050_ADDR 0x68

#define GYRO_SENSITIVITY  131.0f    /* ¡À250¡ã/s */
#define ACC_SENSITIVITY   16384.0f  /* ¡À2g */

typedef struct {
    int16_t acc_x;
    int16_t acc_y;
    int16_t acc_z;
    int16_t gyro_x;
    int16_t gyro_y;
    int16_t gyro_z;
    float temp;
    float pitch;
    float roll;
    float yaw;
} MPU6050_Data_TypeDef;

void MPU6050_Init(void);
uint8_t MPU6050_ReadData(MPU6050_Data_TypeDef *data);
void MPU6050_Display(MPU6050_Data_TypeDef *data);

#endif
