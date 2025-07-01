// eeprom.cpp

#include "eeprom.h"

//==============================================================
//  1 byte write 
//==============================================================
void writeByteToEEPROM(uint16_t address, uint8_t data) {
    Wire.beginTransmission(EEPROM_ADDRESS | (address >> 8) & 0x07);   // Chip address & High byte of memory address
    Wire.write(address & 0xFF);         // Low byte of memory address
    Wire.write(data);                   // Data to write
    Wire.endTransmission();
    delay(5);  // Delay to ensure data is written
}

//==============================================================
//  1 byte read
//==============================================================
uint8_t readByteFromEEPROM(uint16_t address) {
    Wire.beginTransmission(EEPROM_ADDRESS | ((address >> 8) & 0x07));   // Chip address & High byte of memory address
    Wire.write(address & 0xFF);         // Low byte of memory address
    Wire.endTransmission();

    Wire.requestFrom(EEPROM_ADDRESS, 1);
    if (Wire.available()) {
        return Wire.read();
    }
    return 0;  // Return 0 if no data available
}

//==============================================================
//  2 byte write 
//==============================================================
void writeWordToEEPROM(uint16_t address, uint16_t data) {
    Wire.beginTransmission(EEPROM_ADDRESS | (address >> 8) & 0x07);   // Chip address & High byte of memory address
    Wire.write(address & 0xFF);         // Low byte of memory address
    Wire.write((data >> 8) & 0xFF);     // Write the high byte of the data
    Wire.write(data & 0xFF);            // Write the low byte of the data
    Wire.endTransmission();
    delay(5);  // Delay to ensure data is written
}

//==============================================================
//  2 byte read
//==============================================================
uint16_t readWordFromEEPROM(uint16_t address) {
    uint16_t data = 0;
    Wire.beginTransmission(EEPROM_ADDRESS | ((address >> 8) & 0x07));   // Chip address & High byte of memory address
    Wire.write(address & 0xFF);         // Low byte of memory address
    Wire.endTransmission();

    Wire.requestFrom(EEPROM_ADDRESS, 2);
    if (Wire.available() >= 2) {
        data = (Wire.read() << 8);     // Read the high byte and shift it
        data |= Wire.read();           // Read the low byte and combine
    }
    return data;
}


//==============================================================
//  String data write
//==============================================================
void writeStringToEEPROM(uint16_t address, const String& data) {
    const int pageSize = 16;  // AT24C16 페이지 크기

    for (size_t i = 0; i <= data.length(); i++) {  // include null terminator
        uint16_t currentAddress = address + i;
        uint8_t deviceAddr = EEPROM_ADDRESS | ((currentAddress >> 8) & 0x07);
        uint8_t memAddr = currentAddress & 0xFF;

        // 페이지 경계 또는 첫 바이트일 때 transmission 시작
        if ((currentAddress % pageSize == 0) || (i == 0)) {
            if (i > 0) {
                Wire.endTransmission();
                delay(5);  // EEPROM write delay
            }
            Wire.beginTransmission(deviceAddr);
            Wire.write(memAddr);
        }

        char ch = (i == data.length()) ? '\0' : data[i];  // 마지막에 null 문자 추가
        Wire.write(ch);
    }

    Wire.endTransmission();
    delay(5);  // ensure data write
}




void writeStringToEEPROM_bak(uint16_t address, const String& data) {
    Wire.beginTransmission(EEPROM_ADDRESS | ((address >> 8) & 0x07));      // Chip address & High byte of memory address
    Wire.write(address & 0xFF);         // Low byte of memory address

    for (size_t i = 0; i < data.length(); i++) {
        if ((address + i) % 16 == 0 && i > 0) {  // Page boundary reached
            Wire.endTransmission();
            delay(5);  // Write delay for EEPROM
            Wire.beginTransmission(EEPROM_ADDRESS | ((address >> 8) & 0x07));
            //Wire.write((address + i) >> 8);
            Wire.write((address + i) & 0xFF);
        }
        Wire.write(data[i]);
    }
    Wire.write('\0');  // Null-terminate the string in EEPROM
    Wire.endTransmission();
    delay(5);  // Ensure data is written to EEPROM
}

//==============================================================
//  String data read
//==============================================================
String readStringFromEEPROM(uint16_t address) {
    String result = "";

    uint8_t deviceAddr = EEPROM_ADDRESS | ((address >> 8) & 0x07);
    uint8_t memAddr = address & 0xFF;

    Wire.beginTransmission(deviceAddr);
    Wire.write(memAddr);
    Wire.endTransmission();

    Wire.requestFrom(deviceAddr, 32);  // 32바이트까지 읽고 null 체크로 종료

    while (Wire.available()) {
        char c = Wire.read();
        if (c == '\0') break;
        result += c;
    }
    return result;
}


String readStringFromEEPROM_bak(uint16_t address) {
    String result = "";
    Wire.beginTransmission(EEPROM_ADDRESS | ((address >> 8) & 0x07));   // Chip address & High byte of memory address
    Wire.write(address & 0xFF);         // Low byte of memory address
    Wire.endTransmission();

    Wire.requestFrom(EEPROM_ADDRESS, 16);
    while (Wire.available()) {
        char c = Wire.read();
        if (c == '\0') break;  // Stop at null terminator
        result += c;
    }
    return result;
}