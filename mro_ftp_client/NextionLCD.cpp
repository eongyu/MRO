// NextionLCD.cpp

#include "NextionLCD.h"

//extern char buff[32];

void InitLCD(uint16_t baud) {
    Serial2.begin(baud, SERIAL_8N1, RXD2, TXD2);  // Initialize Serial2 for Nextion LCD
    delay(10);
    EasyNex_writeString("rest");  // Send reset command to Nextion LCD
    delay(10);
}

void EasyNex_WriteValue(const char * data, uint16_t value) {
    uint8_t endData[3] = {0xFF, 0xFF, 0xFF};  // Nextion requires these end bytes
    
    while (*data) {
        Serial2.print(*data++);
    }
    Serial2.print(String(value));
    Serial2.write(endData, 3);
    Serial2.flush();
}

void EasyNex_writeString( char * data) {
    uint8_t endData[3] = {0xFF, 0xFF, 0xFF};  // Nextion requires these end bytes
    
    while (*data) {
        Serial2.print(*data++);
    }
    Serial2.write(endData, 3);
    Serial2.flush();
}

void displayToLCD(const char* element, const char* content) {
    char buff[64];  // Buffer to hold the formatted string, adjust size if needed
    sprintf(buff, "%s=\"%s\"", element, content);  // Format the command
    EasyNex_writeString(buff);  // Send the command to the LCD
}

// Overloaded function to display an integer value to the LCD
void displayToLCDValue(const char* element, int value) {
    char buff[64];  // Buffer for formatted string
    sprintf(buff, "%s=%d", element, value);
    EasyNex_writeString(buff);
}