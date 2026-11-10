#ifndef K230_H
#define K230_H

#include <stdint.h>

enum { VISION_IDLE, VISION_SCAN, VISION_TRACK, VISION_FAULT, VISION_LEGACY };

typedef struct {
    int16_t width, height, x, y, box_w, box_h;
    uint16_t ids;
    uint8_t mode;
    int8_t id;
    uint16_t sequence;
} VisionFrame;

int K230_Parse(const char *line, VisionFrame *out);
void K230_Init(void);
int K230_Read(VisionFrame *out);
int K230_Send(const char *command);

#endif
