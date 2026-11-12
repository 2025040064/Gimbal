#include "k230.h"
#include "usart.h"
#include <stdlib.h>
#include <string.h>

extern UART_HandleTypeDef huart3;
extern void MX_USART3_UART_Init(void);

#define RX_BUF_SIZE          64
#define TARGET_FRESH_MS     150U
#define SCREEN_WIDTH        640
#define SCREEN_HEIGHT       480

enum RxState { WAIT_AA, WAIT_55, READ_PAYLOAD, WAIT_LF };

static uint8_t rx_byte;
static char rx_data[RX_BUF_SIZE];
static uint8_t rx_index;
static enum RxState rx_state;
static char pending_data[RX_BUF_SIZE];
static volatile uint8_t pending_length;
static volatile uint32_t pending_tick;

int16_t target_x = -1;
int16_t target_y = -1;
int16_t target_w = -1;
int16_t target_h = -1;
int16_t screen_w = SCREEN_WIDTH;
int16_t screen_h = SCREEN_HEIGHT;

static volatile uint8_t target_valid;
static volatile uint32_t last_target_tick;

void K230_Init(void)
{
    MX_USART3_UART_Init();
    HAL_UART_Receive_IT(&huart3, &rx_byte, 1);
}

uint8_t K230_TargetIsFresh(void)
{
    return target_valid && HAL_GetTick() - last_target_tick < TARGET_FRESH_MS;
}

static uint8_t Parse_K230_Data(const char *data)
{
    long fields[6];
    for (uint8_t i = 0; i < 6; i++) {
        char *end;
        char separator = (i < 5) ? ',' : '\0';
        fields[i] = strtol(data, &end, 10);
        if (end == data || *end != separator) return 0;
        data = end + 1;
    }

    if (fields[0] != SCREEN_WIDTH || fields[1] != SCREEN_HEIGHT) return 0;

    if (fields[2] == -1 && fields[3] == -1 && fields[4] == -1 && fields[5] == -1) {
        target_valid = 0;
        target_x = target_y = target_w = target_h = -1;
        return 0;
    }

    if (fields[2] < 0 || fields[2] >= SCREEN_WIDTH ||
        fields[3] < 0 || fields[3] >= SCREEN_HEIGHT ||
        fields[4] <= 0 || fields[4] > SCREEN_WIDTH ||
        fields[5] <= 0 || fields[5] > SCREEN_HEIGHT) return 0;

    target_x = (int16_t)fields[2];
    target_y = (int16_t)fields[3];
    target_w = (int16_t)fields[4];
    target_h = (int16_t)fields[5];
    return 1;
}

uint8_t K230_Process(void)
{
    uint8_t was_valid = target_valid;
    if (pending_length != 0) {
        char data[RX_BUF_SIZE];
        // Take a snapshot of the latest complete frame before parsing in the main loop.
        uint32_t irq_state = __get_PRIMASK();
        __disable_irq();
        memcpy(data, pending_data, pending_length);
        uint32_t received_at = pending_tick;
        pending_length = 0;
        __set_PRIMASK(irq_state);

        if (HAL_GetTick() - received_at < TARGET_FRESH_MS && Parse_K230_Data(data)) {
            last_target_tick = received_at;
            target_valid = 1;
            return 1;
        }
    }

    if (!K230_TargetIsFresh()) target_valid = 0;
    return was_valid && !target_valid;
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance != USART3 || huart->ErrorCode != HAL_UART_ERROR_NONE) return;

    uint8_t byte = rx_byte;
    if (byte == 0xAA) {
        rx_state = WAIT_55;
    } else {
        switch (rx_state) {
        case WAIT_55:
            rx_state = (byte == 0x55) ? READ_PAYLOAD : WAIT_AA;
            rx_index = 0;
            break;
        case READ_PAYLOAD:
            if (byte == '\r') {
                rx_state = WAIT_LF;
            } else if (((byte >= '0' && byte <= '9') || byte == '-' || byte == ',')
                       && rx_index < RX_BUF_SIZE - 1) {
                rx_data[rx_index++] = (char)byte;
            } else {
                rx_state = WAIT_AA;
            }
            break;
        case WAIT_LF:
            if (byte == '\n') {
                rx_data[rx_index] = '\0';
                memcpy(pending_data, rx_data, rx_index + 1);
                pending_tick = HAL_GetTick();
                pending_length = rx_index + 1;
            }
            rx_state = WAIT_AA;
            break;
        default:
            break;
        }
    }
    HAL_UART_Receive_IT(huart, &rx_byte, 1);
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART3) {
        rx_state = WAIT_AA;
        HAL_UART_Receive_IT(huart, &rx_byte, 1);
    }
}
