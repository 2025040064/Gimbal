#include "app.h"
#include "gpio.h"
#include "usart.h"
#include "oled.h"
#include "motor.h"
#include "stabilizer.h"
#include "contest_config.h"
#include "mpu6050.h"
#include <stdio.h>
#include <stdarg.h>
#include <string.h>

#if CONTEST_MODE != 'S' && CONTEST_MODE != 'A' && CONTEST_MODE != 'B' && CONTEST_MODE != 'C' && CONTEST_MODE != 'D' && CONTEST_MODE != 'F' && CONTEST_MODE != 'J' && CONTEST_MODE != 'M' && CONTEST_MODE != 'T'
#error Invalid internal application mode
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
static TrackControl yaw_control, pitch_control;
static Contest task;
static VisionFrame frame;
static uint32_t last_command, last_display, last_update;
static int32_t yaw_limit, pitch_limit;
static uint8_t jog_active, jog_started;
static volatile uint32_t control_heartbeat;
static volatile uint8_t control_stalled;
static char display_lines[4][17], displayed[4][16];
static uint8_t display_cursor;
static uint32_t last_pixel;
static MPU6050_Data_TypeDef imu_data;
static uint32_t last_imu;
static uint8_t imu_ok;
static unsigned contest_stage;
static uint8_t sequence_saved;
static const char *const round_names[] = {"A", "B1", "B2", "B3", "C-H", "C-D", "D", "END"};

static int SaveStage(unsigned stage)
{
    uint16_t encoded = ContestSequence_Encode(stage);
    /* RM0008: BKP_DR1 survives system reset; no program Flash writes. */
    PWR->CR |= PWR_CR_DBP;
    BKP->DR1 = encoded;
    __DSB();
    PWR->CR &= ~PWR_CR_DBP;
    return (uint16_t)BKP->DR1 == encoded;
}

static void LoadStage(void)
{
    __HAL_RCC_PWR_CLK_ENABLE();
    __HAL_RCC_BKP_CLK_ENABLE();
    contest_stage = (RCC->CSR & RCC_CSR_PORRSTF) ? 0 : ContestSequence_Decode((uint16_t)BKP->DR1);
    if (!SaveStage(contest_stage)) Contest_Fail(&task, FAULT_SEQUENCE, HAL_GetTick());
    __HAL_RCC_CLEAR_RESET_FLAGS();
}
static const char *const state_names[] = {
    "SYNC", "ARM", "SEARCH", "TRACK", "HOLD", "WAIT LOSS", "OCCLUDED",
    "REARM", "DONE", "TIMEOUT", "FAULT"
};
static const char *const fault_names[] = {
    "NONE", "VISION/RECORD", "SYNC TIMEOUT", "ARM TIMEOUT", "WRONG ID",
    "LINK LOST", "STALE VISION", "UART TX", "CONTROL STALL", "ROUND MEMORY"
};

static void Log(const char *format, ...)
{
    char line[160];
    va_list args;
    va_start(args, format);
    vsnprintf(line, sizeof(line), format, args);
    va_end(args);
    UART_LogLine(line);
}

static void InitTimer(void)
{
    htim2.Instance = TIM2;
    htim2.Init.Prescaler = 71;
    htim2.Init.CounterMode = TIM_COUNTERMODE_UP;
    htim2.Init.Period = 49;
    htim2.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
    htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
    if (HAL_TIM_Base_Init(&htim2) != HAL_OK) Error_Handler();
    HAL_NVIC_SetPriority(TIM2_IRQn, 0, 0);
    HAL_NVIC_EnableIRQ(TIM2_IRQn);
    if (HAL_TIM_Base_Start_IT(&htim2) != HAL_OK) Error_Handler();
}

void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *timer)
{
    if (timer->Instance == TIM2) {
        /* A stalled foreground must not leave the last motion running. */
        if (control_stalled) return;
        if (HAL_GetTick() - control_heartbeat >= CONTROL_STALL_MS) {
            MotorCtrl_Stop(&yaw);
            MotorCtrl_Stop(&pitch);
            control_stalled = 1;
            return;
        }
        MotorCtrl_Update(&yaw);
        MotorCtrl_Update(&pitch);
    }
}

static int32_t DegreesToPulses(int degrees, int32_t pulses_per_turn)
{
    return (int32_t)degrees * pulses_per_turn / 360;
}

static void TrackAxis(MotorCtrl_TypeDef *motor, TrackControl *control,
                      int error, int half, int32_t limit, uint32_t now)
{
    int32_t speed = TrackControl_Update(control, error, half, task.sequence, now);
    int32_t magnitude = speed < 0 ? -speed : speed;
    uint16_t period;
    if (magnitude < 16 || (speed > 0 && motor->position >= limit) ||
        (speed < 0 && motor->position <= -limit)) {
        MotorCtrl_Stop(motor);
        if (magnitude >= 16) TrackControl_Reset(control);
        return;
    }
    period = (uint16_t)(1000000u / (uint32_t)magnitude);
    MotorCtrl_Move(motor, speed > 0 ? limit : -limit, period);
}

