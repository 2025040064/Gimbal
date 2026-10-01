#ifndef __STABILIZER_H
#define __STABILIZER_H

#include "main.h"

extern uint16_t motor1_delay_display;
extern uint16_t motor2_delay_display;

void Stabilizer_Init(void);
void Stabilizer_Update(void);

#endif
