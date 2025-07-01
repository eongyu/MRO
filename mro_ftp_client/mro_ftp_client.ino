//  2025/06/19 
//	csv FTP 전송까지 완료
//	한개의 채널씩 수짐하는 방식
//  Board Manager : esp32  2.0.17
//  ESP32_FTPClient.h Line 17 에 디버깅 설정을 막음
//  http://192.168.0.107/updateConfig?ftp_server=192.168.0.2
//  http://192.168.0.107/updateConfig?ssid=IAE_MRO_2G
//  http://192.168.0.107/updateConfig?password=robotics7607
//  http://192.168.0.107/updateConfig?ftp_user=egkim
//  http://192.168.0.107/updateConfig?ftp_pass=1111

//  http://192.168.0.107/updateConfig?ssid=<newSSID>&password=<newPassword>
//  HTTP를 사용하여 사용자 설정을 변경 하도록 수정함


#include <SPI.h>
#include <WiFi.h>
#include <ESP32_FTPClient.h>
#include <WebServer.h>  // Include WebServer library for HTTP functionality
#include <time.h>
#include <Arduino.h>
#include <esp_task_wdt.h>
//#include "freertos/FreeRTOS.h"
//#include "freertos/task.h"

#include <Wire.h>

#include "global.h"
#include "ad7490.h"
#include "eeprom.h"
#include "NextionLCD.h"

#define USE_DEBUG

#define SAMPLE_COUNT_PER_CHANNEL  30000
#define DATA_BUF_SIZE   (2 * SAMPLE_COUNT_PER_CHANNEL)
uint8_t data_buf[DATA_BUF_SIZE];  // 1채널 전용

#define FTP_PORT		2121		// FTP Port 21-> 2121로 변경, 21은 관리자권한으로 실행
//#define DATA_BUF_SIZE   (2 * 30000)		// 2Byte 
#define WIFI_CONNECT_RETRY_COUNT	10
// Constants and global variables
#define BOARD_ID_MASK   0x03        // 총 4개 사용. 추가시 값을 변경

// FTP client with timeout and retries, Timeout=5000msec, retry=2
//ESP32_FTPClient ftp(ftp_server, ftp_user, ftp_pass, 5000, 2);   
ESP32_FTPClient ftp(ftp_server, FTP_PORT, ftp_user, ftp_pass, 5000, 2);   

// NTP 서버 설정, 인터넷 시간 가져오기 위함
const char* ntpServer = "pool.ntp.org";
const long  gmtOffset_sec =  9 * 3600;	// 한국은 UTC+9 (32400초)
const int   daylightOffset_sec = 0;		// 한국은 서머타임이 없음 

uint8_t currentChannel = 0;  // 0 ~ 3 중 하나 (CH0~CH3)

//uint8_t data_buf[2 * 4 * 3000 ];     // Buffer for ADC data


volatile bool FTP_SendFlag = 0;         // FTP send flag
volatile bool adc_read_flag = 0;        // AD7490 read enabled flag
volatile bool timer_flag = 0;           // 100 msec timer flag
volatile bool timer_10sec_flag = 0;     // 10 sec timer flag
volatile bool Send_Count_flag = 0;      // Send count display flag
uint32_t SendCounter = 1;       // FTP Data Send Counter
char buff[32];      // Buffer for sprintf usage
int adc_Count = 0;
bool NetworkDisconnecttedFlag = 0;      // Network disconnect flag
//
bool debuggingEnabled = false;          // Serial Debugging Command Output
// Timer configuration
hw_timer_t * timer = NULL;
portMUX_TYPE timerMux = portMUX_INITIALIZER_UNLOCKED;

//=======================================
//  Motor Model Name
//=======================================
const char *ModelName[4] = {
	"Main FAN",
	"Purge FAN",
	"Combustion FAN",
	"Rotary Motor"
};
uint8_t Board_id = 0;
#define BOARD_ID_MAX    3
#define nxtSerial   Serial1 // Serial1 as Nextion display serial port

//==============================================================
//  HTTP read/write function
//==============================================================

// HTTP Server on port 80
WebServer server(80);

