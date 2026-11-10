#include "stabilizer.h"
#include <assert.h>
#include <stdio.h>

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
    assert(t.state == TASK_DONE && t.hold_ms == 5000);
    start(&t, 'B', 0);
    for (n = 0; n <= 15000; n += 200) input(&t, n, 0);
    assert(t.state == TASK_TIMEOUT);
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

int main(void)
{
    test_protocol();
    test_scan();
    test_lock();
    test_identity_and_timeouts();
    test_moving();
    test_reacquire();
    puts("6 contest scenario groups passed");
    return 0;
}
