// sampling 시간을 결정
#define TIMER_1msec     1000000UL
#define TIMER_500usec   500000UL
#define TIMER_INTERRUPT_INTERVAL TIMER_1msec
//  Register 1
/* Write control register */
#define WRITE                      (1 << 7)
/* Write control register */
#define SEQ                        (1 << 6)
/* Address2 control register */
#define ADD3                       (1 << 5)
/* Address2 control register */
#define ADD2                       (1 << 4)
/* Address2 control register */
#define ADD1                       (1 << 3)
/* Address2 control register */
#define ADD0                       (1 << 2)
/* Normal operation power mode */
#define PM1                        (1 << 1)
/* Normal operation power mode */
#define PM0                        (1 << 0)

//  Register 2
/* Access to the shadow register */
#define SHADOW                     (1 << 7)
/* DOUT line state, weakly driven or three-state */
#define WEAK_TRI                   (1 << 6)
/* Analog input range from 0 to REF_IN volts  */
#define RANGE                      (1 << 5)
/* Output conversion is straight binary */
#define CODING                     (1 << 4)

/* Control Register */
#define NORMAL_CONTROL_REGISTER1    ( WRITE | SEQ | ADD1 | ADD0| PM1 | PM0 )
#define NORMAL_CONTROL_REGISTER2    ( SHADOW | WEAK_TRI | CODING)

/* The ADC will ignore the write of this control register */
#define NO_WRITE_CONTROL_REGISTER  0x000
/* Bit position of the channel number in the control register */
#define CHANNEL_NUMBER_POSITION    6

#define LED_ON      1       // LED ON
#define LED_OFF     0       // LED OFF

// Nextion LCD Color
#define NXT_COLOR_BLACK 0x0000
#define NXT_COLOR_RED   0xF800
#define NXT_COLOR_GREEN 0x07E0
#define NXT_COLOR_BLUE  0x001F
#define NXT_COLOR_WHITE 0xFFFF

#define NXT_STX     'S'     // Nextion STX
#define NXT_ETX     'P'     // Nextion ETX

#define SEND_MAX_COUNT  20

#define RXD 12
#define TXD 13

#define ID_DIGIT1   36
#define ID_DIGIT2   39
#define ID_DIGIT4   34
#define ID_DIGIT8   35

#define BAUDRATE2 9600
#define Device_ID 0x01

// Set Constants, GPIO
const int adcChipSelectPin = 5;     // set pin 8 as the chip select for the ADC:

const int LedRedPin = 27;            // LED2, Operating LED
const int WiFiLedPin = 14;          // LED0, WiFi Connect LED
const int ServerLedPin = 12;         // LED1, Server Connected LED

const int SW1 = 32;
const int SW2 = 33;
const int SW3 = 25;
//const int SW4 = 26;

//const int csPin = 5; // CS (Chip Select) 핀
const int clockPin = 18; // SCK (Clock) 핀
const int mosiPin = 23; // MOSI (Master Out Slave In) 핀
const int misoPin = 19; // MISO (Master In Slave Out) 핀

const int RXD2 = 16;
const int TXD2 = 17;
//
#define USE_NTP_SERVER          // NTP Server 사용, 막으면 RTC 사용
#define IAE_MOBILE_LAB          // 고기원 내부 공유기 사용

// WiFi 설정, ssid & password
#ifdef IAE_MOBILE_LAB
//char ssid[32] = "IAE_ROBOT_LAB_2G";      // WiFi SSID
#else
char ssid[32] = "IAE_MRO_2G";      // WiFi SSID
#endif

//char ssid[32] = "IAE_MRO_2G";      // WiFi SSID
char password[32] = "robotics7607";   // WiFi 비밀번호

// FTP 서버 설정, server ip, user id, password
#ifdef IAE_MOBILE_LAB
//char ftp_server[32] = "192.168.0.2"; // FTP 서버의 IP 주소 (Ubuntu 서버 IP)
#else
//char ftp_server[32] = "192.168.0.2"; // FTP 서버의 IP 주소 (Ubuntu 서버 IP)
#endif
char ssid[32] = "IAE_ROBOT_LAB_2G";      // WiFi SSID
char ftp_server[32] = "192.168.0.2"; // FTP 서버의 IP 주소 (Ubuntu 서버 IP)
char ftp_user[16] = "egkim";    // FTP 사용자 이름
char ftp_pass[16] = "1111";    // FTP 비밀번호