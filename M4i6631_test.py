import time

from M4i6631 import M4i6631

wf_params_test = {
                0: { # Channel 0 index
                    0: { # Tone 0 index
                        "Frequency, Hz": 50e06, # Tone parameters
                        "Amplitude, V": 0.2,
                        # "Phase, rad": 101.5/180 * numpy.pi # Out of phase
                        "Phase, rad": 0
                    }
                },
                1: { # Channel 1 index
                    0: { # Tone 0 index
                        "Frequency, Hz": 50e06, # Tone parameters
                        "Amplitude, V": 0.2,
                        "Phase, rad": 0
                    }
                }
            }

awg_card = M4i6631(address=b'/dev/spcm0',
                   channelNum=2,
                   sampleRate=500,
                   referenceClock=True,
                   referenceClockFrequency=100e06,
                   clockOut=False,
                   wf_params_default=wf_params_test,
                   f_res_desired=100)

awg_card.card_turn_on()
awg_data = awg_card.get_data_buffer()
time.sleep(10)
awg_card.card_turn_off()

