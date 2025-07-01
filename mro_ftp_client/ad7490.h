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


#define MAX_ADC_CH      4
#define MAX_ADC_BUFF    3000

#define RXD 12
#define TXD 13

//
#define LED0        12
#define LED1        0
#define LED2        4

#define ID_DIGIT1   36
#define ID_DIGIT2   39
#define ID_DIGIT4   34
#define ID_DIGIT8   35