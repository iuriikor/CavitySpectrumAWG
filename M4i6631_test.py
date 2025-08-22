import time
import msvcrt

from M4i6631 import M4i6631

from spcm_tools import *
from pyspcm import *
from matplotlib import pyplot as plt

def lKbhit():
    return ord(msvcrt.getch()) if msvcrt.kbhit() else 0

wf_params_test = {
                0: { # Channel 0 index
                    0: { # Tone 0 index
                        "Frequency, Hz": 1e06, # Tone parameters
                        "Amplitude, V": 0.1,
                        "Phase, rad": 0
                    }
                },
                1: { # Channel 1 index
                    0: { # Tone 0 index
                        "Frequency, Hz": 1e06, # Tone parameters
                        "Amplitude, V": 0.1,
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
                   wf_params_default=wf_params_test)

awg_card.card_turn_on()
awg_data = awg_card.get_data_buffer()

# while True:
#     lKey = lKbhit()
#     if lKey == 27:  # ESC
#         spcm_dwSetParam_i32(awg_card.hCard, SPC_M2CMD, M2CMD_CARD_STOP)
#         break
time.sleep(1)

awg_card.card_turn_off()

fig, ax = plt.subplots()
ax.plot(awg_data[0::2])
ax.set_xlim([0, 100])
fig.savefig('awg_data_buffer.pdf', dpi=600)
fig.show()