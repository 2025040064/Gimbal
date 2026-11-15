#include "stabilizer.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "contest_config.h"

static uint16_t seq;

static VisionFrame frame(uint8_t mode, int8_t id, int visible)
{
    VisionFrame f = {640, 480, -1, -1, -1, -1, 0, mode, id, seq++};
    if (visible) {
        f.x = 320; f.y = 240; f.box_w = 40; f.box_h = 50;
        f.ids = 1u << id;
    }
    return f;
}

static void start(Contest *t, char mode, uint32_t now)
{
    VisionFrame idle = frame(VISION_IDLE, -1, 0);
    Contest_Init(t, mode, 1, now);
    Contest_Update(t, &idle, now, 1);
    assert(t->state == TASK_ARM);
}

static void input(Contest *t, uint32_t now, int visible)
{
    VisionFrame f = frame(VISION_TRACK, 1, visible);
    Contest_Update(t, &f, now, 0);
}

static void test_protocol(void)
{
    VisionFrame f;
    assert(K230_Parse("ALL,640,480,9,0,2,1,320,240,40,50,7,100,200,20,30", &f));
    assert(f.mode == VISION_BROADCAST && f.id == CONTEST_TARGET_ID && f.x == 320 && f.ids == 130);
    assert(K230_Parse("ALL,640,480,10,0,1,7,100,200,20,30", &f));
    assert(f.x == -1 && f.ids == 128);
    assert(!K230_Parse("ALL,640,480,9,0,2,1,320,240,40,50,1,100,200,20,30", &f));
    assert(!K230_Parse("ALL,640,480,9,0,1,1,640,240,40,50", &f));
    assert(K230_Parse("ALL,640,480,10,3,0", &f) && f.mode == VISION_FAULT);
    assert(K230_Parse("640,480,320,240,30,50,2,2,1,65535", &f));
    assert(f.mode == VISION_TRACK && f.id == 1 && f.sequence == 65535);
    assert(K230_Parse("640,480,-1,-1,-1,-1,6,1,-1,0", &f));
    assert(K230_Parse("640,480,20,30,10,10", &f) && f.mode == VISION_LEGACY);
    assert(!K230_Parse("640,480,20,30,10,10,4,2,1,0", &f));
    assert(!K230_Parse("640,480,640,30,10,10", &f));
    assert(!K230_Parse("640,480,-1,1,-1,-1", &f));
    assert(!K230_Parse("640,480,-1,-1,-1,-1,", &f));
    assert(!K230_Parse("640,480,-1,-1,-1,-1,2,2,1,65536", &f));
    assert(!K230_Parse("640,480,-1,-1,-1,-1,2,2,1,4x", &f));
}

static void test_continuous_tracking(void)
{
    Contest t;
    VisionFrame f;
    uint32_t n;
    assert(K230_Parse("ALL,640,480,1,0,1,1,400,240,40,40", &f));
    Contest_Init(&t, 'F', CONTEST_TARGET_ID, 0);
    Contest_Update(&t, &f, 0, 1);
    for (n = 0; n <= 40000; n += 100) {
        f.sequence++;
        Contest_Update(&t, &f, n, 1);
    }
    assert(!Contest_Ended(&t) && t.motion == MOTION_TRACK);
    f.x = -1; f.y = -1; f.box_w = -1; f.box_h = -1; f.ids = 0;
    for (; n <= 40700; n += 100) { f.sequence++; Contest_Update(&t, &f, n, 1); }
    assert(t.motion == MOTION_SCAN);
    Contest_Update(&t, 0, n + 500, 1);
    assert(t.state == TASK_FAULT && t.fault == FAULT_LINK && t.motion == MOTION_STOP);
}

static void test_search_pitch_bounds(void)
{
    Contest t;
    VisionFrame f;
    uint32_t now;
    assert(K230_Parse("ALL,640,480,1,0,0", &f));
    Contest_Init(&t, 'F', CONTEST_TARGET_ID, 0);
    Contest_Update(&t, &f, 0, 1);
    f.sequence++;
    Contest_Update(&t, &f, 100, 1);
    assert(t.motion == MOTION_SCAN && t.pitch_deg == 0);
    for (now = 200; now <= 3000; now += 100) {
        f.sequence++;
        Contest_Update(&t, &f, now, 1);
        assert(t.pitch_deg >= -10 && t.pitch_deg <= 10);
    }
}

