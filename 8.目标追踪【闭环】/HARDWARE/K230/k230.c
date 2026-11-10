#include "k230.h"
#include <string.h>

int K230_Parse(const char *line, VisionFrame *out)
{
    int32_t v[10];
    unsigned n = 0;
    int32_t value;
    int negative;
    VisionFrame f;

    do {
        negative = *line == '-';
        if (negative) ++line;
        if (*line < '0' || *line > '9' || n == 10) return 0;
        value = 0;
        do {
            value = value * 10 + *line++ - '0';
            if (value > 65535) return 0;
        } while (*line >= '0' && *line <= '9');
        v[n++] = negative ? -value : value;
        if (!*line) break;
        if (*line++ != ',') return 0;
    } while (1);
    if (n != 6 && n != 7 && n != 10) return 0;
    if (v[0] < 1 || v[0] > 4096 || v[1] < 1 || v[1] > 4096) return 0;
    if (v[2] != -1 || v[3] != -1 || v[4] != -1 || v[5] != -1) {
        if (v[2] < 0 || v[2] >= v[0] || v[3] < 0 || v[3] >= v[1] ||
            v[4] < 1 || v[4] > v[0] || v[5] < 1 || v[5] > v[1]) return 0;
    }
    if (n >= 7 && (v[6] < 0 || v[6] > 2047)) return 0;
    if (n == 10) {
        if (v[7] < VISION_IDLE || v[7] > VISION_FAULT || v[9] < 0) return 0;
        if (v[7] == VISION_TRACK) {
            if (v[8] < 0 || v[8] > 9 || (v[2] >= 0 && !(v[6] & (1u << v[8])))) return 0;
        } else if (v[8] != -1 || v[2] != -1) return 0;
    }
    f.width = v[0]; f.height = v[1]; f.x = v[2]; f.y = v[3];
    f.box_w = v[4]; f.box_h = v[5]; f.ids = n >= 7 ? v[6] : 0;
    f.mode = n == 10 ? v[7] : VISION_LEGACY;
    f.id = n == 10 ? v[8] : -1;
    f.sequence = n == 10 ? v[9] : 0;
    *out = f;
    return 1;
}

#ifndef CONTEST_HOST_TEST
#include "usart.h"

extern UART_HandleTypeDef huart3;
static uint8_t byte_in;
static char receive[80];
static char mailbox[80];
static uint8_t index_in, rx_state;
static volatile uint8_t ready;

void K230_Init(void)
{
    MX_USART3_UART_Init();
    HAL_UART_Receive_IT(&huart3, &byte_in, 1);
}

int K230_Send(const char *command)
{
    return HAL_UART_Transmit(&huart3, (uint8_t *)command, strlen(command), 10) == HAL_OK;
}

int K230_Read(VisionFrame *out)
{
    int parsed;
    if (!ready) return 0;
    parsed = K230_Parse(mailbox, out);
    ready = 0;
    return parsed;
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *uart)
{
    if (uart->Instance != USART3) return;
    if (byte_in == 0xAA) rx_state = 1;
    else if (rx_state == 1) {
        rx_state = byte_in == 0x55 ? 2 : 0;
        index_in = 0;
    } else if (rx_state == 2) {
        if (byte_in == '\r') rx_state = 3;
        else if (byte_in < 32 || byte_in > 126 || index_in == sizeof(receive) - 1) rx_state = 0;
        else receive[index_in++] = byte_in;
    } else if (rx_state == 3) {
        if (byte_in == '\n' && !ready) {
            receive[index_in] = 0;
            memcpy(mailbox, receive, index_in + 1u);
            ready = 1;
        }
        rx_state = 0;
    }
    HAL_UART_Receive_IT(uart, &byte_in, 1);
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *uart)
{
    if (uart->Instance != USART3) return;
    rx_state = 0;
    if (uart->RxState == HAL_UART_STATE_READY) HAL_UART_Receive_IT(uart, &byte_in, 1);
}
#endif