// Root page handler for displaying current configuration
void handleRoot() {
	server.sendHeader("Access-Control-Allow-Origin", "*");
	String message = "Configuration Page\n\n";
	message += "Current SSID: " + String(ssid) + "\n";
	message += "Current Password: " + String(password) + "\n";
	message += "Server IP: " + String(ftp_server) + "\n";
	message += "Server ID: " + String(ftp_user) + "\n";
	message += "Server Password: " + String(ftp_pass) + "\n";

	server.send(200, "text/plain", message);
}

void handleUpdateConfig() {
	server.sendHeader("Access-Control-Allow-Origin", "*");
	bool updated = false;

	// Check if each parameter is provided and update accordingly
	if (server.hasArg("ssid")) {
		String new_ssid = server.arg("ssid");
		strncpy(ssid, new_ssid.c_str(), sizeof(ssid) - 1);
		ssid[sizeof(ssid) - 1] = '\0';  // Ensure null termination
		updated = true;
	}
	if (server.hasArg("password")) {
		String new_password = server.arg("password");
		strncpy(password, new_password.c_str(), sizeof(password) - 1);
		password[sizeof(password) - 1] = '\0';  // Ensure null termination
		updated = true;
	}
	if (server.hasArg("ftp_server")) {
		String new_server_ip = server.arg("ftp_server");
		strncpy(ftp_server, new_server_ip.c_str(), sizeof(ftp_server) - 1);
		ftp_server[sizeof(ftp_server) - 1] = '\0';  // Ensure null termination
		updated = true;
	}
	if (server.hasArg("ftp_user")) {
		String new_user_ip = server.arg("ftp_user");
		strncpy(ftp_user, new_user_ip.c_str(), sizeof(ftp_user) - 1);
		ftp_user[sizeof(ftp_user) - 1] = '\0';  // Ensure null termination
		updated = true;
	}
	if (server.hasArg("ftp_pass")) {
		String new_pass_ip = server.arg("ftp_pass");
		strncpy(ftp_pass, new_pass_ip.c_str(), sizeof(ftp_pass) - 1);
		ftp_pass[sizeof(ftp_pass) - 1] = '\0';  // Ensure null termination
		updated = true;
	}

	// Save changes to EEPROM only if any parameter was updated
	if (updated) {
		saveConfigToEEPROM(ssid, password, ftp_server, ftp_user, ftp_pass);
		server.send(200, "text/plain", "Configuration updated and saved to EEPROM.");
		ESP.restart();    // ESP32 reset
	} else {
		server.send(400, "text/plain", "No configuration parameters provided.");
	}
}

void startServer() {
	server.on("/", handleRoot);
	server.on("/updateConfig", handleUpdateConfig);
	server.begin();
	//Serial.println("HTTP server started.");
}


//==============================================
//  Timer Interrupt Service : 100 usec
//==============================================
volatile uint16_t TimerCounter1 = 0;
volatile uint32_t TimerCounter2 = 0;
void IRAM_ATTR onTimer(void) 
{
	portENTER_CRITICAL_ISR(&timerMux);
	
	if(adc_read_flag){
		ReadADC();
	}   
	//  100 msec
	TimerCounter1++;
	if(TimerCounter1 >= 1000) {       // 100usec * 1000 = 100msec
		timer_flag = 1;
		TimerCounter1 = 0;
	}   
	if(TimerCounter2 >= 100000) {       // 100usec * 100000 = 10sec
		TimerCounter2 = 0;
		timer_10sec_flag = 1;
	}
	portEXIT_CRITICAL_ISR(&timerMux);
}


//==============================================
//	Timer Interrupt Service 
//  Timer Interrupt setting
//  1000 : 1msec
//==============================================
void TimerInit(uint16_t t_usec) 
{
	timer = timerBegin(0, 80, true);
	timerAttachInterrupt(timer, &onTimer, true);
	timerAlarmWrite(timer, t_usec, true);          // 1000000 = 1sec, 1000 = 1msec
	timerAlarmEnable(timer); 
}

//=========================================================
//  GPIO initialize
//=========================================================
void InitGPIO(void)
{
	// GPIO Direction
	pinMode (adcChipSelectPin, OUTPUT);
	pinMode (WiFiLedPin, OUTPUT);
	pinMode (ServerLedPin, OUTPUT);
	pinMode (LedRedPin, OUTPUT);
	//
	pinMode (ID_DIGIT1, INPUT);
	pinMode (ID_DIGIT2, INPUT);
	pinMode (ID_DIGIT4, INPUT);
	pinMode (ID_DIGIT8, INPUT);
	//
	pinMode (SW1, INPUT);
	pinMode (SW2, INPUT);
	pinMode (SW3, INPUT);
	// set the PORT inititial
	digitalWrite(adcChipSelectPin, HIGH);
	digitalWrite(WiFiLedPin, LED_OFF);
	digitalWrite(ServerLedPin, LED_OFF);
	digitalWrite(LedRedPin, LED_OFF);
}

