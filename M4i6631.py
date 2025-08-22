"""
Python class to interface with the Spectrum SPCM library. Essentially a wrapper to simplify
use and write common routines as functions.

Based on a combination between code written in the group and the following github repository:
https://github.com/vuthalab/spectrum-awg/blob/master/M4i6622.py

For details on card operation, refer to the manual:
https://spectrum-instrumentation.com/dl/m4i_m4x_66xx_96xx_manual_english.pdf
"""
import numpy
import time
import json
import os
import ctypes

from spcm_tools import *
from pyspcm import *
from enum import IntEnum
from logger_config import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)

class M4i6631:
    def __init__(self, address=b'/dev/spcm0', channelNum=2, sampleRate=500,
                 referenceClock=True, referenceClockFrequency=100e06,
                 clockOut=False,
                 wf_params_default=None, f_res_desired=100):

        """
        address: location of the card on the computer, default is /dev/spcm0
        channelNum: Number of channels used on the card, default is 2
        sampleRate: Sample Rate in Mega Samples per second (MS/s) default is 1250, the maximum for an M4i.66xx card
        referenceClock: True if external clock is supplied. Default if True
        referenceClockFrequency: Frequency of the reference clock (in Hz), by default is 10 MHz.
        clockOut: If you want a clock output from the M4i. By default is False.

        Reference clock frequencies can only go from 10 MHz to 1.25GHz, but cannot be between 750 to 757 MHz and 1125 to 1145 MHz
        """
        # Populate object variables
        self.channel_number = channelNum
        self.sample_rate = sampleRate # MS/s
        self.ext_clock_freq = referenceClockFrequency
        # Hardware-defined parameters - are assigned a proper value later in the code
        self.max_adc_value = None
        # Waveform parameters
        self.f_res_desired = f_res_desired  # Desired frequency resolution
        self.f_res_set = None
        self.output_waveform_params = {}  # Dictionary with tone parameters
        self.current_segment = 0 # Current memory segment in use - we will switch between segment 0 and 1
        # Buffers
        self.pvBuffer = None
        self.pnData = None
        # Derived parameters
        self.sequence_data_len_samples = None
        self.data_transfer_buffer_size_bytes = None

        self.hCard = spcm_hOpen(create_string_buffer(address))
        if self.hCard is None:
            logger.error("no card found...\n")
            exit(1)
        self.channelNum = channelNum

        # Reset the card - sets all registers to default values. The action is as if you just pressed "On" button
        # somewhere on the card.
        dwErr = spcm_dwSetParam_i32(self.hCard, SPC_M2CMD, M2CMD_CARD_RESET)
        if dwErr != ERR_OK:
            spcm_dwSetParam_i32(self.hCard, SPC_M2CMD, M2CMD_CARD_STOP)
            logger.error("... Error: {0:d}\n".format(dwErr))
            exit(1)

        # Read card type, it's function and serial number and check for D/A card
        self.lCardType = int32(0)
        spcm_dwGetParam_i32(self.hCard, SPC_PCITYP, byref(self.lCardType))
        self.lSerialNumber = int32(0)
        spcm_dwGetParam_i32(self.hCard, SPC_PCISERIALNO, byref(self.lSerialNumber))
        self.lFncType = int32(0)
        spcm_dwGetParam_i32(self.hCard, SPC_FNCTYPE, byref(self.lFncType))

        # I have no fucking clue why this parameter is 6, but it's this way in Spectrum programming examples,
        # so I will not challenge it. It is, however, specific to M4i.66xx cards, or so it seems.
        self.dwFactor = uint32(6)

        max_adc_value = int32(0)
        spcm_dwGetParam_i32(self.hCard, SPC_MIINST_MAXADCVALUE, byref(max_adc_value))
        self.max_adc_value = max_adc_value.value

        # Check if the card itself is valid
        card_valid = self.checkCard()
        if not card_valid:
            exit(1)

        self.setup_channels(self.channel_number)
        self.configure_ref_clock(referenceClock, self.ext_clock_freq)
        self.set_sample_rate(self.sample_rate)
        self.set_clock_output(clockOut)

        # Populate data buffer and AWG memory with default tone parameters
        if wf_params_default is None: # If not externally supplied
            wf_params_default = {
                0: { # Channel 0 index
                    0: { # Tone 0 index
                        "Frequency, Hz": 50e06, # Tone parameters
                        "Amplitude, V": 0.1,
                        "Phase, rad": 0
                    }
                },
                1: { # Channel 1 index
                    0: { # Tone 0 index
                        "Frequency, Hz": 50e06, # Tone parameters
                        "Amplitude, V": 0.1,
                        "Phase, rad": 0
                    }
                }
            }
        self.generate_data(wf_params_default)
        self.populate_awg_buffer()
        # self.card_turn_on()

    def handle_error(self):
        """
        Helper function for more detailed error handling. Normally, one would just check if spcm function executed normally
        by comparing its returned value against ERR_OK, but this does not give a lot of information if an error actually
        occurs. More details about error handling is in the manual, section error handling is specific to the board.
        :return: Error code
        """

        dwErrorReg = uint32(0)
        lErrorValue = int32(0)
        errText = ctypes.create_string_buffer(1000)
        ptrErrText = cast(addressof(errText), ptr16)
        # This function just gets the last error that occurred during running the AWG board
        dwErrorCode = spcm_dwGetErrorInfo_i32(self.hCard, dwErrorReg, lErrorValue, ptrErrText)
        if dwErrorCode:
            logger.error("\n")
            logger.error(f"ERROR: CODE {dwErrorCode}, REGISTER: {dwErrorReg.value}, VALUE: {lErrorValue}")
            logger.error(f"ERROR MESSAGE: {errText.value}\n")
        else:
            logger.info("Function executed normally")
        return dwErrorCode

    def initialize_waveform_buffers(self, f_res_desired):
        """
        Initialize output multiple-tone waveform buffers.
        :param f_res_desired: Desired frequency resolution of the output tones
        :return: None
        """
        # We need to define two buffers, one for generating AWG output data, and one for data transfer to the board.
        # The AWG data buffer length determines fundamental frequency of the waveform we can generate, ie frequency
        # resolution, such that f_min = f_sampling/buffer_length_samples. Data buffer for 2 channels has a minimum
        # value of 192 samples/channel, maximum value of Tot_mem//2/maximum_segments_number, and step of 32.
        self.f_res_desired = f_res_desired

        # Here I have to use a few facts. First, f_res = sample_rate//data_buffer_length. Then, data buffer
        # length itself is always defined as dwFactor*N, where N has to be an integer multiple of 32.
        # Of course, I have to round everything to the nearest integer number.
        buffer_size_closest = int(self.sample_rate*1e06/self.f_res_desired * 1/self.dwFactor.value * 1/32)
        self.sequence_data_len_samples = int(buffer_size_closest * self.dwFactor.value * 32) # PER CHANNEL
        # Buffer length in bytes - 2* because data is in 16-bit format, which is 2 bytes per sample. TOTAL, NOT PER CHANNEL
        self.data_transfer_buffer_size_bytes = int(2 * self.sequence_data_len_samples * self.channel_number)
        # Resulting frequency resolution will not be exactly equal to the one we tried to set because of the rounding
        self.f_res_set = self.sample_rate*1e06//self.sequence_data_len_samples

        logger.info(f"Frequency Resolution: requested {self.f_res_desired} Hz, set to {self.f_res_set} Hz")
        logger.info(f"Buffer size: {buffer_size_closest} * 6 * 32")

        # Allocate buffer for the generated waveforms
        self.pvBuffer = pvAllocMemPageAligned(self.data_transfer_buffer_size_bytes)
        # Create a variable stored at the address of the allocated memory buffer
        self.pnData = cast(addressof(self.pvBuffer), ptr16)

        return None

    def setup_channels(self, channelNum=2):
        """
        Configures AWG channels for repeated sequential output. Number of channels is always 2, but I leave the
        parameter here in case it changes in the future.
        :param channelNum: Number of channels used on the card, default is 2
        :return: None
        """
        # Setup output mode to repeated sequence output
        llChEnable = int64(CHANNEL0)
        lMaxSegments = int32(32)
        dwErr = spcm_dwSetParam_i32(self.hCard, SPC_CARDMODE, SPC_REP_STD_SEQUENCE)
        spcm_dwSetParam_i64(self.hCard, SPC_CHENABLE, CHANNEL0 | CHANNEL1)
        spcm_dwSetParam_i32(self.hCard, SPC_SEQMODE_MAXSEGMENTS, 2)

        # Setup trigger - use software trigger only
        spcm_dwSetParam_i32(self.hCard, SPC_TRIG_ORMASK, SPC_TMASK_SOFTWARE)  # software trigger
        spcm_dwSetParam_i32(self.hCard, SPC_TRIG_ANDMASK, 0)
        spcm_dwSetParam_i32(self.hCard, SPC_TRIG_CH_ORMASK0, 0)
        spcm_dwSetParam_i32(self.hCard, SPC_TRIG_CH_ORMASK1, 0)
        spcm_dwSetParam_i32(self.hCard, SPC_TRIG_CH_ANDMASK0, 0)
        spcm_dwSetParam_i32(self.hCard, SPC_TRIG_CH_ANDMASK1, 0)
        spcm_dwSetParam_i32(self.hCard, SPC_TRIGGEROUT, 0)

        # Setup the channels
        # Get total number of channels recognized by the software
        lNumChannels = int32(0)
        spcm_dwGetParam_i32(self.hCard, SPC_CHCOUNT, byref(lNumChannels))
        # Set the channel properties - enable_out, maximum amplitude and what to do after output is stopped (?)
        spcm_dwSetParam_i32(self.hCard, SPC_ENABLEOUT0, 1)
        spcm_dwSetParam_i32(self.hCard, SPC_AMP0, 1000)
        spcm_dwSetParam_i32(self.hCard, SPC_CH0_STOPLEVEL, SPCM_STOPLVL_HOLDLAST)
        spcm_dwSetParam_i32(self.hCard, SPC_ENABLEOUT1, 1)
        spcm_dwSetParam_i32(self.hCard, SPC_AMP1, 1000)
        spcm_dwSetParam_i32(self.hCard, SPC_CH1_STOPLEVEL, SPCM_STOPLVL_HOLDLAST)

        # Setup GPIO (X0) port to async output - it's used to output trigger for data acquisition
        spcm_dwSetParam_i32(self.hCard, SPCM_X0_MODE, SPCM_XMODE_ASYNCOUT)  # Set X0 to ASYNC_OUT
        spcm_dwSetParam_i32(self.hCard, SPCM_XX_ASYNCIO, 0)  # Set output to 0

    def configure_ref_clock(self, useExternalRefClock=True, referenceClockFrequency=100e06):
        """
        Configures reference clock. From Spectrum knowledge base: "Accurate digitizing of a signal requires the
        digitizer's sample rate should be at least five to ten times the required bandwidth". Bandwidth = maximum
        output frequency.
        :param useExternalRefClock: Boolean, whether the AWG uses externally supplied clock
        :param referenceClockFrequency: Frequency of external clock
        :return: 0 if success, 1 if failure
        """
        # Configure the reference clock (if required)
        logger.info("Sample Rate has been set.\n")
        if useExternalRefClock:
            spcm_dwSetParam_i32(self.hCard, SPC_CLOCKMODE, SPC_CM_EXTREFCLOCK)  # Set to reference clock mode
            spcm_dwSetParam_i32(self.hCard, SPC_REFERENCECLOCK,
                                int(referenceClockFrequency))  # Reference clock that is fed in at the Clock Frequency
            dwErrorCode = self.handle_error()
            if dwErrorCode:
                logger.error(f"Error in configuring clock")
                return 1
            else:
                logger.info("Clock has been set\n")
                return 0
        else:
            logger.error("The card is supposed to always use external clock\n")
            return 1 # Because this should never happen

    def checkExternalClock(self):
        '''
        Checks to see if the external clock is working.
        '''

        if spcm_dwSetParam_i32(self.hCard, SPC_M2CMD,
                               M2CMD_CARD_START | M2CMD_CARD_ENABLETRIGGER) == ERR_CLOCKNOTLOCKED:
            logger.error("External clock not locked. Please check connection\n")
            return False
        else:
            logger.info("External clock locked.\n")
            return True

    def set_sample_rate(self, sampleRate):
        """
        Sets the card sampling rate
        :param sampleRate: Sampling rate in MS/s. For M4i6631 card maximum is 1250 MS/s
        :return: 0 if sampling rate set successfully, otherwise 1
        """
        # Set the Sample Rate
        self.SampleRate = MEGA(int(sampleRate)) # Just to make sure that we have the correct number stored
        if ((self.lCardType.value & TYP_SERIESMASK) == TYP_M4IEXPSERIES) or (
                (self.lCardType.value & TYP_SERIESMASK) == TYP_M4XEXPSERIES):
            spcm_dwSetParam_i64(self.hCard, SPC_SAMPLERATE, self.SampleRate)
            dwErrorReg = uint32(0)
            lErrorValue = int32(0)
            errText = ctypes.create_string_buffer(1000)
            ptrErrText =  cast(addressof(errText), ptr16)
            dwErrorCode = spcm_dwGetErrorInfo_i32(self.hCard, dwErrorReg, lErrorValue, ptrErrText)
            if dwErrorCode:
                logger.error(f"ERROR HERE: CODE {dwErrorCode}, REGISTER: {dwErrorReg.value}, VALUE: {lErrorValue} \n")
                logger.error(f"ERROR MESSAGE: {errText.value}")
            logger.info("Sample Rate has been set.\n")
            return 0
        else:
            spcm_dwSetParam_i64(self.hCard, SPC_SAMPLERATE, MEGA(1))
            logger.error(
                "ERROR: Sample Rate failed to be set. Make sure that the sample rate is under 1250 Mega Samples/s and is an integer number\n")
            return 1


    def set_clock_output(self, clockOut):
        """
        Sets if the card should output its clock
        :param clockOut: True if clock should be output, False otherwise
        :return: None
        """
        # Set the clock output
        if clockOut:
            spcm_dwSetParam_i32(self.hCard, SPC_CLOCKOUT, 1)
            logger.info("Clock Output On.\n")
        else:
            spcm_dwSetParam_i32(self.hCard, SPC_CLOCKOUT, 0)
            logger.info("Clock Output Off.\n")

    def checkCard(self):
        """
        Function that checks if the card used is indeed an M4i.6631-x8 or is compatible with Analog Output.
        """

        # Check if Card is connected
        if self.hCard is None:
            logger.error("no card found...\n")
            return False

        # Getting the card Name to check if it's supported.
        try:
            sCardName = szTypeToName(self.lCardType.value)
            if self.lFncType.value == SPCM_TYPE_AO:
                logger.info("Found: {0} sn {1:05d}\n".format(sCardName, self.lSerialNumber.value))
                return True
            else:
                logger.error("Code is for an M4i.6631 Card.\nCard: {0} sn {1:05d} is not supported.\n".format(sCardName,
                                                                                                       self.lSerialNumber.value))
                return False

        except:
            dwError = spcm_dwSetParam_i32(self.hCard, SPC_M2CMD,
                                          M2CMD_CARD_START | M2CMD_CARD_ENABLETRIGGER | M2CMD_CARD_WAITREADY)
            logger.error(dwError)
            logger.error("Problem occured, mb")



    def configure_sequence_step(self, step_index, next_step_index, segment_index, num_loops=1, segment_flags=0):
        """
        For details on Sequence Replay Mode of AWG operation, refer to page 148 of the manual, link at the top of the page.
        This is a helper function to configure each step of the replay sequence. A step with index STEP_INDEX will replay
        data from the memory segment with index SEGMENT_INDEX until the condition specified in SEGMENT_FLAGS. While
        replaying the loop, the software will check if the condition SEGMENT_FLAGS is met every NUM_LOOPS loops. Then
        the sequence will proceed to the step with index next_step_index.

        :param step_index: Index of the current step in the sequence
        :param next_step_index: Index of the next step in the sequence
        :param segment_index: Index of memory segment associated with the current step
        :param num_loops: How frequently the termination condition validity is checked
        :param segment_flags: Condition to end the replay of the current step - 0 is
        :return: None
        """
        logger.info(f"Configuring sequence step {step_index}")
        qwSequenceEntry = uint64(0)     # Sequence step configuration register, 64 bit
        # setup register value
        ### I would like to comment this particular line. Again, for details on how this SUPPOSED to work I refer to the
        ### manual. For some fucking reason, instead of just configuring register with segment_flags variable, they
        ### decided to do whatever the fuck they do below. I emailed spectrum-instruments support, and they said that
        ### since they don't have a dedicated bit mask for flags, they just invert loop mask, but then again, why.
        ### The two approaches give the exact same register tuning word.
        ### How a normal human being would write it:
        # qwSequenceEntry = segment_flags | (num_loops & SPCSEQ_LOOPMASK)
        qwSequenceEntry = (segment_flags & ~SPCSEQ_LOOPMASK) | (num_loops & SPCSEQ_LOOPMASK)
        ###
        qwSequenceEntry <<= 32
        qwSequenceEntry |= ((next_step_index << 16) & SPCSEQ_NEXTSTEPMASK) | (
                    int(segment_index) & SPCSEQ_SEGMENTMASK)

        spcm_dwSetParam_i64(self.hCard, SPC_SEQMODE_STEPMEM0 + step_index, int64(qwSequenceEntry))
        dwError = self.handle_error()
        if dwError:
            logger.error(f"Error configuring sequence step {step_index}: {dwError}")

    def generate_data(self, output_wf_params : dict):
        """
        Generate waveform to output from the AWG and transfer to the board memory.
        :param output_wf_params: Dictionary. Format: {Channel number: {0: {"Frequency, Hz": frequency, "Amplitude, V": amplitude, "Phase, rad": phase}}, ...},
                                 i.e. keys of the dictionaries are channel numbers (0 or 1 in this case), and the values are
                                 dictionaries with the tone parameters. In the tone parameter dictionary, the key are tone
                                 indices, and the values are dictionaries with the tone parameter values.
        :return: None
        """
        logger.info(f"Generating tones with the following parameter dictionary: {output_wf_params}")

        self.initialize_waveform_buffers(self.f_res_desired)
        # Normalization factor to convert from normalized voltage units to ADC units
        wf_adc_norm = self.max_adc_value - 1

        self.output_waveform_params = output_wf_params
        sample_ind_vector = numpy.arange(0, self.sequence_data_len_samples, 1)
        waveform_ch0 = numpy.zeros(self.sequence_data_len_samples, dtype=numpy.int16)
        waveform_ch1 = numpy.zeros(self.sequence_data_len_samples, dtype=numpy.int16)

        # Amplitude conversion: AWG outputs +-2.0 V into 50 Ohm. The internal ADC (I suppose 16-bit) has a maximum value
        # of self.max_adc_value, but only outputs positive integers. This means that max_adc_value corresponds to +4 V output.
        # Therefore, the desired output should be scaled by 4
        for tone_ind, tone_params in self.output_waveform_params[0].items():
            logger.info(f"CH0: Setting tone {tone_ind} with tone parameters: {tone_params}")
            waveform_ch0 = waveform_ch0 +  (wf_adc_norm * (tone_params["Amplitude, V"]/4.0) \
                            * numpy.sin(2 * numpy.pi * sample_ind_vector \
                                        * tone_params["Frequency, Hz"]//self.f_res_set \
                                        + tone_params["Phase, rad"])).astype(numpy.int16)
            logger.info(
                f"Tone {tone_ind}: \nRequested frequency: {tone_params["Frequency, Hz"]} Hz, \nSet frequency: {tone_params["Frequency, Hz"] // self.f_res_set * self.f_res_set} Hz")

        for tone_ind, tone_params in self.output_waveform_params[1].items():
            logger.info(f"CH1: Setting tone {tone_ind} with tone parameters: {tone_params}")
            waveform_ch1 = waveform_ch1 + (wf_adc_norm * (tone_params["Amplitude, V"]/4.0) \
                            * numpy.sin(2 * numpy.pi * sample_ind_vector \
                                        * tone_params["Frequency, Hz"]//self.f_res_set \
                                        + tone_params["Phase, rad"])).astype(numpy.int16)
            logger.info(
                f"Tone {tone_ind}: \nRequested frequency: {tone_params["Frequency, Hz"]} Hz, \nSet frequency: {tone_params["Frequency, Hz"] // self.f_res_set * self.f_res_set} Hz")

        # Interleave waveforms because that's how the AWG card transfers data
        waveform_interleaved = numpy.empty(2*waveform_ch0.size, dtype=numpy.int16)
        waveform_interleaved[0::self.channel_number] = waveform_ch0
        waveform_interleaved[1::self.channel_number] = waveform_ch1
        self.pnData = (waveform_interleaved).astype(int16)
        logger.info("Data transferred to the PC memory buffer")

        return None

    def transfer_data(self, segment_index, segment_len_samples_per_ch, segment_len_bytes, data_to_transfer):
        """
        Helper function to transfer data from PC to AWG memory.
        :param segment_index: Segment index where we want to transfer data.
        :param segment_len_samples_per_ch: Length of the data to transfer, IN SAMPLES PER CHANNEL
        :param segment_len_bytes: Length of data to transfer, IN BYTES. Should be 2* segment_len_samples_per_ch * chnum
        :param data_to_transfer: Buffer to transfer. Should be pointer, but I have no clue what that means for Python
        :return: None
        """
        logger.info("Starting data transfer to AWG memory")
        # setup
        # Select index of the AWG memory segment to set up
        dwError = spcm_dwSetParam_i32(self.hCard, SPC_SEQMODE_WRITESEGMENT, segment_index)
        if dwError != ERR_OK:
            logger.error(f"Error during data transfer to AWG memory: {dwError}")
            return 1
        if dwError == ERR_OK:
            logger.info(f"Configuring AWG memory segment {segment_index}")
            # Set the size of segment in samples per channel
            dwError = spcm_dwSetParam_i32(self.hCard, SPC_SEQMODE_SEGMENTSIZE, segment_len_samples_per_ch)
            if dwError != ERR_OK:
                logger.error(f"Configuring AWG memory segment {segment_index} failed")
                return 1

        # write data to board (main) sample memory
        if dwError == ERR_OK:
            logger.info(f"Transferring data to AWG memory segment {segment_index}")
            dwError = spcm_dwDefTransfer_i64(self.hCard, SPCM_BUF_DATA, SPCM_DIR_PCTOCARD, 0, data_to_transfer, 0, segment_len_bytes)
        if dwError == ERR_OK:
            logger.info("Data transferred to the card memory")
            dwError = spcm_dwSetParam_i32(self.hCard, SPC_M2CMD, M2CMD_DATA_STARTDMA | M2CMD_DATA_WAITDMA)
            if dwError == ERR_OK:
                return 0
            else:
                return 1
        else:
            return 1


    def populate_awg_buffer(self):

        if self.pnData is None:
            logger.error("Data buffer not populated")
            return 1
        # The way we switch between waveforms is the following. The sequence replay mode defines a sequence with just
        # one step, which infinitely loops onto itself. We then subdivide internal AWG memory into 2 parts.
        # If the sequence currently plays memory segment 0, then we write data into segment 1, and then change
        # sequence step 0 to infinitely loop over memory segment 1, and same for the other case.
        if self.current_segment == 0:
            self.transfer_data(segment_index=1,
                               segment_len_samples_per_ch=self.sequence_data_len_samples,
                               segment_len_bytes=self.data_transfer_buffer_size_bytes,
                               data_to_transfer=self.pvBuffer)
            # Change step 0 of the sequence to output data from memory segment 1
            self.configure_sequence_step(step_index=0,
                                         next_step_index=0,
                                         segment_index=1,
                                         num_loops=1,
                                         segment_flags=0)
            self.current_segment = 1
            logger.info(f"AWG memory updated, sequence replaying segment {self.current_segment}")

            spcm_dwSetParam_i32(self.hCard, SPCM_XX_ASYNCIO, 1)  # Emit a 1ms pulse from X0
            time.sleep(1 / 1000)
            spcm_dwSetParam_i32(self.hCard, SPCM_XX_ASYNCIO, 0)
            return 0
        elif self.current_segment == 1:
            self.transfer_data(segment_index=0,
                               segment_len_samples_per_ch=self.sequence_data_len_samples,
                               segment_len_bytes=self.data_transfer_buffer_size_bytes,
                               data_to_transfer=self.pvBuffer)
            # Change step 0 of the sequence to output data from memory segment 0
            self.configure_sequence_step(step_index=0,
                                         next_step_index=0,
                                         segment_index=0,
                                         num_loops=1,
                                         segment_flags=0)
            self.current_segment = 1
            logger.info(f"AWG memory updated, sequence replaying segment {self.current_segment}")

            spcm_dwSetParam_i32(self.hCard, SPCM_XX_ASYNCIO, 1)  # Emit a 1ms pulse from X0
            time.sleep(1 / 1000)
            spcm_dwSetParam_i32(self.hCard, SPCM_XX_ASYNCIO, 0)

            return 0
        else:
            logger.error("Unexpected segment index")
            return 1

    def card_turn_on(self):
        # We'll start and wait until all sequences are replayed.
        spcm_dwSetParam_i32(self.hCard, SPC_TIMEOUT, 0)
        logger.info("Starting the card")
        spcm_dwSetParam_i32(self.hCard, SPC_M2CMD, M2CMD_CARD_START | M2CMD_CARD_ENABLETRIGGER)
        dwErr = self.handle_error()
        if dwErr != ERR_OK:
            spcm_dwSetParam_i32(self.hCard, SPC_M2CMD, M2CMD_CARD_STOP)
            logger.error("... Error: {0:d}".format(dwErr))
            return 1
        return 0

    def card_turn_off(self):
        spcm_dwSetParam_i32(self.hCard, SPC_M2CMD, M2CMD_CARD_STOP)
        spcm_vClose(self.hCard)
        return 0

    def get_data_buffer(self):
        return self.pnData


