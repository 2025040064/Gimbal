#include "app.h"
#include "gpio.h"
#include "usart.h"
#include "oled.h"
#include "motor.h"
#include "stabilizer.h"
#include "contest_config.h"
#include <stdio.h>

#if CONTEST_MODE != 'A' && CONTEST_MODE != 'B' && CONTEST_MODE != 'C' && CONTEST_MODE != 'D' && CONTEST_MODE != 'J' && CONTEST_MODE != 'T'
#error Select A, B, C, D, J or T
#endif
#if CONTEST_TARGET_ID < 0 || CONTEST_TARGET_ID > 9
#error Select a digit from 0 to 9
#endif
#if MOTION_CALIBRATED && (YAW_PULSES_PER_TURN < 360 || YAW_PULSES_PER_TURN > 1000000 || PITCH_PULSES_PER_TURN < 360 || PITCH_PULSES_PER_TURN > 1000000)
#error Invalid measured output-axis pulses per revolution
#endif
#if JOG_AXIS < 0 || JOG_AXIS > 1 || JOG_PULSES < -200 || JOG_PULSES > 200 || JOG_PULSE_US < 8000
#error Calibration jog must be small and slow
#endif
#if SCAN_PULSE_US < 500 || SCAN_PULSE_US > 10000 || TRACK_MIN_PULSE_US < 500 || TRACK_MIN_PULSE_US > 5500
#error Invalid pulse period
#endif

TIM_HandleTypeDef htim2;
static MotorCtrl_TypeDef yaw, pitch;
static Contest task;
static VisionFrame frame;
static uint32_t last_command, last_display, last_update;
static int32_t yaw_limit, pitch_limit;
static uint8_t jog_active, jog_started;
static const char *const state_names[] = {
    "SYNC", "ARM", "SEARCH", "TRACK", "HOLD", "WAIT LOSS", "OCCLUDED",
    "REARM", "DONE", "TIMEOUT", "LINK FAULT"
};

static void InitTimer(void)
{
    htim2.Instance = TIM2;
    htim2.Init.Prescaler = 71;
    htim2.Init.CounterMode = TIM_COUNTERMODE_UP;
    htim2.Init.Period = 49;
    htim2.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
    htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
    if (HAL_TIM_Base_Init(&htim2) != HAL_OK) Error_Handler();
    HAL_NVIC_SetPriority(TIM2_IRQn, 2, 0);
    HAL_NVIC_EnableIRQ(TIM2_IRQn);
    if (HAL_TIM_Base_Start_IT(&htim2) != HAL_OK) Error_Handler();
}

void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *timer)
{
    if (timer->Instance == TIM2) {
        MotorCtrl_Update(&yaw);
        MotorCtrl_Update(&pitch);
    }
}

static int32_t DegreesToPulses(int degrees, int32_t pulses_per_turn)
{
    return (int32_t)degrees * pulses_per_turn / 360;
}

static void TrackAxis(MotorCtrl_TypeDef *motor, int error, int half, int32_t limit)
{
    int magnitude = error < 0 ? -error : error;
    uint16_t period;
    uint32_t remaining;
    if (magnitude <= TRACK_DEADZONE_PX || half == 0) {
        MotorCtrl_Stop(motor);
        return;
    }
    remaining = magnitude >= half ? 0u : (uint32_t)(half - magnitude) * 100u / half;
    period = TRACK_MIN_PULSE_US +
             (5500u - TRACK_MIN_PULSE_US) * remaining * remaining / 10000u;
    MotorCtrl_Move(motor, error > 0 ? limit : -limit, period);
}

static void ApplyMotion(void)
{
    if (task.motion == MOTION_SCAN) {
        MotorCtrl_Move(&yaw, DegreesToPulses(task.yaw_deg, YAW_PULSES_PER_TURN), SCAN_PULSE_US);
        MotorCtrl_Move(&pitch, DegreesToPulses(task.pitch_deg, PITCH_PULSES_PER_TURN), SCAN_PULSE_US);
    } else if (task.motion == MOTION_TRACK) {
        TrackAxis(&yaw, task.frame.x - task.frame.width / 2, task.frame.width / 2, yaw_limit);
        TrackAxis(&pitch, task.frame.y - task.frame.height / 2, task.frame.height / 2, pitch_limit);
    } else {
        MotorCtrl_Stop(&yaw);
        MotorCtrl_Stop(&pitch);
    }
}

static void Line(uint8_t page, char *line)
{
    unsigned i = 0;
    while (i < 16 && line[i]) ++i;
    while (i < 16) line[i++] = ' ';
    line[16] = 0;
    OLED_ShowString(0, page, (uint8_t *)line, 16);
}

