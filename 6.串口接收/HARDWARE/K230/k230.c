#include "k230.h"
#include "usart.h"
#include "string.h"
#include "stdio.h"




extern UART_HandleTypeDef huart3;  // huart3串口句柄定义，外部变量声明
extern void MX_USART3_UART_Init(void);


// 串口接收缓冲区大小：K230一帧数据最多20字节，64字节足够用
#define RX_BUF_SIZE         64
// 超时时间：500ms内没收到任何有效帧，就认为数据无效
// 为什么选500ms：K230每秒发10帧，500ms没收到说明通信中断
#define K230_TIMEOUT_MS     500



static uint8_t k230_rx_byte;         // 每次中断接收1个字节，存在这里
static uint8_t k230_rx_data[RX_BUF_SIZE]; // 接收缓冲区，存储一帧完整数据
static uint8_t k230_rx_index = 0;    // 缓冲区当前写入位置索引
static uint8_t k230_rx_state = 0;    // 状态机当前状态（0~3）
static uint8_t k230_frame_ready = 0; // 帧就绪标志：=1表示收到完整一帧，等待解析


int16_t target_x = -1;
int16_t target_y = -1;
int16_t target_w = -1;
int16_t target_h = -1;
int16_t screen_w = 0;
int16_t screen_h = 0;

uint8_t k230_data_valid = 0;         // 数据有效标志
static uint32_t last_k230_recv_tick = 0; // 上一次收到有效帧的时间戳（ms）


static void Parse_K230_Data(uint8_t *data);

// 【初始化函数】
void K230_Init(void)
{
    // 1. 初始化USART3串口硬件（波特率115200 8N1）
    MX_USART3_UART_Init();
    // 2. 启动第一次中断接收：告诉HAL库"收到1个字节就触发中断"
    // 注意：HAL的中断接收是一次性的，每次收到后必须重新调用
    HAL_UART_Receive_IT(&huart3, &k230_rx_byte, 1);
    // 3. 初始化超时时间戳
    last_k230_recv_tick = HAL_GetTick();
    // 调试打印
    printf("K230视觉模块初始化完成\r\n");
}

// 【主循环处理函数】
void K230_Process(void)
{
    // 1. 如果收到完整一帧，就解析数据

    if (k230_frame_ready) {
        Parse_K230_Data(k230_rx_data);
        // 解析完成后清除标志，等待下一帧
        k230_frame_ready = 0;
    }

    // 2. 超时检测：超过500ms没收到有效帧，标记数据无效
    // 作用：防止K230断电/断线后，屏幕还显示过期的旧数据
    if (HAL_GetTick() - last_k230_recv_tick > K230_TIMEOUT_MS) {
        k230_data_valid = 0;
    }
}


// 【串口接收完成中断回调函数】
// 这是数据进入STM32的唯一入口！

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
    // 只处理USART3的中断（USART1是调试串口，不处理）
    if (huart->Instance == USART3) {
        // 取出刚刚收到的1个字节
        uint8_t data = k230_rx_byte;


        // 【状态帧解析状态机】
        // 这是嵌入式串口通信最稳定的解析方式
        // 可以自动跳过错误字节，同步到正确的帧头

        switch (k230_rx_state) {
            // 状态0：等待帧头第1字节 0xAA
            case 0: 
                if (data == 0xAA) 
                    k230_rx_state = 1; // 收到0xAA，进入下一个状态
                break;

            // 状态1：等待帧头第2字节 0x55
            case 1: 
                if (data == 0x55) {
                    // 收到完整帧头(0xAA 0x55)，准备接收数据
                    k230_rx_state = 2;
                    // 重置缓冲区索引
                    k230_rx_index = 0;
                    // 清空缓冲区，防止上一帧残留数据干扰
                    memset(k230_rx_data, 0, RX_BUF_SIZE);
                } else {
                    // 不是0x55，说明是错误字节，回到状态0重新等待帧头
                    k230_rx_state = 0;
                }
                break;

            // 状态2：接收数据内容，直到收到帧尾第1字节 0x0D
            case 2:
                if (data == 0x0D) {
                    // 收到0x0D，进入状态3等待第二个帧尾字节
                    k230_rx_state = 3;
                } else {
                    // 是数据内容，存入缓冲区
                    k230_rx_data[k230_rx_index++] = data;
                    // 缓冲区溢出保护：防止数据过长导致内存越界
                    if (k230_rx_index >= RX_BUF_SIZE - 1) 
                        k230_rx_state = 0;
                }
                break;

            // 状态3：等待帧尾第2字节 0x0A
            case 3:
                if (data == 0x0A) {
                    // 收到完整帧尾(0x0D 0x0A)，标记帧就绪
                    k230_frame_ready = 1;
                }
                // 无论是否收到0x0A，都回到状态0等待下一帧
                k230_rx_state = 0;
                break;

            // 异常状态：回到初始状态
            default: 
                k230_rx_state = 0; 
                break;
        }

        // 重新启动下一次中断接收
        // HAL的中断接收是一次性的，每次收到1个字节后必须重新调用
        HAL_UART_Receive_IT(&huart3, &k230_rx_byte, 1);
    }
}

// 【数据解析函数】
// 把收到的CSV格式字符串解析成数值
static void Parse_K230_Data(uint8_t *data)
{
    int16_t sw, sh; // 临时存储屏幕分辨率

    // 用sscanf解析CSV格式字符串
    // 格式说明：%hd 对应int16_t类型，逗号分隔
    // 解析顺序：屏幕宽,屏幕高,目标X,目标Y,目标宽,目标高
    int result = sscanf((char*)data, "%hd,%hd,%hd,%hd,%hd,%hd",
           &sw, &sh, 
           &target_x, &target_y, 
           &target_w, &target_h);

    // 只有成功解析到6个数值，才认为是有效帧
    if (result != 6) {
        // 解析失败，打印错误信息，不更新数据
        printf("K230数据解析失败: %s\r\n", data);
        return;
    }

    // 解析成功，更新全局变量
    screen_w = sw;
    screen_h = sh;
    // 标记数据有效
    k230_data_valid = 1;
    // 更新最后一次收到有效帧的时间戳
    last_k230_recv_tick = HAL_GetTick();

    // 调试打印
    if (target_x == -1 && target_y == -1) {
        // K230返回-1表示未检测到目标
        printf("K230：未检测到目标\r\n");
    } else {
        // 打印检测到的目标坐标
        printf("K230识别到目标: X=%d Y=%d W=%d H=%d\r\n", 
               target_x, target_y, target_w, target_h);
    }
}
