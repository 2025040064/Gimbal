#include "k230.h"
#include "usart.h"
#include "string.h"
#include "stdio.h"

extern UART_HandleTypeDef huart3;
extern void MX_USART3_UART_Init(void);
extern uint8_t k230_data_valid;

#define RX_BUF_SIZE         64
#define K230_TIMEOUT_MS     500   // 超时时间：超过此时间未收到帧即认为无数据

static uint8_t k230_rx_byte;
static uint8_t k230_rx_data[RX_BUF_SIZE];
static uint8_t k230_rx_index = 0;
static uint8_t k230_rx_state = 0;
static uint8_t k230_frame_ready = 0;

// 对外暴露的解析结果
int16_t target_x = -1;
int16_t target_y = -1;
int16_t target_w = -1;
int16_t target_h = -1;
int16_t screen_w = 0;
int16_t screen_h = 0;

// 超时检测相关
static uint32_t last_k230_recv_tick = 0;   // 上一次成功解析帧的时刻

static void Parse_K230_Data(uint8_t *data);

/**
 * @brief  K230模块初始化
 */
void K230_Init(void)
{
    MX_USART3_UART_Init();
    HAL_UART_Receive_IT(&huart3, &k230_rx_byte, 1);
    last_k230_recv_tick = HAL_GetTick();    // 初始化时间戳
    printf("K230\xCA\xD3\xBE\xF5\xC4\xA3\xBF\xE9\xB3\xF5\xCA\xBC\xBB\xAF\xCD\xEA\xB3\xC9\r\n");
}

/**
 * @brief  处理K230接收帧，并维护超时状态
 */
void K230_Process(void)
{
    if (k230_frame_ready) {
        Parse_K230_Data(k230_rx_data);
        k230_frame_ready = 0;
    }

    // 超时检测：超过 K230_TIMEOUT_MS 未收到任何有效帧，视为无数据
    if (HAL_GetTick() - last_k230_recv_tick > K230_TIMEOUT_MS) {
        k230_data_valid = 0;
    }
}

/**
 * @brief  串口接收完成中断回调函数
 */
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART3) {
        uint8_t data = k230_rx_byte;

        switch (k230_rx_state) {
            case 0: if (data == 0xAA) k230_rx_state = 1; break;
            case 1: 
                if (data == 0x55) {
                    k230_rx_state = 2;
                    k230_rx_index = 0;
                    memset(k230_rx_data, 0, RX_BUF_SIZE);
                } else {
                    k230_rx_state = 0;
                }
                break;
            case 2:
                if (data == 0x0D) {
                    k230_rx_state = 3;
                } else {
                    k230_rx_data[k230_rx_index++] = data;
                    if (k230_rx_index >= RX_BUF_SIZE - 1) k230_rx_state = 0;
                }
                break;
            case 3:
                if (data == 0x0A) k230_frame_ready = 1;
                k230_rx_state = 0;
                break;
            default: k230_rx_state = 0; break;
        }

        HAL_UART_Receive_IT(&huart3, &k230_rx_byte, 1);
    }
}

/**
 * @brief  解析CSV数据帧，仅判断格式，不因内容为-1而置无效
 */
static void Parse_K230_Data(uint8_t *data)
{
    int16_t sw, sh;
    int result = sscanf((char*)data, "%hd,%hd,%hd,%hd,%hd,%hd", 
           &sw, &sh, 
           &target_x, &target_y, 
           &target_w, &target_h);
    
    if (result != 6) {
        // 解析失败，保持上次数据，但不清除 k230_data_valid
        printf("K230\xCA\xFD\xBE\xDD\xBD\xE2\xCE\xF6\xCA\xA7\xB0\xDC: %s\r\n", data);
        return;   
    }

    
    screen_w = sw;
    screen_h = sh;

    // 更新有效帧标志和时间戳
    k230_data_valid = 1;
    last_k230_recv_tick = HAL_GetTick();

   
    if (target_x == -1 && target_y == -1 && target_w == -1 && target_h == -1) {
        printf("K230\xA3\xBA\xCE\xB4\xBC\xEC\xB2\xE2\xB5\xBD\xC4\xBF\xB1\xEA\r\n");
    } else {
        printf("K230\xCA\xB6\xB1\xF0\xB5\xBD\xC4\xBF\xB1\xEA: X=%d Y=%d W=%d H=%d\r\n", 
               target_x, target_y, target_w, target_h);
    }
}
