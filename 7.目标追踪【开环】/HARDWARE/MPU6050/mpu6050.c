#include "mpu6050.h"
#include "stdio.h"

#define SCL_PIN GPIO_PIN_6
#define SDA_PIN GPIO_PIN_7
#define I2C_PORT GPIOB

#define COMPLEMENTARY_FILTER 0.98f
#define DT 0.1f

static float pitch = 0.0f;
static float roll = 0.0f;
static float yaw = 0.0f;

static void I2C_Delay(void) {
    for (volatile uint32_t i = 0; i < 10; i++) {
        __NOP();
    }
}

static void I2C_GPIO_Init(void) {
    GPIO_InitTypeDef GPIO_InitStruct = {0};
    __HAL_RCC_GPIOB_CLK_ENABLE();
    GPIO_InitStruct.Pin = SCL_PIN | SDA_PIN;
    GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_OD;
    GPIO_InitStruct.Pull = GPIO_PULLUP;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(I2C_PORT, &GPIO_InitStruct);
    HAL_GPIO_WritePin(I2C_PORT, SCL_PIN, GPIO_PIN_SET);
    HAL_GPIO_WritePin(I2C_PORT, SDA_PIN, GPIO_PIN_SET);
}

static void I2C_Start(void) {
    HAL_GPIO_WritePin(I2C_PORT, SDA_PIN, GPIO_PIN_SET);
    HAL_GPIO_WritePin(I2C_PORT, SCL_PIN, GPIO_PIN_SET);
    I2C_Delay();
    HAL_GPIO_WritePin(I2C_PORT, SDA_PIN, GPIO_PIN_RESET);
    I2C_Delay();
    HAL_GPIO_WritePin(I2C_PORT, SCL_PIN, GPIO_PIN_RESET);
    I2C_Delay();
}