//===========================================================================
//  Rotary SWITCH의 값을 읽는다
//===========================================================================
uint8_t ReadID(void)
{
	uint8_t id = 0;
	
	if(digitalRead(ID_DIGIT1)) id |= 0x01;
	if(digitalRead(ID_DIGIT2)) id |= 0x02;
#if 0
	if(digitalRead(ID_DIGIT4)) id |= 0x04;
	if(digitalRead(ID_DIGIT8)) id |= 0x08;
#endif 
	displayToLCD("name.txt", ModelName[id & 0x03]);

	return id;    
}

// 현재 시간을 가져오는 함수
String getFormattedTime() 
{
	struct tm timeinfo;
	if (!getLocalTime(&timeinfo)) {
		Serial.println("Failed to obtain time");
		return "00000000_000000";  // 시간을 얻을 수 없을 때 기본 값
	}
	// 형식: YYYYMMDD_HHMMSS
	char timeStr[20];
	strftime(timeStr, sizeof(timeStr), "%Y%m%d_%H%M%S", &timeinfo);

	return String(timeStr);
}

//==========================================================================
//  AD7490 CH0 ~ CH3 데이터를 연속적으로 읽는다.
//==========================================================================
void ReadADC(void)
{
	uint8_t in_buff[2] = {0x00, 0x00};
	
	uint8_t addr = 0;
	int ch=0;

	for(ch=0; ch < MAX_ADC_CH; ch++){
		// SPI Data Read
		in_buff[0] = 0x00;
		in_buff[1] = 0x00;

		digitalWrite(adcChipSelectPin, LOW);
		in_buff[0] = SPI.transfer(0x00);
		in_buff[1] = SPI.transfer(0x00);
		digitalWrite(adcChipSelectPin, HIGH);

		addr = (( in_buff[0] >> 4 ) & 0x03);	// AD7490 채널 확인
		if(currentChannel == addr ){
			data_buf[2 * adc_Count + 0] = ( in_buff[0] & 0x0F);
			data_buf[2 * adc_Count + 1] = ( in_buff[1] );      
		}


	}

	if(adc_Count++ == SAMPLE_COUNT_PER_CHANNEL) {
		adc_Count = 0;
		adc_read_flag = 0;
		FTP_SendFlag = 1;        
	}
}

//===========================================================================
//  Wi-Fi 연결 정보를 LCD에 표시한다.
//===========================================================================
void printWifiStatus(void) 
{
	//
	String currentSSID = WiFi.SSID();
	IPAddress ip = WiFi.localIP();

	displayToLCD("s_ip.txt", ftp_server);  // Display the FTP server IP on the LCD
	delay(10);
	displayToLCD("ssid.txt", ssid);        // Display the SSID on the LCD
	delay(10);
	displayToLCD("ip.txt", WiFi.localIP().toString().c_str());  // Display local IP on the LCD
	delay(10);
}

//===========================================================================
//  Wi-Fi RSSI 값을 LCD에 표시한다.
//===========================================================================
void printWifiStatusRssi(void) 
{   
	long rssi = WiFi.RSSI();
	char strRssi[16];  
	//  
	sprintf(strRssi, "%ld", rssi); // Convert long to C-style string directly.
	displayToLCD("rssi.txt", strRssi);
}

//==================================================
//  sec 에 해당 하는 초로 WDT를 설정한다.
//==================================================
void EnableWatchDog(int sec)
{
	esp_task_wdt_init(sec, true);                      //enable panic so ESP32 restarts
	esp_task_wdt_add(NULL);   
}