static void test_tracking_response(void)
{
    TrackControl control;
    int32_t speed = 0, previous = 0;
    uint32_t now;
    TrackControl_Reset(&control);
    for (now = 0; now <= 500; now += 10) {
        speed = TrackControl_Update(&control, 32, 320, (uint16_t)(now / 50), now);
        assert(speed - previous <= 24);
        previous = speed;
    }
    /* A 10% frame error must command a useful speed after acceleration. */
    assert(speed >= 180 && speed <= 1000000 / TRACK_MIN_PULSE_US);
}

static void test_one_way(void)
{
    Contest t;
    VisionFrame f;
    char packet[320];
    const char modes[] = "ABCD";
    unsigned i, n;
    int used;
    /* Ten simultaneous IDs, including the selected target, fit one UART frame. */
    used = sprintf(packet, "ALL,640,480,65535,0,10");
    for (i = 0; i < 10; ++i)
        used += sprintf(packet + used, ",%u,320,240,640,480", i);
    assert(used < 320 && K230_Parse(packet, &f));
    assert(f.ids == 1023 && f.id == CONTEST_TARGET_ID && f.x == 320);
    for (i = 0; i < 4; ++i) {
        Contest_Init(&t, modes[i], CONTEST_TARGET_ID, 0);
        f.sequence = 65534;
        Contest_Update(&t, &f, 0, 1);
        assert(t.state == TASK_ARM && t.motion == MOTION_STOP);
        /* No IDLE reply, command ACK or K230 RX is involved. */
        for (n = 0; n <= 1200; n += 100) {
            f.sequence = (uint16_t)(65535 + n / 100);
            Contest_Update(&t, &f, n, 1);
        }
        assert(!Contest_Ended(&t));
        if (modes[i] == 'A') assert(t.ids == 1023 && t.motion == MOTION_SCAN);
        else assert(t.locked);
    }
    assert(K230_Parse("ALL,640,480,20,0,1,7,320,240,40,40", &f));
    Contest_Init(&t, 'B', CONTEST_TARGET_ID, 0);
    Contest_Update(&t, &f, 0, 1);
    for (n = 0; n <= 1200; n += 100) {
        f.sequence++;
        Contest_Update(&t, &f, n, 1);
    }
    assert(!t.locked && t.frame.x == -1 && t.motion == MOTION_SCAN);
    Contest_Update(&t, &f, 1550, 1); /* Repeated sequence cannot keep motion alive. */
    assert(t.motion == MOTION_STOP);
    Contest_Update(&t, 0, 2050, 1);
    assert(t.state == TASK_FAULT && t.fault == FAULT_LINK);
    assert(!K230_Parse("ALL,640,480,1,0,11", &f));
    assert(!K230_Parse("ALL,640,480,1,0,1", &f));
    assert(!K230_Parse("ALL,640,480,1,0,0,1", &f));
    assert(!K230_Parse("ALL,640,480,1,3,1,1,320,240,40,40", &f));
    assert(!K230_Parse("ALL,640,480,-1,0,0", &f));
    assert(!K230_Parse("ALL,640,480,1,0,1,10,320,240,40,40", &f));
    assert(!K230_Parse("ALL,640,480,1,0,1,1,320,240,0,40", &f));
    assert(!K230_Parse("ALL,640,480,1,1,0", &f));
    assert(K230_Parse("ALL,640,480,21,3,0", &f));
    Contest_Init(&t, 'B', CONTEST_TARGET_ID, 0);
    Contest_Update(&t, &f, 0, 1);
    assert(t.state == TASK_FAULT && t.fault == FAULT_VISION);
}

static void test_scan(void)
{
    Contest t;
    uint32_t n;
    int saw_top = 0, saw_bottom = 0;
    start(&t, 'A', 0);
    for (n = 0; n <= 60000; n += 200) {
        VisionFrame f = frame(VISION_SCAN, -1, 0);
        f.ids = n < 60000 ? 1026 | ((n > 500) ? 4 : 0) : 8;
        Contest_Update(&t, &f, n, 1);
        assert(t.yaw_deg >= -60 && t.yaw_deg <= 60);
        assert(t.pitch_deg >= -20 && t.pitch_deg <= 20);
        saw_top |= t.pitch_deg == 20;
        saw_bottom |= t.pitch_deg == -20;
    }
    assert(saw_top && saw_bottom && t.ids == 6);
    assert(t.state == TASK_DONE && t.motion == MOTION_STOP);
}