static void Show(void)
{
    char line[32];
    unsigned pos, i;
    const char *state = state_names[task.state];
    if (task.mode == 'C' && !Contest_Ended(&task) && task.have_sequence &&
        HAL_GetTick() - task.started >= 15000u) state = "MOVE NOW";
    sprintf(line, "%c %s", CONTEST_MODE, CONTEST_MODE == 'J' ?
            (jog_active ? "JOG" : "JOG DONE") : !MOTION_CALIBRATED && CONTEST_MODE != 'T' ?
            "CAL REQUIRED" : state);
    Line(0, line);
    if (CONTEST_MODE == 'A') {
        pos = 3;
        line[0] = 'I'; line[1] = 'D'; line[2] = ':';
        for (i = 0; i < 10; ++i) if (task.ids & (1u << i)) line[pos++] = '0' + i;
        if (pos == 3) line[pos++] = '-';
        line[pos] = 0;
    } else {
        sprintf(line, "ID:%u %s", task.id, task.centered ? "CENTER" : "");
    }
    Line(2, line);
    sprintf(line, "X:%d Y:%d", frame.x, frame.y);
    Line(4, line);
    if (CONTEST_MODE == 'B') sprintf(line, "HOLD:%lums", (unsigned long)task.hold_ms);
    else if (CONTEST_MODE == 'D') sprintf(line, "PASS:%u/%u", task.d_passes, task.d_trials);
    else if (CONTEST_MODE == 'J') sprintf(line, "STEP:%ld", (long)(JOG_AXIS ? pitch.position : yaw.position));
    else sprintf(line, "LOCK:%lums", (unsigned long)task.lock_ms);
    Line(6, line);
}

void App_Init(void)
{
    MX_GPIO_Init();
    MX_USART1_UART_Init();
    MotorCtrl_Init(&yaw, &hmotor2, YAW_POSITIVE_CW);
    MotorCtrl_Init(&pitch, &hmotor1, PITCH_POSITIVE_CW);
    OLED_Init();
    OLED_Clear();
    K230_Init();
    InitTimer();
    yaw_limit = DegreesToPulses(60, YAW_PULSES_PER_TURN);
    pitch_limit = DegreesToPulses(20, PITCH_PULSES_PER_TURN);
    frame.x = frame.y = -1;
    Contest_Init(&task, CONTEST_MODE == 'T' ? 'B' : CONTEST_MODE, CONTEST_TARGET_ID, HAL_GetTick());
    printf("BOOT,%c,%d,CAL=%d\r\n", CONTEST_MODE, CONTEST_TARGET_ID, MOTION_CALIBRATED);
}

void App_Update(void)
{
    uint32_t now = HAL_GetTick();
    VisionFrame received;
    int new_frame = K230_Read(&received);
    enum TaskState previous = task.state;
    uint8_t trials = task.d_trials;
    uint8_t locked = task.locked;
    int arrived;
    const char *command;
    char id_command[8];

    if (new_frame) frame = received;
    if (CONTEST_MODE == 'J') {
        if (!jog_started && now >= 1500u) {
            jog_started = jog_active = 1;
            MotorCtrl_Move(JOG_AXIS ? &pitch : &yaw, JOG_PULSES, JOG_PULSE_US);
        }
        if (jog_started && yaw.position == yaw.goal && pitch.position == pitch.goal) jog_active = 0;
    } else if ((MOTION_CALIBRATED || CONTEST_MODE == 'T') && (new_frame || now - last_update >= 10u)) {
        last_update = now;
        arrived = yaw.position == yaw.goal && pitch.position == pitch.goal;
        Contest_Update(&task, new_frame ? &received : 0, now, arrived);
        if (CONTEST_MODE != 'T') ApplyMotion();
        if (previous != task.state)
            printf("STATE,%lu,%s\r\n", (unsigned long)now, state_names[task.state]);
        if (!locked && task.locked)
            printf("LOCK,%lu,%u,%lu\r\n", (unsigned long)now, task.id, (unsigned long)task.lock_ms);
        if (trials != task.d_trials)
            printf("RECAPTURE,%u,%u,%lu\r\n", task.d_trials, task.d_passes, (unsigned long)task.d_last_ms);
        if (previous != task.state && Contest_Ended(&task))
            printf("RESULT,%c,%u,%lu,%lu,%u,%u,%u\r\n", task.mode, task.ids,
                   (unsigned long)task.lock_ms, (unsigned long)task.hold_ms,
                   task.left_view, task.d_passes, task.d_trials);
    }

    if (now - last_command >= 200u) {
        last_command = now;
        command = (MOTION_CALIBRATED || CONTEST_MODE == 'T') && CONTEST_MODE != 'J' ?
                  Contest_Command(&task) : "STOP\n";
        if (command[0] == 'I') {
            sprintf(id_command, "ID,%u\n", task.id);
            command = id_command;
        }
        K230_Send(command);
    }
    if (now - last_display >= 200u) {
        last_display = now;
        Show();
    }
}

void SystemClock_Config(void)
{
    RCC_OscInitTypeDef osc = {0};
    RCC_ClkInitTypeDef clk = {0};
    osc.OscillatorType = RCC_OSCILLATORTYPE_HSE;
    osc.HSEState = RCC_HSE_ON;
    osc.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
    osc.HSIState = RCC_HSI_ON;
    osc.PLL.PLLState = RCC_PLL_ON;
    osc.PLL.PLLSource = RCC_PLLSOURCE_HSE;
    osc.PLL.PLLMUL = RCC_PLL_MUL9;
    if (HAL_RCC_OscConfig(&osc) != HAL_OK) Error_Handler();
    clk.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    clk.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
    clk.AHBCLKDivider = RCC_SYSCLK_DIV1;
    clk.APB1CLKDivider = RCC_HCLK_DIV2;
    clk.APB2CLKDivider = RCC_HCLK_DIV1;
    if (HAL_RCC_ClockConfig(&clk, FLASH_LATENCY_2) != HAL_OK) Error_Handler();
}

void Error_Handler(void)
{
    __disable_irq();
    while (1) {}
}