void InitAD7490(void)
{
	// SPI 초기화
	SPI.begin(clockPin, misoPin, mosiPin, adcChipSelectPin);

	// --- SPI 설정 시작 ---
	SPI.beginTransaction(SPISettings(10000000, MSBFIRST, SPI_MODE0));

	// Dummy clock 전송 (2회)
	for (int i = 0; i < 2; i++) {
		digitalWrite(adcChipSelectPin, LOW);
		SPI.transfer(0xFF);
		SPI.transfer(0xFF);
		digitalWrite(adcChipSelectPin, HIGH);
	}

	// NOP로 약간의 시간 지연
	for (int i = 0; i < 5; i++) {
		asm volatile("nop");
	}

	// 제어 워드 전송
	unsigned int controlWord = 0b1100111111110000;
	digitalWrite(adcChipSelectPin, LOW);
	SPI.transfer16(controlWord);
	digitalWrite(adcChipSelectPin, HIGH);

	SPI.endTransaction();  // <-- 중요!

	delay(10);
}


void InitAD7490_org(void)
{

	SPI.begin(clockPin, misoPin, mosiPin, adcChipSelectPin);
	// 아래 설정으로 대체
	SPI.beginTransaction(SPISettings(10000000, MSBFIRST, SPI_MODE0));


	
	//Send dummy values over when ADC is turned on
	//Hold Din High for 16 clock cycles twice
	digitalWrite(adcChipSelectPin, LOW);
	SPI.transfer(0xFF);
	SPI.transfer(0xFF);
	digitalWrite(adcChipSelectPin, HIGH);
	
	digitalWrite(adcChipSelectPin, LOW);
	SPI.transfer(0xFF);
	SPI.transfer(0xFF);
	digitalWrite(adcChipSelectPin, HIGH);
	asm volatile("nop");
	asm volatile("nop");
	asm volatile("nop");
	asm volatile("nop");
	asm volatile("nop");
	//Send dummy values, next read should have correct values

	unsigned int controlWord = 0b1100111111110000;  // 12비트 컨트롤 워드
	//  ADC 0 ~ ADC 3 : 4channel  
	digitalWrite(adcChipSelectPin, LOW);
	SPI.transfer16(controlWord);  // 16비트 데이터 전송
	digitalWrite(adcChipSelectPin, HIGH);
	SPI.endTransaction();
	
	delay(10);    
}  

void ConnectToWiFi(void) 
{
	// Wi-Fi 연결 상태 확인
	if (WiFi.status() != WL_CONNECTED) {
		esp_task_wdt_reset();   // WDT reset
		
		// Disconnects the ESP32 from any currently connected Wi-Fi network.
		WiFi.disconnect();      
		
		// Attempts to reconnect the ESP32 to the last Wi-Fi network it was connected to using the previously stored SSID and password.
		WiFi.reconnect();       
		
		WifiConnection(0);

		// 재연결 시도
		int retryCount = 0;
		while (WiFi.status() != WL_CONNECTED && retryCount < WIFI_CONNECT_RETRY_COUNT) {
			delay(200);
			Serial.print(".");
			retryCount++;
		}

		if (WiFi.status() == WL_CONNECTED) {
			WifiConnection(1);      // WiFi Connected
			printWifiStatus();  
			printWifiStatusRssi();
		} 
		else {
				WifiConnection(0);
		}
	}
}


void InitWiFi() {
	// WiFi 연결
	//Serial.print("Connecting to WiFi");
	WiFi.begin(ssid, password);
	int connectCounter = 0;
	while (WiFi.status() != WL_CONNECTED) {
		delay(500);
		connectCounter++;
		if(connectCounter >= 10){
			connectCounter = 0;
			NetworkDisconnecttedFlag = 1;
			EasyNex_writeString("time.txt=\"Network Error\"");
			break;
		}
		Serial.print(".");
	}   
	WifiConnection(1);
	printWifiStatus();
	printWifiStatusRssi();
}