static void test_lock(void)
{
    Contest t;
    uint32_t n;
    start(&t, 'B', 0);
    for (n = 0; n <= 6400; n += 200) {
        input(&t, n, n != 400);
        if (n < 1600) assert(!t.locked);
    }
    assert(t.lock_ms == 1600 && t.hold_ms == 4800);
    input(&t, 6600, 1);
    assert(!Contest_Ended(&t) && t.hold_ms == 5000);
    for (n = 6800; n <= 20000; n += 200) input(&t, n, 1);
    assert(t.state == TASK_DONE && t.hold_ms == 5000);
    start(&t, 'B', 0);
    for (n = 0; n <= 15000; n += 200) input(&t, n, 0);
    assert(!Contest_Ended(&t) && !t.locked);
    for (n = 15200; n <= 20000; n += 200) input(&t, n, 1);
    assert(t.state == TASK_TIMEOUT && !t.locked);
}

static void test_identity_and_timeouts(void)
{
    Contest t;
    VisionFrame wrong = frame(VISION_TRACK, 2, 1);
    VisionFrame repeated = frame(VISION_TRACK, 1, 1);
    uint32_t n;
    start(&t, 'B', 0);
    Contest_Update(&t, &wrong, 10, 1);
    assert(t.state == TASK_ARM && t.motion == MOTION_STOP);
    input(&t, 20, 1);
    Contest_Update(&t, &wrong, 30, 1);
    assert(t.state == TASK_FAULT && t.motion == MOTION_STOP);
    start(&t, 'B', 0);
    input(&t, 100, 1);
    Contest_Update(&t, 0, 600, 0);
    assert(t.state == TASK_FAULT && t.motion == MOTION_STOP);
    start(&t, 'B', 0);
    for (n = 0; n <= 1100; n += 100) Contest_Update(&t, &repeated, n, 0);
    assert(t.state == TASK_FAULT && !t.locked);
}

static void test_moving(void)
{
    Contest t;
    uint32_t n;
    start(&t, 'C', 0);
    for (n = 0; n <= 30000; n += 200) input(&t, n, n != 16000);
    assert(t.locked && t.left_view && t.state == TASK_DONE);
}

static void test_reacquire(void)
{
    Contest t;
    uint32_t n, trial;
    start(&t, 'D', 0);
    for (n = 0; n <= 1000; n += 200) input(&t, n, 1);
    assert(t.state == TASK_WAIT_LOSS && t.locked);
    for (trial = 0; trial < 3; ++trial) {
        uint32_t start_loss = n;
        for (; n < start_loss + 2000; n += 200) {
            input(&t, n, 0);
            assert(t.state == TASK_OCCLUDED && t.motion == MOTION_STOP);
        }
        for (; n <= start_loss + 3000; n += 200) input(&t, n, 1);
        assert(t.d_passes == trial + 1 && t.d_last_ms == 1000);
    }
    assert(t.state == TASK_DONE);
}

static void test_tracking_control(void)
{
    TrackControl c;
    uint32_t now;
    int32_t speed = 0, previous, filtered;
    int crossed_zero = 0;
    TrackControl_Reset(&c);
    for (now = 0; now <= 600; now += 10) {
        previous = speed;
        speed = TrackControl_Update(&c, 320, 320, 1, now);
        assert(speed >= previous && speed - previous <= TRACK_ACCEL_PPS2 / 100);
        assert(speed <= 1000000 / TRACK_MIN_PULSE_US);
    }
    for (; now <= 1800; now += 10) {
        previous = speed;
        speed = TrackControl_Update(&c, -320, 320, 2, now);
        if (!speed) crossed_zero = 1;
        if (speed < 0) assert(crossed_zero);
        assert(previous - speed <= TRACK_ACCEL_PPS2 / 100);
    }
    assert(speed < 0);
    assert(TrackControl_Update(&c, 7, 320, 3, now) == 0);
    assert(TrackControl_Update(&c, 11, 320, 4, now + 10) == 0);
    assert(TrackControl_Update(&c, -11, 320, 5, now + 20) == 0);
    assert(TrackControl_Update(&c, 20, 320, 6, now + 30) > 0);
    filtered = c.filtered_q8;
    TrackControl_Update(&c, 20, 320, 6, now + 40);
    assert(c.filtered_q8 == filtered);
    TrackControl_Reset(&c);
    TrackControl_Update(&c, 320, 320, 65535, 0xfffffff0u);
    assert(TrackControl_Update(&c, 320, 320, 0, 4) == 48);
    assert(TrackControl_Update(&c, 320, 320, 0, 1004) == 168);
    assert(TrackControl_Update(&c, 20, 0, 1, 1014) == 0);
}

