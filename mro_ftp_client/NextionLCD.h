// NextionLCD.h

#ifndef NEXTION_LCD_H
#define NEXTION_LCD_H

#include <Arduino.h>

// Pin definitions for RX and TX (replace with actual pins if different)
#define RXD2    16
#define TXD2    17

void InitLCD(uint16_t baud);
void EasyNex_WriteValue(const char * data, uint16_t value);
void EasyNex_writeString( char * data);
void displayToLCD(const char* element, const char* content);
void displayToLCDValue(const char* element, int value);
#endif // NEXTION_LCD_H