static void I2C_Stop(void) {
    HAL_GPIO_WritePin(I2C_PORT, SDA_PIN, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(I2C_PORT, SCL_PIN, GPIO_PIN_SET);
    I2C_Delay();
    HAL_GPIO_WritePin(I2C_PORT, SDA_PIN, GPIO_PIN_SET);
    I2C_Delay();
}

static uint8_t I2C_SendByte(uint8_t byte) {
    for (uint8_t i = 0; i < 8; i++) {
        if (byte & 0x80) HAL_GPIO_WritePin(I2C_PORT, SDA_PIN, GPIO_PIN_SET);
        else HAL_GPIO_WritePin(I2C_PORT, SDA_PIN, GPIO_PIN_RESET);
        I2C_Delay();
        HAL_GPIO_WritePin(I2C_PORT, SCL_PIN, GPIO_PIN_SET);
        I2C_Delay();
        HAL_GPIO_WritePin(I2C_PORT, SCL_PIN, GPIO_PIN_RESET);
        byte <<= 1;
    }
    HAL_GPIO_WritePin(I2C_PORT, SDA_PIN, GPIO_PIN_SET);
    I2C_Delay();
    HAL_GPIO_WritePin(I2C_PORT, SCL_PIN, GPIO_PIN_SET);
    I2C_Delay();
    uint8_t ack = HAL_GPIO_ReadPin(I2C_PORT, SDA_PIN);
    HAL_GPIO_WritePin(I2C_PORT, SCL_PIN, GPIO_PIN_RESET);
    return ack;
}

static uint8_t I2C_ReadByte(uint8_t ack) {
    uint8_t byte = 0;
    HAL_GPIO_WritePin(I2C_PORT, SDA_PIN, GPIO_PIN_SET);
    for (uint8_t i = 0; i < 8; i++) {
        byte <<= 1;
        HAL_GPIO_WritePin(I2C_PORT, SCL_PIN, GPIO_PIN_SET);
        I2C_Delay();
        if (HAL_GPIO_ReadPin(I2C_PORT, SDA_PIN)) byte |= 0x01;
        HAL_GPIO_WritePin(I2C_PORT, SCL_PIN, GPIO_PIN_RESET);
        I2C_Delay();
    }
    if (ack) HAL_GPIO_WritePin(I2C_PORT, SDA_PIN, GPIO_PIN_RESET);
    else HAL_GPIO_WritePin(I2C_PORT, SDA_PIN, GPIO_PIN_SET);
    I2C_Delay();
    HAL_GPIO_WritePin(I2C_PORT, SCL_PIN, GPIO_PIN_SET);
    I2C_Delay();
    HAL_GPIO_WritePin(I2C_PORT, SCL_PIN, GPIO_PIN_RESET);
    return byte;
}

static uint8_t MPU6050_WriteReg(uint8_t reg, uint8_t data) {
    I2C_Start();
    if (I2C_SendByte(MPU6050_ADDR << 1)) { I2C_Stop(); return 1; }
    if (I2C_SendByte(reg)) { I2C_Stop(); return 1; }
    if (I2C_SendByte(data)) { I2C_Stop(); return 1; }
    I2C_Stop();
    return 0;
}

static uint8_t MPU6050_ReadReg(uint8_t reg, uint8_t *data, uint8_t len) {
    I2C_Start();
    if (I2C_SendByte(MPU6050_ADDR << 1)) { I2C_Stop(); return 1; }
    if (I2C_SendByte(reg)) { I2C_Stop(); return 1; }
    I2C_Start();
    if (I2C_SendByte((MPU6050_ADDR << 1) | 0x01)) { I2C_Stop(); return 1; }
    for (uint8_t i = 0; i < len; i++) {
        data[i] = I2C_ReadByte(i < len - 1);
    }
    I2C_Stop();
    return 0;
}

static void MPU6050_CalculateAngle(MPU6050_Data_TypeDef *data) {
    float ax = (float)data->acc_x / ACC_SENSITIVITY;
    float ay = (float)data->acc_y / ACC_SENSITIVITY;
    float az = (float)data->acc_z / ACC_SENSITIVITY;
    float gx = (float)data->gyro_x / GYRO_SENSITIVITY;
    float gy = (float)data->gyro_y / GYRO_SENSITIVITY;
    float gz = (float)data->gyro_z / GYRO_SENSITIVITY;
    float pitch_acc = atan2(ay, sqrt(ax*ax + az*az)) * 180.0f / M_PI;
    float roll_acc = atan2(-ax, az) * 180.0f / M_PI;
    pitch += gy * DT;
    roll += gx * DT;
    yaw += gz * DT;
    pitch = COMPLEMENTARY_FILTER * pitch + (1.0f - COMPLEMENTARY_FILTER) * pitch_acc;
    roll = COMPLEMENTARY_FILTER * roll + (1.0f - COMPLEMENTARY_FILTER) * roll_acc;
    if (pitch > 90.0f) pitch = 90.0f;
    if (pitch < -90.0f) pitch = -90.0f;
    if (roll > 180.0f) roll -= 360.0f;
    if (roll < -180.0f) roll += 360.0f;
    if (yaw > 180.0f) yaw -= 360.0f;
    if (yaw < -180.0f) yaw += 360.0f;
    data->pitch = pitch;
    data->roll = roll;
    data->yaw = yaw;
}

void MPU6050_Init(void) {
    I2C_GPIO_Init();
    HAL_Delay(100);
    MPU6050_WriteReg(0x6B, 0x80);
    HAL_Delay(100);
    MPU6050_WriteReg(0x6B, 0x00);
    MPU6050_WriteReg(0x1B, 0x00);
    MPU6050_WriteReg(0x1C, 0x00);
    MPU6050_WriteReg(0x1A, 0x03);
    pitch = 0.0f;
    roll = 0.0f;
    yaw = 0.0f;
    printf("MPU6050陀螺仪初始化完成\r\n");
}

uint8_t MPU6050_ReadData(MPU6050_Data_TypeDef *data) {
    uint8_t buf[14];
    if (MPU6050_ReadReg(0x3B, buf, 14)) return 1;
    data->acc_x = (int16_t)((buf[0] << 8) | buf[1]);
    data->acc_y = (int16_t)((buf[2] << 8) | buf[3]);
    data->acc_z = (int16_t)((buf[4] << 8) | buf[5]);
    data->temp = ((int16_t)((buf[6] << 8) | buf[7])) / 340.0f + 36.53f;
    data->gyro_x = (int16_t)((buf[8] << 8) | buf[9]);
    data->gyro_y = (int16_t)((buf[10] << 8) | buf[11]);
    data->gyro_z = (int16_t)((buf[12] << 8) | buf[13]);
    MPU6050_CalculateAngle(data);
    return 0;
}

void MPU6050_Display(MPU6050_Data_TypeDef *data) {
    char buf[17];
    sprintf(buf, "Pitch:%+7.1f      ", data->pitch);
    OLED_ShowString(0, 0, (uint8_t*)buf, 16);
    sprintf(buf, "Roll :%+7.1f      ", data->roll);
    OLED_ShowString(0, 2, (uint8_t*)buf, 16);
    sprintf(buf, "Yaw  :%+7.1f      ", data->yaw);
    OLED_ShowString(0, 4, (uint8_t*)buf, 16);
    sprintf(buf, "Temp :%6.1f C     ", data->temp);
    OLED_ShowString(0, 6, (uint8_t*)buf, 16);
}