void NtpServerConnect(void)
{
#ifdef USE_NTP_SERVER    

	if(NetworkDisconnecttedFlag == 0) {
		// NTP 시간 동기화 설정. 인터넷 연결이 된 경우 사용
		configTime(gmtOffset_sec, daylightOffset_sec, ntpServer);

		// NTP 서버로부터 시간이 동기화될 때까지 기다림
		struct tm timeinfo;
		while (!getLocalTime(&timeinfo)) {
			if (debuggingEnabled) {
				Serial.println("Waiting for NTP time sync...");
			}
			delay(500);  // 1초 대기 후 다시 시도
		}
		startServer();  // Start HTTP server for configuration updates, 241107
	}

#endif
}
void setup() 
{
	Serial.begin(115200);
	InitGPIO();         // GPIO Initialize
	InitLCD(9600);      // LCD Initialize & Set baud rate, 9600

	//===================================================
	Wire.begin(SDA_PIN, SCL_PIN);  // SDA: 21, SCL: 22 on ESP32

	ReadSwitch();
	InitEEPROM();    

	InitWiFi();

	// Initialize the FTP client with the non-const char array
	ftp = ESP32_FTPClient(ftp_server, ftp_user, ftp_pass, 5000, 2);

	Board_id = (ReadID() & BOARD_ID_MASK);
  
	NtpServerConnect();

	InitAD7490();
	TimerInit(100);             // 1,000-usec = 1kHz, 100 usec = 10kHz
	EnableWatchDog(10);      // WDT Enable, 10sec
	adc_read_flag = 1;
}	


void WifiConnection(bool onoff)
{
	if(onoff){
		EasyNex_WriteValue("led0.bco=", NXT_COLOR_GREEN);
		digitalWrite(WiFiLedPin, LED_ON);
		
	}
	else {
		EasyNex_WriteValue("led0.bco=", NXT_COLOR_RED);
		digitalWrite(WiFiLedPin, LED_OFF);
	}
}

void ServerConnection(bool onoff)
{
	if(onoff){
		digitalWrite(ServerLedPin, LED_ON);
		EasyNex_WriteValue("led1.bco=", NXT_COLOR_GREEN);
	}
	else {
		digitalWrite(ServerLedPin, LED_OFF);
		EasyNex_WriteValue("led1.bco=", NXT_COLOR_RED);
	}
}

bool FTP_ConnectWithRetry(int retryCount, int delayMs) {
	for (int i = 0; i < retryCount; i++) {
		ftp.OpenConnection();
		if (ftp.isConnected()) {
			Serial.println("FTP connected successfully.");
			return true; // 연결 성공
		}
		delay(delayMs); // 재시도 대기
	}
	Serial.println("Failed to connect to FTP server.");
	return false; // 재시도 실패
}
//===================================================================
//  FTP Server와 연결하고 현재 날짜와 시간을 읽어 CSV 파일 이름을 설정
//  센서 데이터를 CSV 로 변환하여 FTP Server 에 전송
//===================================================================
void FTP_Send(void)
{
	const uint16_t chunkSize = 1024;
	String fileName;

	if (!FTP_ConnectWithRetry(3, 2000)) { // 3회 재시도, 2초 간격
		EasyNex_writeString("time.txt=\"FTP Server Unavailable\"");
		return;
	}

	ServerConnection(1);

	// 현재 시간 문자열
	String currentTime = getFormattedTime();

	// CSV 파일 이름 생성
	fileName = "[" + String(ModelName[Board_id]) + "]_CH" + String(currentChannel) + "_" + currentTime + ".csv";

	// FTP 설정
	ftp.InitFile("Type A");                 
	ftp.NewFile(fileName.c_str());

	// CSV 헤더 작성
	String header = "Location : EMSolution\n";
	header += "Position : " + String(ModelName[Board_id]) + "\n";
	header += "Date & Time: " + currentTime + "\n";

	switch(currentChannel & 0x03){
		case 0: header += "Vibration\n"; break;
		case 1: header += "Current R\n"; break;	
		case 2: header += "Current S\n"; break;
		case 3: header += "Current T\n"; break;
	}

	// 헤더 먼저 전송
	ftp.Write(header.c_str());

	// CSV 데이터 전송 (chunk 단위)
	String csvChunk = "";
	for (int i = 0; i < DATA_BUF_SIZE; i += 2) {
		uint16_t value = (data_buf[i] << 8) | data_buf[i + 1];
		csvChunk += String(value) + "\n";

		// chunkSize 넘으면 전송
		if (csvChunk.length() >= chunkSize) {
			ftp.Write(csvChunk.c_str());
			csvChunk = ""; // clear for next chunk
			delay(1);      // yield to WiFi stack
		}
	}

	// 남은 데이터 전송
	if (csvChunk.length() > 0) {
		ftp.Write(csvChunk.c_str());
	}

	// 파일 전송 종료
	ftp.CloseFile();
	ftp.CloseConnection();

	ServerConnection(0);

#ifdef USE_NTP_SERVER
	displayToLCD("time.txt", currentTime.c_str());
#endif

	Send_Count_flag = 1;   // LCD 카운터 표시용
	adc_read_flag = 1;     // 다음 측정 시작 플래그
}