static void test_sequence_and_recovery(void)
{
    Contest t;
    VisionFrame f = frame(VISION_TRACK, 1, 1);
    start(&t, 'C', 0);
    f.sequence = 65535;
    Contest_Update(&t, &f, 0, 0);
    f.sequence = 0;
    Contest_Update(&t, &f, 200, 0);
    assert(t.sequence == 0 && t.last_obs == 200);
    f.sequence = 65535;
    f.x = 100;
    Contest_Update(&t, &f, 300, 0);
    assert(t.frame.x == 320 && t.last_obs == 200);
    Contest_Update(&t, 0, 550, 0);
    assert(t.motion == MOTION_STOP && !t.centered);
    f.sequence = 1;
    f.x = 320;
    Contest_Update(&t, &f, 600, 0);
    assert(t.motion == MOTION_TRACK && !t.locked);
    f.sequence = 2;
    f.x = f.y = f.box_w = f.box_h = -1;
    Contest_Update(&t, &f, 700, 0);
    assert(t.motion == MOTION_STOP);
    f.sequence = 3;
    f.x = 320; f.y = 240; f.box_w = 40; f.box_h = 50;
    Contest_Update(&t, &f, 800, 0);
    assert(t.motion == MOTION_TRACK && !t.locked);
}

static void test_deadlines_and_d_estimate(void)
{
    Contest t;
    uint32_t n;
    start(&t, 'B', 0);
    for (n = 0; n <= 20000; n += 200) input(&t, n, n >= 14000);
    assert(t.lock_ms == 15000 && t.hold_ms == 5000 && t.state == TASK_DONE);
    start(&t, 'C', 0);
    for (n = 0; n <= 15000; n += 200) input(&t, n, 0);
    assert(t.scoring && !t.locked && !Contest_Ended(&t));
    for (; n <= 30000; n += 200) input(&t, n, 1);
    assert(t.state == TASK_DONE && t.left_view && t.locked);
    start(&t, 'D', 0);
    for (n = 0; n <= 1000; n += 200) input(&t, n, 1);
    input(&t, 1200, 0);
    for (n = 1400; n <= 3200; n += 200) input(&t, n, 1);
    assert(t.d_trials == 0 && t.reveal_at == 3200); /* Early visibility cannot move the estimate. */
    for (; n <= 4200; n += 200) input(&t, n, 1);
    assert(t.d_passes == 1 && t.d_times[0] == 1000);
    for (n = 4400; n <= 14400; n += 200) input(&t, n, 0);
    assert(t.d_trials == 2 && t.d_passes == 1 && t.state == TASK_REARM);
    assert(t.d_times[1] == 8000);
    for (; n <= 15600; n += 200) input(&t, n, 1);
    assert(t.state == TASK_WAIT_LOSS);
    for (; n < 17800; n += 200) input(&t, n, 0);
    for (; n <= 18800; n += 200) input(&t, n, 1);
    assert(t.state == TASK_DONE && t.d_trials == 3 && t.d_passes == 2);
    assert(t.d_success_mask == 5);
}

int main(void)
{
    test_search_pitch_bounds();
    test_tracking_response();
    test_continuous_tracking();
    test_one_way();
    test_deadlines_and_d_estimate();
    test_tracking_control();
    test_sequence_and_recovery();
    /* A heartbeat must not keep driving toward an old coordinate. */
    {
        Contest t;
        VisionFrame f = frame(VISION_TRACK, 1, 1);
        start(&t, 'C', 0);
        Contest_Update(&t, &f, 0, 0);
        Contest_Update(&t, &f, 350, 0);
        assert(t.motion == MOTION_STOP);
        assert(!t.centered);
        input(&t, 400, 1);
        input(&t, 500, 0);
        input(&t, 600, 0);
        assert(t.motion == MOTION_STOP);
        input(&t, 850, 0);
        assert(t.motion == MOTION_SCAN);
    }
    test_protocol();
    test_scan();
    test_lock();
    test_identity_and_timeouts();
    test_moving();
    test_reacquire();
    puts("14 contest/tracking scenario groups passed");
    return 0;
}