static void ApplyMotion(uint32_t now)
{
    if (task.motion != MOTION_TRACK) {
        TrackControl_Reset(&yaw_control);
        TrackControl_Reset(&pitch_control);
    }
    if (task.motion == MOTION_SCAN) {
        MotorCtrl_Move(&yaw, DegreesToPulses(task.yaw_deg, YAW_PULSES_PER_TURN), SCAN_PULSE_US);
        MotorCtrl_Move(&pitch, DegreesToPulses(task.pitch_deg, PITCH_PULSES_PER_TURN), SCAN_PULSE_US);
    } else if (task.motion == MOTION_TRACK) {
        TrackAxis(&yaw, &yaw_control, task.frame.x - task.frame.width / 2, task.frame.width / 2, yaw_limit, now);
        TrackAxis(&pitch, &pitch_control, task.frame.y - task.frame.height / 2, task.frame.height / 2, pitch_limit, now);
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
    memcpy(display_lines[page / 2], line, 17);
}

static void DisplayStep(uint32_t now)
{
    unsigned count;
    if (now - last_pixel < 2u) return;
    last_pixel = now;
    for (count = 0; count < 64; ++count) {
        unsigned row = display_cursor / 16u, col = display_cursor % 16u;
        display_cursor = (display_cursor + 1u) % 64u;
        if (displayed[row][col] != display_lines[row][col]) {
            OLED_ShowChar(col * 8u, row * 2u, (uint8_t)display_lines[row][col], 16);
            displayed[row][col] = display_lines[row][col];
            break; /* One glyph per main-loop pass, not a blocking screen refresh. */
        }
    }
}

static void Show(void)
{
    char line[32];
#if CONTEST_MODE == 'M'
    (void)frame.x;
    (void)jog_active;
    sprintf(line, "M MPU %s", imu_ok ? "OK" : "ERROR");
    Line(0, line);
    sprintf(line, "AX:%d", imu_data.acc_x); Line(2, line);
    sprintf(line, "AY:%d", imu_data.acc_y); Line(4, line);
    sprintf(line, "AZ:%d", imu_data.acc_z); Line(6, line);
#else
    unsigned pos, i;
    const char *state = state_names[task.state];
    uint32_t elapsed = HAL_GetTick() - task.started;
    (void)imu_ok;
    if (task.fault) state = fault_names[task.fault];
    else if (task.mode == 'C' && !Contest_Ended(&task) && task.scoring) state = "MOVE NOW";
    else if (task.mode == 'B' && task.acquire_failed && !Contest_Ended(&task)) state = "LOCK FAILED";
    sprintf(line, "%c %s", CONTEST_MODE, CONTEST_MODE == 'J' ?
            (jog_active ? "JOG" : "JOG DONE") : !MOTION_CALIBRATED && CONTEST_MODE != 'T' ?
            "CAL REQUIRED" : state);
    if (CONTEST_MODE == 'S') sprintf(line, "%s %s", round_names[contest_stage], state);
    Line(0, line);
    if (task.mode == 'A') {
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
    if (task.mode == 'B') sprintf(line, "HOLD:%lums", (unsigned long)task.hold_ms);
    else if (task.mode == 'D') sprintf(line, "PASS:%u/%u", task.d_passes, task.d_trials);
    else if (CONTEST_MODE == 'J') sprintf(line, "STEP:%ld", (long)(JOG_AXIS ? pitch.position : yaw.position));
    else if (task.mode == 'C' && task.have_sequence && !Contest_Ended(&task)) {
        uint32_t end = task.scoring ? ACQUIRE_MS + C_SCORE_MS : ACQUIRE_MS;
        sprintf(line, "%s:%lus", task.scoring ? "SCORE" : "READY", (unsigned long)((end - elapsed + 999u) / 1000u));
    } else sprintf(line, "LOCK:%lums", (unsigned long)task.lock_ms);
    Line(6, line);
#endif
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
    if (CONTEST_MODE == 'M') MPU6050_Init();
    control_heartbeat = HAL_GetTick();
    InitTimer();
    memset(display_lines, ' ', sizeof(display_lines));
    yaw_limit = DegreesToPulses(YAW_LIMIT_DEG, YAW_PULSES_PER_TURN);
    pitch_limit = DegreesToPulses(PITCH_LIMIT_DEG, PITCH_PULSES_PER_TURN);
    frame.x = frame.y = -1;
    Contest_Init(&task, CONTEST_MODE == 'T' ? 'B' : CONTEST_MODE, CONTEST_TARGET_ID, HAL_GetTick());
    if (CONTEST_MODE == 'S') {
        LoadStage();
        task.mode = ContestSequence_Mode(contest_stage);
        if (contest_stage == 7 && !task.fault) task.state = TASK_DONE;
        Log("ROUND,%s,ID=%u\r\n", round_names[contest_stage], task.id);
    }
    Log("BOOT,%c,%d,CAL=%d,ONE_WAY=%d,ZERO=MANUAL,D_TIME=EST\r\n", CONTEST_MODE, CONTEST_TARGET_ID, MOTION_CALIBRATED, VISION_ONE_WAY);
    Show();
}

void App_Update(void)
{
    uint32_t now = HAL_GetTick();
    VisionFrame received;
    int new_frame = K230_Read(&received);
    enum TaskState previous = task.state;
    uint8_t trials = task.d_trials;
    uint8_t locked = task.locked;
    uint8_t scoring = task.scoring;
    uint16_t sequence = task.sequence;
    int arrived;
    const char *command;
    char id_command[8];

    control_heartbeat = now;
    if (control_stalled) Contest_Fail(&task, FAULT_CONTROL, now);
    if (new_frame) frame = received;
    if (CONTEST_MODE == 'M') {
        if (now - last_imu >= 100) {
            last_imu = now;
            imu_ok = MPU6050_ReadData(&imu_data) == 0;
        }
    } else if (CONTEST_MODE == 'J') {
        if (!jog_started && now >= 1500u) {
            jog_started = jog_active = 1;
            MotorCtrl_Move(JOG_AXIS ? &pitch : &yaw, JOG_PULSES, JOG_PULSE_US);
        }
        if (jog_started && yaw.position == yaw.goal && pitch.position == pitch.goal) jog_active = 0;
    } else if ((MOTION_CALIBRATED || CONTEST_MODE == 'T') && (new_frame || now - last_update >= 10u)) {
        last_update = now;
        arrived = yaw.position == yaw.goal && pitch.position == pitch.goal;
        Contest_Update(&task, new_frame ? &received : 0, now, arrived);
        if (CONTEST_MODE != 'T') ApplyMotion(now);
        if (previous != task.state)
            Log("STATE,%lu,%s,FAULT=%s\r\n", (unsigned long)now, state_names[task.state], fault_names[task.fault]);
        if (!locked && task.locked)
            Log("LOCK,%lu,%u,%lu\r\n", (unsigned long)now, task.id, (unsigned long)task.lock_ms);
        if (trials != task.d_trials)
            Log("RECAPTURE_EST,%u,%u,%lu\r\n", task.d_trials, task.d_passes, (unsigned long)task.d_last_ms);
        if (!scoring && task.scoring) Log("SCORE_START,%lu\r\n", (unsigned long)now);
        if (new_frame && task.have_sequence && sequence != task.sequence)
            Log("OBS,%lu,%u,%d,%d,%u\r\n", (unsigned long)now, task.sequence, task.frame.x, task.frame.y, task.frame.ids);
        if (previous != task.state && Contest_Ended(&task))
            Log("RESULT,%c,%u,%lu,%lu,%u,%u,%u,DROP=%lu\r\n", task.mode, task.ids,
                   (unsigned long)task.lock_ms, (unsigned long)task.hold_ms,
                   task.left_view, task.d_passes, task.d_trials, (unsigned long)UART_LogDropped());
    }

    if (CONTEST_MODE == 'S' && !sequence_saved &&
        (task.state == TASK_DONE || task.state == TASK_TIMEOUT)) {
        unsigned next = ContestSequence_Next(contest_stage, task.state);
        if (SaveStage(next)) {
            sequence_saved = 1;
            Log("NEXT,%s,RESET_TO_START\r\n", round_names[next]);
        } else Contest_Fail(&task, FAULT_SEQUENCE, now);
    }

    if (!VISION_ONE_WAY && CONTEST_MODE != 'M' && now - last_command >= 200u) {
        last_command = now;
        command = (MOTION_CALIBRATED || CONTEST_MODE == 'T') && CONTEST_MODE != 'J' ?
                  Contest_Command(&task) : "STOP\n";
        if (command[0] == 'I') {
            sprintf(id_command, "ID,%u\n", task.id);
            command = id_command;
        }
        if (!K230_Send(command)) {
            Contest_Fail(&task, FAULT_TX, now);
            MotorCtrl_Stop(&yaw);
            MotorCtrl_Stop(&pitch);
        }
    }
    if (now - last_display >= 200u) {
        last_display = now;
        Show();
    }
    UART_LogPoll();
    DisplayStep(now);
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
