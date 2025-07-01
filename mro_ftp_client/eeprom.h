// NextionLCD.h

#ifndef AT24C16_EEPROM_H
#define AT24C16_EEPROM_H

#include <Arduino.h>
#include <Wire.h>

// I2C
#define EEPROM_ADDRESS 0x50  // AT24C16 I2C address
#define SDA_PIN 21           // SDA pin for ESP32
#define SCL_PIN 22           // SCL pin for ESP32

//==============================================================
//	EEPROM Address
//==============================================================
#define EEP_ID_ADDR           	0x10		// 2-bytes
	#define EEP_DEFAULT_ID				0xAAA5
#define EEP_DEBUG_ADDR  				0x12		// 1-byte	
#define EEP_SSID_ADDR         	0x20		// 32-bytes
#define EEP_PASSWORD_ADDR     	0x40		// 32-bytes
#define EEP_SERVER_IP_ADDR    	0x60		// 32-bytes, FTP Server Address
#define EEP_SERVER_SSID_ADDR   	0x80		// 16-bytes. FTP Login ID
#define EEP_SERVER_PASS_ADDR   	0x90		// 16-bytes, FTP Login Password

void writeByteToEEPROM(uint16_t address, uint8_t data);
uint8_t readByteFromEEPROM(uint16_t address);
void writeWordToEEPROM(uint16_t address, uint16_t data);
uint16_t readWordFromEEPROM(uint16_t address);
void writeStringToEEPROM(uint16_t address, const String& data);
String readStringFromEEPROM(uint16_t address);
void loadConfigFromEEPROM(char* ssid, char* password, char* serverIP, char* ftp_user, char* ftp_pass);

#endif // AT24C16_EEPROM_H