uint8_t sw_data_bak = 0x00;
void ReadSwitch(void)
{
	uint8_t sw_data = 0x00;
	
	// Read SW1
	if(!digitalRead(SW1)) {
		sw_data |= 0x01;
	}
	// Read SW2
	if(!digitalRead(SW2)) {
		sw_data |= 0x02;
	}
	// Read SW3
	if(!digitalRead(SW3)) {
		sw_data |= 0x04;
	}
	sw_data &= 0x07;    // Switch Mask
	   
	if( sw_data != sw_data_bak) {
		switch(sw_data){
			case 0x00:
				break;
			case 0x01:
				break;
			case 0x02:
				break;
			case 0x03:
				break;    
			case 0x04:
				break;
			case 0x05:
				break;
			case 0x06:
				break;
			case 0x07:
				saveConfigToEEPROM(ssid, password, ftp_server, ftp_user, ftp_pass);
				writeWordToEEPROM(EEP_ID_ADDR, EEP_DEFAULT_ID);   
				writeByteToEEPROM(EEP_DEBUG_ADDR, debuggingEnabled );
				break;
		}
		sw_data_bak = sw_data;
	}
}

//====================== EEPROM Configuration ======================
// Initializes EEPROM configuration, loads or saves as needed
void InitEEPROM()
{
	uint16_t id = readWordFromEEPROM(EEP_ID_ADDR);
	char temp[50];


	if( id != EEP_DEFAULT_ID ) 
	{
		Serial.println("id mismatch");
		saveConfigToEEPROM(ssid, password, ftp_server, ftp_user, ftp_pass);
		writeWordToEEPROM(EEP_ID_ADDR, EEP_DEFAULT_ID);   
		writeByteToEEPROM(EEP_DEBUG_ADDR, debuggingEnabled );     
	}
	// Load configuration from AT24C16 EEPROM
	loadConfigFromEEPROM(ssid, password, ftp_server, ftp_user, ftp_pass);
	debuggingEnabled = readByteFromEEPROM(EEP_DEBUG_ADDR );  

#if 0
	sprintf(temp, "%s", ssid);
	Serial.println(temp);
	sprintf(temp, "%s", password);
	Serial.println(temp);
	sprintf(temp, "%s", ftp_server);
	Serial.println(temp);
	sprintf(temp, "%s", ftp_user);
	Serial.println(temp);
	sprintf(temp, "%s", ftp_pass);
	Serial.println(temp);
#endif	
}

// Saves configuration to EEPROM
void saveConfigToEEPROM(const char* ssid, const char* password, const char* serverIP, const char* ftp_user, const char* ftp_pass) {
	writeStringToEEPROM(EEP_SSID_ADDR, String(ssid));
	writeStringToEEPROM(EEP_PASSWORD_ADDR, String(password));
	writeStringToEEPROM(EEP_SERVER_IP_ADDR, String(serverIP));
	writeStringToEEPROM(EEP_SERVER_SSID_ADDR, String(ftp_user));
	writeStringToEEPROM(EEP_SERVER_PASS_ADDR, String(ftp_pass));
	//
	if(debuggingEnabled) {
		Serial.println("Configuration saved to EEPROM.");
		
		// Print the saved configuration for verification
		Serial.print("SSID: ");         Serial.println(ssid);
		Serial.print("Password: ");     Serial.println(password);
		Serial.print("Server IP: ");    Serial.println(serverIP);
		Serial.print("Server ID: ");    Serial.println(ftp_user);
		Serial.print("Server Password: ");    Serial.println(ftp_pass);
	}
}

// Loads configuration from EEPROM
void loadConfigFromEEPROM(char* ssid, char* password, char* serverIP, char* ftp_user, char* ftp_pass) {
	String tempSSID = readStringFromEEPROM(EEP_SSID_ADDR);
	Serial.print("TEMP SSID = "); Serial.println(tempSSID);
	String tempPassword = readStringFromEEPROM(EEP_PASSWORD_ADDR);
	String tempServerIP = readStringFromEEPROM(EEP_SERVER_IP_ADDR);
	String tempFtpID = readStringFromEEPROM(EEP_SERVER_SSID_ADDR);
	String tempFtpPass = readStringFromEEPROM(EEP_SERVER_PASS_ADDR);

	// Ensure the strings fit into the provided char arrays and copy them
	tempSSID.toCharArray(ssid, 32);             // 공유기 SSID
	tempPassword.toCharArray(password, 32);     // 공유기 Password
	tempServerIP.toCharArray(serverIP, 32);     // FTP Server IP
	tempFtpID.toCharArray(ftp_user, 16);        // FTP User
	tempFtpPass.toCharArray(ftp_pass, 16);      // FTP Password

	if(debuggingEnabled) {
		Serial.println("Configuration loaded from EEPROM.");
		Serial.print("SSID: ");     Serial.println(ssid);
		Serial.print("Password: ");     Serial.println(password);
		Serial.print("Server IP: ");    Serial.println(serverIP);
		Serial.print("Server ID: ");    Serial.println(ftp_user);
		Serial.print("Server Password: ");    Serial.println(ftp_pass);
	}
}

void sendConfigToSerial() {
	Serial.println("SSID:" + String(ssid));
	Serial.println("Password:" + String(password));
	Serial.println("FTP Server:" + String(ftp_server));
	Serial.println("FTP User:" + String(ftp_user));
	Serial.println("FTP Password:" + String(ftp_pass));
	if(debuggingEnabled){
		Serial.println("DEBUG:ENABLE");
	}
	else {
		Serial.println("DEBUG:DISABLE");
	}
}

void handleSerialInput() {
	if (Serial.available()) {
		String command = Serial.readStringUntil('\n');
		command.trim();

		if (command == "READ_CONFIG") {
			sendConfigToSerial();
		} else if (command.startsWith("SSID:")) {
			command.substring(5).toCharArray(ssid, 32);
			writeStringToEEPROM(EEP_SSID_ADDR, String(ssid));
			//Serial.println(ssid);
		} else if (command.startsWith("PASS:")) {
			command.substring(5).toCharArray(password, 32);
			writeStringToEEPROM(EEP_PASSWORD_ADDR, String(password));
		} else if (command.startsWith("FTP_IP:")) {
			command.substring(7).toCharArray(ftp_server, 32);
			writeStringToEEPROM(EEP_SERVER_IP_ADDR, String(ftp_server));
		} else if (command.startsWith("FTP_USER:")) {
			command.substring(9).toCharArray(ftp_user, 16);
			writeStringToEEPROM(EEP_SERVER_SSID_ADDR, String(ftp_user));
		} else if (command.startsWith("FTP_PASS:")) {
			command.substring(9).toCharArray(ftp_pass, 16);
			writeStringToEEPROM(EEP_SERVER_PASS_ADDR, String(ftp_pass));
		} else if (command == "DEBUG:ENABLE") {
			debuggingEnabled = true;
			writeByteToEEPROM(EEP_DEBUG_ADDR, 0x01);
		} else if (command == "DEBUG:DISABLE") {
			debuggingEnabled = false;
			writeByteToEEPROM(EEP_DEBUG_ADDR, 0x00);
		} else if (command == "ADC:START") {
			adc_read_flag = true;
			adc_Count = 0;
		} else if (command == "ADC:STOP") {
			adc_read_flag = false;
			adc_Count = 0;
		}
	}
}


//====================== Main Loop ======================
void loop(void) 
{
	esp_task_wdt_reset();   // Reset watchdog timer

	ConnectToWiFi();        // Check Wi-Fi connection

	handleSerialInput(); 	// Serial 입력 처리

	if(FTP_SendFlag && (NetworkDisconnecttedFlag == 0) ) {
		FTP_Send();
		FTP_SendFlag = 0;
		currentChannel++;
		if(currentChannel >= 4){
			currentChannel=0;
		}
	}

	
	//  100 msec timer interrupt
	if(timer_flag) {
		timer_flag = 0;
		ReadSwitch();
		server.handleClient();   // Handle HTTP server requests,
		//  FTP Data Send Count Display
		if(Send_Count_flag){
			displayToLCDValue("n0.val", SendCounter++);
			Send_Count_flag = 0;
		}
	}
	//	매 10초 마다 WiFi 의 상태를 체크한다.
	if(timer_10sec_flag) {
		printWifiStatusRssi();
		timer_10sec_flag = 0;
	}
	  
	delay(1);       // delay 1msec
}


