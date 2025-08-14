from tkinter import *
from tkinter import messagebox
import Input_correction_new as CI
from spcm_tools import *
import numpy as np
from pyspcm import *
from enum import IntEnum
import time
import json
import os

## Spectrum Card Code###

USING_EXTERNAL_TRIGGER = False

data_directory = r'C:\Users\iurii\Documents\AOD_control'


def vWriteSegmentData(hCard, dwSegmentIndex, dwSegmentLenSample, pvSegData):
    lBytesPerSample = 2
    dwSegLenByte = uint32(dwSegmentLenSample * lBytesPerSample)

    # setup
    dwError = spcm_dwSetParam_i32(hCard, SPC_SEQMODE_WRITESEGMENT, dwSegmentIndex)
    if dwError == ERR_OK:
        dwError = spcm_dwSetParam_i32(hCard, SPC_SEQMODE_SEGMENTSIZE, dwSegmentLenSample // 2)

    # write data to board (main) sample memory
    if dwError == ERR_OK:
        dwError = spcm_dwDefTransfer_i64(hCard, SPCM_BUF_DATA, SPCM_DIR_PCTOCARD, 0, pvSegData, 0, dwSegLenByte)
    if dwError == ERR_OK:
        dwError = spcm_dwSetParam_i32(hCard, SPC_M2CMD, M2CMD_DATA_STARTDMA | M2CMD_DATA_WAITDMA)


class SEGMENT_IDX(IntEnum):
    SEG0_SIN = 0
    SEG1_SIN = 1


def vDoDataCalculation(lCardType, lMaxDACValue):
    dwSegmentLenSample = uint32(0)
    dwSegLenByte = uint32(0)

    sys.stdout.write("Calculation of output data\n")

    dwFactor = uint32(1)
    # This series has a slightly increased minimum size value.
    if ((lCardType.value & TYP_SERIESMASK) == TYP_M4IEXPSERIES) or (
            (lCardType.value & TYP_SERIESMASK) == TYP_M4XEXPSERIES):
        dwFactor = 6

    # buffer for data transfer
    dwSegLenByte = 2 * dwFactor * 512  # max value taken from sine calculation below
    pvBuffer = pvAllocMemPageAligned(16384 * 4 * 4 * 4)    #wrote 80 instead of 4
    pnData = cast(addressof(pvBuffer), ptr16)

    # helper values: Full Scale
    global dwFS
    dwFS = uint32(lMaxDACValue.value)
    dwFShalf = uint32(dwFS.value // 2)

    dwSegmentLenSample = dwFactor * 128 * 16 * 13

    f_c = 860e06 / (dwSegmentLenSample)
    freq_ini_1 = 50e06
    freq_ini_2 = 50e06  # Hz
    Ch0_phase = 0
    Ch1_phase = 0
    amp_ini = 0  # mV
    amp_ini = CI.amplitude_correction(amp_ini, freq_ini_1)
    f_factor_1 = int(freq_ini_1 / f_c)
    f_factor_2 = int(freq_ini_2 / f_c)
    for i in range(0, dwSegmentLenSample * 2, 1):
        if i % 2 == 0:
            pnData[i] = int16(int(dwFShalf.value * (
                    (amp_ini / 1000) * np.sin(2.0 * np.pi * (i // 2) * f_factor_1 / (dwSegmentLenSample)))) + int(
                dwFShalf.value * ((amp_ini / 1000) * np.sin(
                    2.0 * np.pi * (i // 2) * f_factor_2 / (dwSegmentLenSample) + Ch0_phase))))
        else:
            pnData[i] = int16(int(dwFShalf.value * (
                    (amp_ini / 1000) * np.sin(2.0 * np.pi * (i // 2) * f_factor_1 / (dwSegmentLenSample)))) + int(
                dwFShalf.value * ((amp_ini / 1000) * np.sin(
                    2.0 * np.pi * (i // 2) * f_factor_2 / (dwSegmentLenSample) + Ch1_phase))))
    vWriteSegmentData(hCard, SEGMENT_IDX.SEG0_SIN, dwSegmentLenSample * 2, pvBuffer)

    #dwSegmentLenSample = dwFactor * 128 * 320 * 13      #wrote 320 instead of 16
    for i in range(0, dwSegmentLenSample * 2, 1):
        if i % 2 == 0:
            pnData[i] = int16(int(dwFShalf.value * (
                    (amp_ini / 1000) * np.sin(2.0 * np.pi * (i // 2) * f_factor_1 / (dwSegmentLenSample)))) + int(
                dwFShalf.value * ((amp_ini / 1000) * np.sin(
                    2.0 * np.pi * (i // 2) * f_factor_2 / (dwSegmentLenSample) + Ch0_phase))))
        else:
            pnData[i] = int16(int(dwFShalf.value * (
                    (amp_ini / 1000) * np.sin(2.0 * np.pi * (i // 2) * f_factor_1 / (dwSegmentLenSample)))) + int(
                dwFShalf.value * ((amp_ini / 1000) * np.sin(
                    2.0 * np.pi * (i // 2) * f_factor_2 / (dwSegmentLenSample) + Ch1_phase))))

    vWriteSegmentData(hCard, SEGMENT_IDX.SEG1_SIN, dwSegmentLenSample * 2, pvBuffer)


def vWriteStepEntry(hCard, dwStepIndex, dwStepNextIndex, dwSegmentIndex, dwLoops, dwFlags):
    qwSequenceEntry = uint64(0)

    # setup register value
    qwSequenceEntry = (dwFlags & ~SPCSEQ_LOOPMASK) | (dwLoops & SPCSEQ_LOOPMASK)
    qwSequenceEntry <<= 32
    qwSequenceEntry |= ((dwStepNextIndex << 16) & SPCSEQ_NEXTSTEPMASK) | (int(dwSegmentIndex) & SPCSEQ_SEGMENTMASK)

    dwError = spcm_dwSetParam_i64(hCard, SPC_SEQMODE_STEPMEM0 + dwStepIndex, int64(qwSequenceEntry))


def vConfigureSequence(hCard):
    vWriteStepEntry(hCard, 0, 0, SEGMENT_IDX.SEG0_SIN, 1, 0)
    if USING_EXTERNAL_TRIGGER == False:
        vWriteStepEntry(hCard, 0, 0, SEGMENT_IDX.SEG0_SIN, 1, 0)
    else:
        vWriteStepEntry(hCard, 0, 2, SEGMENT_IDX.SEG2_SIN, 1, SPCSEQ_ENDLOOPONTRIG)
    # Configure the beginning (index of first seq-entry to start) of the sequence replay.
    spcm_dwSetParam_i32(hCard, SPC_SEQMODE_STARTSTEP, 0)

    if False:
        sys.stdout.write("\n")
        for i in range(0, 32, 1):
            llTemp = int64(0)
            spcm_dwGetParam_i64(hCard, SPC_SEQMODE_STEPMEM0 + i, byref(llTemp))
            sys.stdout.write("Step {0:.2}: 0x{1:016llx}\n".format(i, llTemp))

        sys.stdout.write("\n\n")


def CalculateData(Ch0_f, Ch0_amp, Ch0_phase, Ch1_f, Ch1_amp, Ch1_phase, Ch1_phase_offset, Segment, lCardType,
                  lMaxDACValue):
    sys.stdout.write("Calculation of output data\n")

    dwFactor = uint32(1)
    # This series has a slightly increased minimum size value.
    if ((lCardType.value & TYP_SERIESMASK) == TYP_M4IEXPSERIES) or (
            (lCardType.value & TYP_SERIESMASK) == TYP_M4XEXPSERIES):
        dwFactor = 6

    # buffer for data transfer
    dwSegLenByte = 2 * dwFactor * 512  # max value taken from sine calculation below
    if detune.get()==False:
        pvBuffer = pvAllocMemPageAligned(16384 * 4 * 4 * 4)    #wrote 80 instead of 4
    else:
        pvBuffer = pvAllocMemPageAligned(16384 * 4 * 4 * 80)    #wrote 80 instead of 4
    pnData = cast(addressof(pvBuffer), ptr16)
    global dwFS
    dwFS = uint32(lMaxDACValue.value)
    dwFShalf = uint32(dwFS.value // 2)
    if detune.get()==False:
        dwSegmentLenSample = dwFactor * 128 * 16 * 13
    else:
        dwSegmentLenSample = dwFactor * 128 * 320 * 13      #wrote 320 instead of 16
        
    f_c = 860e06 / (dwSegmentLenSample)
    #print("Ch0_f_value: " + str(Ch0_f[0]))
    """
    for i in range(0, dwSegmentLenSample * 2, 1):  
        if i % 2 == 0:
            Signal = [dwFShalf.value * ((Ch0_amp[j] / 1000) * np.sin(
                2.0 * np.pi * (i // 2) * int(Ch0_f[j]) / (dwSegmentLenSample) + Ch0_phase[j])) for j in range(len(Ch0_f))]
            pnData[i] = int16(round(sum(Signal)))
            
        else:
            Signal = [dwFShalf.value * ((Ch1_amp[j] / 1000) * np.sin(
                (2.0 * np.pi * (i // 2) * int(Ch1_f[j]) / (dwSegmentLenSample)) + Ch1_phase[j] - Ch1_phase_offset[j])) for j
                      in range(len(Ch1_f))]  # deleted '- Ch1_phase_offset[j]' #deleted '+ Ch1_phase_offset[j]'
            pnData[i] = int16(round(sum(Signal)))
    print("comparison:")
    print(type(pnData))
    """
    steps = np.arange(0, dwSegmentLenSample, 1)
    sig = np.zeros((int(2*dwSegmentLenSample), len(Ch0_f)))
    for j in range(len(Ch0_f)):

        sig[::2,j] = (dwFShalf.value * ((Ch0_amp[j] / 1000) * 
            np.sin(2.0 * np.pi * (steps) * Ch0_f[j] / (dwSegmentLenSample) + Ch0_phase[j])))
        sig[1::2,j] = (dwFShalf.value * ((Ch1_amp[j] / 1000) * 
            np.sin(2.0 * np.pi * (steps) * Ch1_f[j] / (dwSegmentLenSample) + Ch1_phase[j])))

    sig = np.sum(sig.astype(float), axis = 1)
    #sig[:] = np.int16(np.round(sig[:]))
    #sig = sig.round()
    
    #for i in range(0, dwSegmentLenSample * 2, 1): 
    #    pnData[i] = np.int16(round(sig[i]))
    sig = np.int16(np.round(sig))
    #for i in range(0, dwSegmentLenSample * 2, 1): 
    #    pnData[i] = sig[i]
    for i, j in enumerate(sig): 
        pnData[i] = j
    #print(type(pnData))
    
    if Segment == 0:
        vWriteSegmentData(hCard, SEGMENT_IDX.SEG1_SIN, dwSegmentLenSample * 2, pvBuffer)
    if Segment == 1:
        vWriteSegmentData(hCard, SEGMENT_IDX.SEG0_SIN, dwSegmentLenSample * 2, pvBuffer)


def Create_interface():
    Label(fenetre, text="Freq [MhZ]").grid(row=0, column=3, sticky=W)
    Label(fenetre, text="Amp [mV]").grid(row=0, column=4, sticky=W)
    Label(fenetre, text="Phase [°]").grid(row=0, column=5, sticky=W)
    # Channel_0
    global Ch0_f_entry_dic, Ch0_amp_entry_dic, Ch0_phase_entry_dic, Ch1_f_entry_dic, Ch1_amp_entry_dic, Ch1_phase_entry_dic, Ch0_click, Ch1_click, detune
    Ch0_f_entry_dic = {}
    Ch0_Freq = [DoubleVar() for j in range(int(N_freq0.get()))]
    for i in range(0, int(N_freq0.get())):
        Ch0_f_entry_dic[i] = Entry(fenetre, text=Ch0_Freq[i], width=20)
        Ch0_f_entry_dic[i].grid(row=1 + i, column=3)

    Ch0_amp_entry_dic = {}
    Ch0_Amp = [DoubleVar() for j in range(int(N_freq0.get()))]
    for i in range(0, int(N_freq0.get())):
        Ch0_amp_entry_dic[i] = Entry(fenetre, text=Ch0_Amp[i], width=20)
        Ch0_amp_entry_dic[i].grid(row=1 + i, column=4)

    Ch0_phase_entry_dic = {}
    Ch0_Phase = [DoubleVar() for j in range(int(N_freq0.get()))]
    for i in range(0, int(N_freq0.get())):
        Ch0_phase_entry_dic[i] = Entry(fenetre, text=Ch0_Phase[i], width=20)
        Ch0_phase_entry_dic[i].grid(row=1 + i, column=5)

    Ch0_click_dic = {}
    Ch0_click = [BooleanVar() for j in range(int(N_freq0.get()))]
    for i in range(0, int(N_freq0.get())):
        Ch0_click_dic[i] = Checkbutton(fenetre, text='Enable', variable=Ch0_click[i], onvalue=True, offvalue=False)
        Ch0_click_dic[i].select()           #Try starting with enabled on
        Ch0_click_dic[i].grid(row=1 + i, column=6)

    # set default values for Ch0
    if int(N_freq0.get()) == 2:
        Ch0_Freq[0].set(48)
        Ch0_Freq[1].set(52)
        Ch0_Amp[0].set(80)
        Ch0_Amp[1].set(80)

    # Channel_1
    Ch1.grid(row=1 + int(N_freq0.get()), column=0)
    N_freq1.grid(row=1 + int(N_freq0.get()), column=1)

    Ch1_f_entry_dic = {}
    Ch1_Freq = [DoubleVar() for j in range(int(N_freq1.get()))]
    for i in range(0, int(N_freq1.get())):
        Ch1_f_entry_dic[i] = Entry(fenetre, text=Ch1_Freq[i], width=20)
        Ch1_f_entry_dic[i].grid(row=1 + int(N_freq0.get()) + i, column=3)

    Ch1_amp_entry_dic = {}
    Ch1_Amp = [DoubleVar() for j in range(int(N_freq1.get()))]
    for i in range(0, int(N_freq1.get())):
        Ch1_amp_entry_dic[i] = Entry(fenetre, text=Ch1_Amp[i], width=20)
        Ch1_amp_entry_dic[i].grid(row=1 + int(N_freq0.get()) + i, column=4)

    Ch1_phase_entry_dic = {}
    Ch1_Phase = [DoubleVar() for j in range(int(N_freq1.get()))]
    for i in range(0, int(N_freq1.get())):
        Ch1_phase_entry_dic[i] = Entry(fenetre, text=Ch1_Phase[i], width=20)
        Ch1_phase_entry_dic[i].grid(row=1 + int(N_freq0.get()) + i, column=5)

    Ch1_click_dic = {}
    Ch1_click = [BooleanVar() for j in range(int(N_freq1.get()))]
    for i in range(0, int(N_freq1.get())):
        Ch1_click_dic[i] = Checkbutton(fenetre, text='Enable', variable=Ch1_click[i], onvalue=True, offvalue=False)
        Ch1_click_dic[i].select()           #Try starting with enabled on
        Ch1_click_dic[i].grid(row=1 + int(N_freq0.get()) + i, column=6)

    # set default values for Ch1
    if int(N_freq1.get()) == 2:
        Ch1_Freq[0].set(52)
        Ch1_Freq[1].set(56)
        Ch1_Amp[0].set(80)
        Ch1_Amp[1].set(80)
        
    detune = BooleanVar()
    detune_dic = Checkbutton(fenetre, text='Small Frequency Steps', variable=detune, onvalue=True, offvalue=False)
    detune_dic.grid(row=int(int(N_freq1.get())*2+2), column=3)

    
def data():
    global running
    dwFactor = 6
    if detune.get()==False:
        dwSegmentLenSample = dwFactor * 128 * 16 * 13
    else:
        dwSegmentLenSample = dwFactor * 128 * 320 * 13      #wrote 320 instead of 16
    f_c = 860e06 / dwSegmentLenSample      #wrote dwSegmentLenSample instead of (6 * 128 * 13 * 16)
    Output_Ch0 = [Ch0_click[i].get() for i in range(int(N_freq0.get()))]
    Output_Ch1 = [Ch1_click[i].get() for i in range(int(N_freq1.get()))]

    # Channel0 data
    Ch0_f_value = [float(Ch0_f_entry_dic[i].get()) for i in range(int(N_freq0.get()))]
    #print(Ch0_f_value[0])
    Ch0_f_value = [((i *1e06 /f_c)) for i in Ch0_f_value]       #removed conversion factor
    Ch0_f_value = [Ch0_f_value[i] for i in range(int(N_freq0.get())) if Output_Ch0[i] == True]
    
    if detune.get()==False:
        totalfint_Ch0 = sum([int(Ch0_f_value[i]) for i in range(len(Ch0_f_value))])
        if len(Ch0_f_value) > 1:
            if totalfint_Ch0 > 27119:
                if (Ch0_f_value[0] - int(Ch0_f_value[0])) > (Ch0_f_value[1] - int(Ch0_f_value[1])):
                    Ch0_f_value[0] = int(Ch0_f_value[0])
                    Ch0_f_value[1] = int(Ch0_f_value[1] - 1)
                else:
                    Ch0_f_value[0] = int(Ch0_f_value[0] - 1)
                    Ch0_f_value[1] = int(Ch0_f_value[1])
            elif totalfint_Ch0 < 27119:
                if (Ch0_f_value[0] - int(Ch0_f_value[0])) > (Ch0_f_value[1] - int(Ch0_f_value[1])):
                    Ch0_f_value[0] = int(Ch0_f_value[0] + 1)
                    Ch0_f_value[1] = int(Ch0_f_value[1])
                else:
                    Ch0_f_value[0] = int(Ch0_f_value[0])
                    Ch0_f_value[1] = int(Ch0_f_value[1] + 1)
            else:
                Ch0_f_value[0] = int(Ch0_f_value[0])
                Ch0_f_value[1] = int(Ch0_f_value[1])
        else:
            if len(Ch0_f_value) > 0:
                Ch0_f_value[0] = int(Ch0_f_value[0])
        totalfint_Ch0 = sum(Ch0_f_value)

        # if not totalfint_Ch0 == (27119) and len(Ch0_f_value) > 1:
        #     messagebox.showerror('Frequency error', 'Frequencies are not moved symmetrically')
        #     running = False
        #     return ()
    else:
        Ch0_f_value[0] = int(Ch0_f_value[0])
        if len(Ch0_f_value) > 1:
            Ch0_f_value[1] = int(Ch0_f_value[1])
        
    Ch0_amp_value = [float(Ch0_amp_entry_dic[i].get()) for i in range(int(N_freq0.get()))]
    Ch0_amp_value = [Ch0_amp_value[i] for i in range(int(N_freq0.get())) if Output_Ch0[i] == True]
    total_Ch0 = sum(Ch0_amp_value)
    if total_Ch0 >= 600:
        messagebox.showerror('Amplitude error', 'Total Amplitude on channel0 should be under:600 mV')
        return ()

    Ch0_amp_value = [CI.amplitude_correction(Ch0_amp_value[i], Ch0_f_value[i] * f_c) for i in range(len(Ch0_amp_value))]
    Ch0_phase_value = [float(Ch0_phase_entry_dic[i].get()) for i in range(int(N_freq0.get()))]
    Ch0_phase_value = [i * (np.pi / 180) for i in Ch0_phase_value]
    Ch0_phase_value = [Ch0_phase_value[i] for i in range(int(N_freq0.get())) if Output_Ch0[i] == True]

    # Channel1 data
    Ch1_f_value = [float(Ch1_f_entry_dic[i].get()) for i in range(int(N_freq1.get()))]
    Ch1_f_value = [((i* 1e06 / f_c )) for i in Ch1_f_value]       #removed conversion factor
    Ch1_f_value = [Ch1_f_value[i] for i in range(int(N_freq1.get())) if Output_Ch1[i] == True]
    totalfint_Ch1 = sum([int(Ch1_f_value[i]) for i in range(len(Ch1_f_value))])
        
    if detune.get()==False:
        if len(Ch1_f_value) > 1:
            if totalfint_Ch1 > 27119:
                if (Ch1_f_value[0] - int(Ch1_f_value[0])) > (Ch1_f_value[1] - int(Ch1_f_value[1])):
                    Ch1_f_value[0] = int(Ch1_f_value[0])
                    Ch1_f_value[1] = int(Ch1_f_value[1] - 1)
                else:
                    Ch1_f_value[0] = int(Ch1_f_value[0] - 1)
                    Ch1_f_value[1] = int(Ch1_f_value[1])
            elif totalfint_Ch1 < 27119:
                if (Ch1_f_value[0] - int(Ch1_f_value[0])) > (Ch1_f_value[1] - int(Ch1_f_value[1])):
                    Ch1_f_value[0] = int(Ch1_f_value[0] + 1)
                    Ch1_f_value[1] = int(Ch1_f_value[1])
                else:
                    Ch1_f_value[0] = int(Ch1_f_value[0])
                    Ch1_f_value[1] = int(Ch1_f_value[1] + 1)
            else:
                Ch1_f_value[0] = int(Ch1_f_value[0])
                Ch1_f_value[1] = int(Ch1_f_value[1])
        else:
            if len(Ch1_f_value) > 0:
                Ch1_f_value[0] = int(Ch1_f_value[0])
        totalfint_Ch1 = sum(Ch1_f_value)

        # if not totalfint_Ch1 == (27119) and len(Ch1_f_value) > 1:
        #     messagebox.showerror('Frequency error', 'Frequencies are not moved symmetrically')
        #     running = False
        #     return ()
    else:
        Ch1_f_value[0] = int(Ch1_f_value[0])
        if len(Ch1_f_value) > 1:
            Ch1_f_value[1] = int(Ch1_f_value[1])
           
    """    
    ###Ensures frequencies add up to 146MHz if one of the traps is not detuned even though detuning is enabled
    ###only works if trap 1 is created by Ch0[0]+Ch1[0]!!
        
    else:
        if len(Ch0_f_value) > 1:
            p1_f_value = float(Ch0_f_entry_dic[0].get())+float(Ch1_f_entry_dic[0].get())
            p2_f_value = float(Ch0_f_entry_dic[1].get())+float(Ch1_f_entry_dic[1].get())
            print(p1_f_value, p2_f_value)
            
            if p1_f_value==146:
                totalfint_p1 = int(Ch0_f_value[0])+int(Ch1_f_value[0])
                if totalfint_p1 > 27119:
                    if (Ch0_f_value[0] - int(Ch0_f_value[0])) > (Ch1_f_value[0] - int(Ch1_f_value[0])):
                        Ch0_f_value[0] = int(Ch0_f_value[0])
                        Ch1_f_value[0] = int(Ch1_f_value[0] - 1)
                    else:
                        Ch0_f_value[0] = int(Ch0_f_value[0] - 1)
                        Ch1_f_value[0] = int(Ch1_f_value[0])
                elif totalfint_p1 < 27119:
                    if (Ch0_f_value[0] - int(Ch0_f_value[0])) > (Ch1_f_value[0] - int(Ch1_f_value[0])):
                        Ch0_f_value[0] = int(Ch0_f_value[0] + 1)
                        Ch1_f_value[0] = int(Ch1_f_value[0])
                    else:
                        Ch0_f_value[0] = int(Ch0_f_value[0])
                        Ch1_f_value[0] = int(Ch1_f_value[0] + 1)
                else:
                    Ch0_f_value[0] = int(Ch0_f_value[0])
                    Ch1_f_value[0] = int(Ch1_f_value[0])
                                         
            if p2_f_value==146:
                totalfint_p2 = int(Ch0_f_value[1])+int(Ch1_f_value[1])
                if totalfint_p2 > 27119:
                    if (Ch0_f_value[1] - int(Ch0_f_value[1])) > (Ch1_f_value[1] - int(Ch1_f_value[1])):
                        Ch0_f_value[1] = int(Ch0_f_value[1])
                        Ch1_f_value[1] = int(Ch1_f_value[1] - 1)
                    else:
                        Ch0_f_value[1] = int(Ch0_f_value[1] - 1)
                        Ch1_f_value[1] = int(Ch1_f_value[1])
                elif totalfint_p2 < 27119:
                    if (Ch0_f_value[1] - int(Ch0_f_value[1])) > (Ch1_f_value[1] - int(Ch1_f_value[1])):
                        Ch0_f_value[1] = int(Ch0_f_value[1] + 1)
                        Ch1_f_value[1] = int(Ch1_f_value[1])
                    else:
                        Ch0_f_value[1] = int(Ch0_f_value[1])
                        Ch1_f_value[1] = int(Ch1_f_value[1] + 1)
                else:
                    Ch0_f_value[1] = int(Ch0_f_value[1])
                    Ch1_f_value[1] = int(Ch1_f_value[1])
"""

    ### make frequency an integer
    #Ch0_f_value = [int(Ch0_f_value[i]) for i in range(int(N_freq0.get()))]
    #Ch1_f_value = [int(Ch1_f_value[i]) for i in range(int(N_freq1.get()))]


    
    Ch1_amp_value = [float(Ch1_amp_entry_dic[i].get()) for i in range(int(N_freq1.get()))]
    Ch1_amp_value = [Ch1_amp_value[i] for i in range(int(N_freq1.get())) if Output_Ch1[i] == True]
    total_Ch1 = sum(Ch1_amp_value)
    if total_Ch1 >= 600:
        messagebox.showerror('Amplitude error', 'Total Amplitude on channel1 should be under 600 mV')
        return ()
    Ch1_amp_value = [CI.amplitude_correction(Ch1_amp_value[i], Ch1_f_value[i] * f_c) for i in range(len(Ch1_amp_value))]

    Ch1_phase_value = [float(Ch1_phase_entry_dic[i].get()) for i in range(int(N_freq1.get()))]
    Ch1_phase_value = [i * (np.pi / 180) for i in Ch1_phase_value]
    Ch1_phase_value = [Ch1_phase_value[i] for i in range(int(N_freq1.get())) if Output_Ch1[i] == True]
    Ch1_phase_offset = [-7.65 * np.pi / 180 for i in range(len(Ch1_f_value))]

    ## print frequency output
    print("Ch0:")
    for i in range(len(Ch0_amp_value)):
        print(int(Ch0_f_value[i] * f_c*1e6))
    print("Ch1:")
    for i in range(len(Ch1_amp_value)):
        print(int(Ch1_f_value[i] * f_c*1e6))
    
    if Segment.get() == 0:
        CalculateData(Ch0_f_value, Ch0_amp_value, Ch0_phase_value, Ch1_f_value, Ch1_amp_value, Ch1_phase_value,
                      Ch1_phase_offset, Segment.get(), lCardType, dwFS)
        vWriteStepEntry(hCard, 0, 0, SEGMENT_IDX.SEG1_SIN, 1, 0)
        Segment.set(1)
        spcm_dwSetParam_i32(hCard, SPCM_XX_ASYNCIO, 1) # Emit a 1ms pulse from X0
        time.sleep(1/1000)
        spcm_dwSetParam_i32(hCard, SPCM_XX_ASYNCIO, 0)
    elif Segment.get() == 1:
        CalculateData(Ch0_f_value, Ch0_amp_value, Ch0_phase_value, Ch1_f_value, Ch1_amp_value, Ch1_phase_value,
                      Ch1_phase_offset, Segment.get(), lCardType, dwFS)
        vWriteStepEntry(hCard, 0, 0, SEGMENT_IDX.SEG0_SIN, 1, 0)  # replace Seg0 by seg0
        Segment.set(0)
        spcm_dwSetParam_i32(hCard, SPCM_XX_ASYNCIO, 1) # Emit a 1ms pulse from X0
        time.sleep(1/1000)
        spcm_dwSetParam_i32(hCard, SPCM_XX_ASYNCIO, 0)


def take_data():
    freq00 = DoubleVar()
    freq00.set(Ch0_f_entry_dic[0].get())
    freq10 = DoubleVar()
    freq10.set(Ch1_f_entry_dic[0].get())

    amp00 = DoubleVar()
    amp00.set(Ch0_amp_entry_dic[0].get())
    amp10 = DoubleVar()
    amp10.set(Ch1_amp_entry_dic[0].get())

    phase00 = DoubleVar()
    phase00.set(Ch0_phase_entry_dic[0].get())
    phase10 = DoubleVar()
    phase10.set(Ch1_phase_entry_dic[0].get())

    if len(Ch0_f_entry_dic) > 1:  # here I expect that Channel 0 and Channel 1 will always be of same size
        freq01 = DoubleVar()
        freq01.set(Ch0_f_entry_dic[1].get())
        freq11 = DoubleVar()
        freq11.set(Ch1_f_entry_dic[1].get())

        amp01 = DoubleVar()
        amp01.set(Ch0_amp_entry_dic[1].get())
        amp11 = DoubleVar()
        amp11.set(Ch1_amp_entry_dic[1].get())

        phase01 = DoubleVar()
        phase01.set(Ch0_phase_entry_dic[1].get())
        phase11 = DoubleVar()
        phase11.set(Ch1_phase_entry_dic[1].get())

    header_file_name = 'get_info.dat'
    with open(os.path.join(data_directory, header_file_name), 'w') as file:
        file.write('CH00: \n    Freq = ' + str(Ch0_f_entry_dic[0].get()) + '\n')
        file.write('    Phase = ' + str(Ch0_phase_entry_dic[0].get()) + '\n')
        file.write('    Amp = ' + str(Ch0_amp_entry_dic[0].get()) + '\n')
        if len(Ch0_amp_entry_dic) > 1:
            file.write('CH01: \n    Freq = ' + str(Ch0_f_entry_dic[1].get()) + '\n')
            file.write('    Phase = ' + str(Ch0_phase_entry_dic[1].get()) + '\n')
            file.write('    Amp = ' + str(Ch0_amp_entry_dic[1].get()) + '\n')
        file.write('CH10: \n    Freq = ' + str(Ch1_f_entry_dic[0].get()) + '\n')
        file.write('    Phase = ' + str(Ch1_phase_entry_dic[0].get()) + '\n')
        file.write('    Amp = ' + str(Ch1_amp_entry_dic[0].get()) + '\n')
        if len(Ch1_amp_entry_dic) > 1:
            file.write('CH11: \n    Freq = ' + str(Ch1_f_entry_dic[1].get()) + '\n')
            file.write('    Phase = ' + str(Ch1_phase_entry_dic[1].get()) + '\n')
            file.write('    Amp = ' + str(Ch1_amp_entry_dic[1].get()))

    CH00 = {
        "Freq": str(Ch0_f_entry_dic[0].get()),
        "Phase": str(Ch0_phase_entry_dic[0].get()),
        "Amp": str(Ch0_amp_entry_dic[0].get())
        }
    if len(Ch0_amp_entry_dic) > 1:
        CH01 = {
        "Freq": str(Ch0_f_entry_dic[1].get()),
        "Phase": str(Ch0_phase_entry_dic[1].get()),
        "Amp": str(Ch0_amp_entry_dic[1].get())
        }
    else:
        CHO1 = {}
    CH10 = {
        "Freq": str(Ch1_f_entry_dic[0].get()),
        "Phase": str(Ch1_phase_entry_dic[0].get()),
        "Amp": str(Ch1_amp_entry_dic[0].get())
        }
    if len(Ch1_amp_entry_dic) > 1:
        CH11 = {
        "Freq": str(Ch1_f_entry_dic[1].get()),
        "Phase": str(Ch1_phase_entry_dic[1].get()),
        "Amp": str(Ch1_amp_entry_dic[1].get())
        }
    else:
        CH11 = {}
    

    x = {
      "CH00": CH00,
      "CH01": CH01,
      "CH10": CH10,
      "CH11": CH11,
    }

    jdata = open("savedata.json", "w")  
    json.dump(x, jdata, indent = 6)  
    jdata.close() 

    os.system("scr_picostream.py")


def Move_Freq():
    global fenetre_freq, fenetre_stop, CH00_freq_ini, CH01_freq_ini, CH00_freq_final, CH01_freq_final, CH10_freq_ini, CH11_freq_ini, CH10_freq_final, CH11_freq_final, step_entry, dtime_entry, ftakedata, Final_value01, Final_value10, Final_value11
    fenetre_freq = Toplevel(fenetre)
    # fenetre_stop = Toplevel(fenetre)

    ftakedata = BooleanVar()
    ftakedata_dic = Checkbutton(fenetre_freq, text='Take data', variable=ftakedata, onvalue=True, offvalue=False)
    ftakedata_dic.grid(row=4, column=5)

    Button(fenetre_freq, text='ok', command=FMove).grid(row=1, column=5)
    Button(fenetre_freq, text='auto fill', command=auto_fill).grid(row=5, column=3)

    freq_ini = Label(fenetre_freq, text="Initial Freq")
    freq_ini.grid(row=0, column=1, sticky=W)
    freq_final = Label(fenetre_freq, text="Final Freq")
    freq_final.grid(row=0, column=2, sticky=W)

    Channel00 = Label(fenetre_freq, text="Ch0-0")
    Channel00.grid(row=1, column=0, sticky=W)
    Start_value00 = DoubleVar()
    Start_value00.set(Ch0_f_entry_dic[0].get())
    CH00_freq_ini = Entry(fenetre_freq, text=Start_value00, state=DISABLED)
    CH00_freq_ini.grid(row=1, column=1)
    Final_value00 = DoubleVar()
    Final_value00.set(Ch0_f_entry_dic[0].get())  # before it was .set(0)
    CH00_freq_final = Entry(fenetre_freq, text=Final_value00)
    CH00_freq_final.grid(row=1, column=2)

    if len(Ch0_f_entry_dic) > 1:
        Channel01 = Label(fenetre_freq, text="Ch0-1")
        Channel01.grid(row=2, column=0, sticky=W)
        Start_value01 = DoubleVar()
        Start_value01.set(Ch0_f_entry_dic[1].get())
        CH01_freq_ini = Entry(fenetre_freq, text=Start_value01, state=DISABLED)
        CH01_freq_ini.grid(row=2, column=1)
        Final_value01 = DoubleVar()
        Final_value01.set(Ch0_f_entry_dic[1].get())
        CH01_freq_final = Entry(fenetre_freq, text=Final_value01)
        CH01_freq_final.grid(row=2, column=2)

    Channel10 = Label(fenetre_freq, text="Ch1-0")
    Channel10.grid(row=3, column=0, sticky=W)
    Start_value10 = DoubleVar()
    Start_value10.set(Ch1_f_entry_dic[0].get())
    CH10_freq_ini = Entry(fenetre_freq, text=Start_value10, state=DISABLED)
    CH10_freq_ini.grid(row=3, column=1)
    Final_value10 = DoubleVar()
    Final_value10.set(Ch1_f_entry_dic[0].get())
    CH10_freq_final = Entry(fenetre_freq, text=Final_value10)
    CH10_freq_final.grid(row=3, column=2)

    if len(Ch1_f_entry_dic) > 1:
        Channel11 = Label(fenetre_freq, text="Ch1-1")
        Channel11.grid(row=4, column=0, sticky=W)
        Start_value11 = DoubleVar()
        Start_value11.set(Ch1_f_entry_dic[1].get())
        CH11_freq_ini = Entry(fenetre_freq, text=Start_value11, state=DISABLED)
        CH11_freq_ini.grid(row=4, column=1)
        Final_value11 = DoubleVar()
        Final_value11.set(Ch1_f_entry_dic[1].get())
        CH11_freq_final = Entry(fenetre_freq, text=Final_value11)
        CH11_freq_final.grid(row=4, column=2)

    step = Label(fenetre_freq, text='freq_step [kHz]')
    step.grid(row=1, column=3, sticky=W)
    step_value = IntVar()
    step_value.set(10)
    step_entry = Entry(fenetre_freq, text=step_value)
    step_entry.grid(row=1, column=4, sticky=W)

    dtime = Label(fenetre_freq, text='time per step [s] (>1.5s)')
    dtime.grid(row=2, column=3, sticky=W)
    dtime_value = IntVar()
    dtime_value.set(0)
    dtime_entry = Entry(fenetre_freq, text=dtime_value)
    dtime_entry.grid(row=2, column=4, sticky=W)


def auto_fill():  # automatically fills the frequencies symmetrically to the first one
    global CH00_freq_ini, CH01_freq_ini, CH00_freq_final, CH01_freq_final, CH10_freq_ini, CH11_freq_ini, CH10_freq_final, CH11_freq_final, Final_value01, Final_value10, Final_value11

    i00 = CH00_freq_ini.get()
    i10 = CH10_freq_ini.get()
    f00 = CH00_freq_final.get()
    delta = float(f00) - float(i00)
    Final_value01.set((float(CH01_freq_ini.get()) - delta))
    if i10 == i00:
        Final_value10.set(f00)
        Final_value11.set((float(CH11_freq_ini.get()) - delta))
    else:
        Final_value11.set(f00)
        Final_value10.set((float(CH10_freq_ini.get()) - delta))


def FMove():
    global running, fenetre_stop

    running = True  # Global flag
    idx = 0  # loop index

    takedata = ftakedata.get()
    step = int(float(step_entry.get())*1e3)
    dt = float(dtime_entry.get())
    a = time.time()
    
    freq_ini_00 = int(float(CH00_freq_ini.get()) * 1e06)
    freq_final_00 = int(float(CH00_freq_final.get()) * 1e06)
    nb_freq00 = int(np.abs(freq_ini_00 - freq_final_00) / (step))
    p00 = DoubleVar()
    p00.set(Ch0_phase_entry_dic[0].get())
    p_00 = float(p00.get())
    a00 = DoubleVar()
    a00.set(Ch0_amp_entry_dic[0].get())
    a_00 = float(a00.get())

    if len(Ch0_f_entry_dic) > 1:
        freq_ini_01 = int(float(CH01_freq_ini.get()) * 1e06)
        freq_final_01 = int(float(CH01_freq_final.get()) * 1e06)
        nb_freq01 = int(np.abs(freq_ini_01 - freq_final_01) / (step))
        p01 = DoubleVar()
        p01.set(Ch0_phase_entry_dic[1].get())
        p_01 = float(p01.get())
        a01 = DoubleVar()
        a01.set(Ch0_amp_entry_dic[1].get())
        a_01 = float(a01.get())

        # if not (int(freq_ini_00 + freq_ini_01)) == 146 * 1e6:
        #     messagebox.showinfo('Error', 'Starting frequencies are not symmetric')
        #     running = False
        # if not (int(freq_final_00 + freq_final_01)) == 146 * 1e6:
        #     messagebox.showinfo('Error', 'Final frequencies are not symmetric')
        #     running = False

    freq_ini_10 = int(float(CH10_freq_ini.get()) * 1e06)
    freq_final_10 = int(float(CH10_freq_final.get()) * 1e06)
    nb_freq10 = int(np.abs(freq_ini_10 - freq_final_10) / (step))
    p10 = DoubleVar()
    p10.set(Ch1_phase_entry_dic[0].get())
    p_10 = float(p10.get())
    a10 = DoubleVar()
    a10.set(Ch1_amp_entry_dic[0].get())
    a_10 = float(a10.get())

    if len(Ch1_f_entry_dic) > 1:
        freq_ini_11 = int(float(CH11_freq_ini.get()) * 1e06)
        freq_final_11 = int(float(CH11_freq_final.get()) * 1e06)
        nb_freq11 = int(np.abs(freq_ini_11 - freq_final_11) / (step))
        p11 = DoubleVar()
        p11.set(Ch1_phase_entry_dic[1].get())
        p_11 = float(p11.get())
        a11 = DoubleVar()
        a11.set(Ch1_amp_entry_dic[1].get())
        a_11 = float(a11.get())
        # if not (int(freq_ini_10 + freq_ini_11)) == 146 * 1e6:
        #     messagebox.showinfo('Error', 'Starting frequencies are not symmetric')
        #     running = False
        # if not (int(freq_final_10 + freq_final_11)) == 146 * 1e6:
        #     messagebox.showinfo('Error', 'Final frequencies are not symmetric')
        #     running = False

    if len(Ch0_f_entry_dic) > 1:
        nb_freq = max(nb_freq00, nb_freq01, nb_freq10, nb_freq11)
    else:
        nb_freq = max(nb_freq00, nb_freq10)

    list_freq_00 = np.linspace(freq_ini_00, freq_final_00, nb_freq + 1)
    if len(Ch0_f_entry_dic) > 1:
        list_freq_01 = np.linspace(freq_ini_01, freq_final_01, nb_freq + 1)
    list_freq_10 = np.linspace(freq_ini_10, freq_final_10, nb_freq + 1)
    if len(Ch1_f_entry_dic) > 1:
        list_freq_11 = np.linspace(freq_ini_11, freq_final_11, nb_freq + 1)

    if running:
        fenetre_stop = Toplevel(fenetre)
        Button(fenetre_stop, text='Interrupt', command=Interrupt).grid(row=2, column=5)

        Ch00 = Label(fenetre_stop, text="Ch_H Freq 1:" + str(list_freq_00[-1] / (1e6)))
        Ch00.grid(row=1, column=1, sticky=W)
        Ch01 = Label(fenetre_stop, text="Ch_H Freq 2:" + str(list_freq_01[-1] / (1e6)))
        Ch01.grid(row=2, column=1, sticky=W)
        Ch10 = Label(fenetre_stop, text="Ch_V Freq 1:" + str(list_freq_10[-1] / (1e6)))
        Ch10.grid(row=3, column=1, sticky=W)
        Ch11 = Label(fenetre_stop, text="Ch_V Freq 2:" + str(list_freq_11[-1] / (1e6)))
        Ch11.grid(row=4, column=1, sticky=W)


    for i in range(0, nb_freq + 1):
        if idx % 2 == 0:
            fenetre.update()
        if running:
            fenetre_freq.destroy()
            idx += 1
            mt1 = time.time()
            Ch0_f_entry_dic[0].delete(0, END)
            Ch0_f_entry_dic[0].insert(1, str(float(list_freq_00[i]) / 1e06))
            if len(Ch0_f_entry_dic) > 1:
                Ch0_f_entry_dic[1].delete(0, END)
                Ch0_f_entry_dic[1].insert(1, str(float(list_freq_01[i]) / 1e06))
            Ch1_f_entry_dic[0].delete(0, END)
            Ch1_f_entry_dic[0].insert(1, str(float(list_freq_10[i]) / 1e06))
            if len(Ch1_f_entry_dic) > 1:
                Ch1_f_entry_dic[1].delete(0, END)
                Ch1_f_entry_dic[1].insert(1, str(float(list_freq_11[i]) / 1e06))
                # add certain time intervall between steps
            data()
            mt2 = time.time() - mt1
            if not takedata:
                if dt > mt2:
                    time.sleep(dt - mt2)
            else:  # Writing header
                header_file_name = 'get_info.dat'
                with open(os.path.join(data_directory, header_file_name), 'w') as file:
                    file.write('CH00: \n    Freq = ' + str(list_freq_00[i]/1e06) + '\n')
                    file.write('    Phase = ' + str(p_00) + '\n')
                    file.write('    Amp = ' + str(a_00) + '\n')
                    if len(Ch0_amp_entry_dic) > 1:
                        file.write('CH01: \n    Freq = ' + str(list_freq_01[i]/1e06) + '\n')
                        file.write('    Phase = ' + str(p_01) + '\n')
                        file.write('    Amp = ' + str(a_01) + '\n')
                    file.write('CH10: \n    Freq = ' + str(list_freq_10[i]/1e06) + '\n')
                    file.write('    Phase = ' + str(p_10) + '\n')
                    file.write('    Amp = ' + str(a_10) + '\n')
                    if len(Ch1_amp_entry_dic) > 1:
                        file.write('CH11: \n    Freq = ' + str(list_freq_11[i]/1e06) + '\n')
                        file.write('    Phase = ' + str(p_11) + '\n')
                        file.write('    Amp = ' + str(a_11))

                CH00 = {
                    "Freq": str(list_freq_00[i]/1e06),
                    "Phase": str(p_00),
                    "Amp": str(a_00)
                    }
                if len(Ch0_amp_entry_dic) > 1:
                    CH01 = {
                        "Freq": str(list_freq_01[i]/1e06),
                        "Phase": str(p_01),
                        "Amp": str(a_01)
                    }
                else:
                    CHO1 = {}
                CH10 = {
                    "Freq": str(list_freq_10[i]/1e06),
                    "Phase": str(p_10),
                    "Amp": str(a_10)
                    }
                if len(Ch1_amp_entry_dic) > 1:
                    CH11 = {
                        "Freq": str(list_freq_11[i]/1e06),
                        "Phase": str(p_11),
                        "Amp": str(a_11)
                    }
                else:
                    CH11 = {}
                

                x = {
                  "CH00": CH00,
                  "CH01": CH01,
                  "CH10": CH10,
                  "CH11": CH11,
                }

                jdata = open("savedata.json", "w")  
                json.dump(x, jdata, indent = 6)  
                jdata.close() 

                os.system("scr_picostream.py")
            # else:
            #    fenetre_freq.destroy()
            #    break
    b = time.time() - a
    if running:
        messagebox.showinfo('Done', 'Freq changed successfully in {}s'.format(b))
    fenetre_stop.destroy()
    print('number of steps: ', nb_freq)
    print('step size: ', round(1e3*np.abs(freq_ini_00 - freq_final_00) / (1e3 * nb_freq)), ' Hz')


def Interrupt():
    global running
    running = False
    fenetre_stop.destroy()


# amplitude movement must only be made in equal difference (or none) between initial and final value
def Move_Amp():
    global fenetre_amp, CH00_amp_ini, CH01_amp_ini, CH00_amp_final, CH01_amp_final, CH10_amp_ini, CH11_amp_ini, CH10_amp_final, CH11_amp_final, step_entry, dtime_entry, atakedata
    fenetre_amp = Toplevel(fenetre)

    atakedata = BooleanVar()
    atakedata_dic = Checkbutton(fenetre_amp, text='Take data', variable=atakedata, onvalue=True, offvalue=False)
    atakedata_dic.grid(row=4, column=5)

    Button(fenetre_amp, text='ok', command=AMove).grid(row=1, column=5)
    Button(fenetre_amp, text='Interrupt', command=Interrupt).grid(row=2, column=5)
    amp_ini = Label(fenetre_amp, text="Initial Amp")
    amp_ini.grid(row=0, column=1, sticky=W)
    amp_final = Label(fenetre_amp, text="Final Amp")
    amp_final.grid(row=0, column=2, sticky=W)

    Channel00 = Label(fenetre_amp, text="Ch0-0")
    Channel00.grid(row=1, column=0, sticky=W)
    Start_value00 = DoubleVar()
    Start_value00.set(Ch0_amp_entry_dic[0].get())
    CH00_amp_ini = Entry(fenetre_amp, text=Start_value00, state=DISABLED)
    CH00_amp_ini.grid(row=1, column=1)
    Final_value00 = DoubleVar()
    Final_value00.set(Ch0_amp_entry_dic[0].get())  # before it was .set(0)
    CH00_amp_final = Entry(fenetre_amp, text=Final_value00)
    CH00_amp_final.grid(row=1, column=2)

    if len(Ch0_amp_entry_dic) > 1:
        Channel01 = Label(fenetre_amp, text="Ch0-1")
        Channel01.grid(row=2, column=0, sticky=W)
        Start_value01 = DoubleVar()
        Start_value01.set(Ch0_amp_entry_dic[1].get())
        CH01_amp_ini = Entry(fenetre_amp, text=Start_value01, state=DISABLED)
        CH01_amp_ini.grid(row=2, column=1)
        Final_value01 = DoubleVar()
        Final_value01.set(Ch0_amp_entry_dic[1].get())
        CH01_amp_final = Entry(fenetre_amp, text=Final_value01)
        CH01_amp_final.grid(row=2, column=2)

    Channel10 = Label(fenetre_amp, text="Ch1-0")
    Channel10.grid(row=3, column=0, sticky=W)
    Start_value10 = DoubleVar()
    Start_value10.set(Ch1_amp_entry_dic[0].get())
    CH10_amp_ini = Entry(fenetre_amp, text=Start_value10, state=DISABLED)
    CH10_amp_ini.grid(row=3, column=1)
    Final_value10 = DoubleVar()
    Final_value10.set(Ch1_amp_entry_dic[0].get())
    CH10_amp_final = Entry(fenetre_amp, text=Final_value10)
    CH10_amp_final.grid(row=3, column=2)

    if len(Ch1_amp_entry_dic) > 1:
        Channel11 = Label(fenetre_amp, text="Ch1-1")
        Channel11.grid(row=4, column=0, sticky=W)
        Start_value11 = DoubleVar()
        Start_value11.set(Ch1_amp_entry_dic[1].get())
        CH11_amp_ini = Entry(fenetre_amp, text=Start_value11, state=DISABLED)
        CH11_amp_ini.grid(row=4, column=1)
        Final_value11 = DoubleVar()
        Final_value11.set(Ch1_amp_entry_dic[1].get())
        CH11_amp_final = Entry(fenetre_amp, text=Final_value11)
        CH11_amp_final.grid(row=4, column=2)

    step = Label(fenetre_amp, text='amp_step [mV]')
    step.grid(row=1, column=3, sticky=W)
    step_value = IntVar()
    step_value.set(1)
    step_entry = Entry(fenetre_amp, text=step_value)
    step_entry.grid(row=1, column=4, sticky=W)

    dtime = Label(fenetre_amp, text='time per step [s] (>1.5s)')
    dtime.grid(row=2, column=3, sticky=W)
    dtime_value = IntVar()
    dtime_value.set(0)
    dtime_entry = Entry(fenetre_amp, text=dtime_value)
    dtime_entry.grid(row=2, column=4, sticky=W)


def AMove():
    global running
    running = True  # Global flag
    idx = 0  # loop index
    takedata = atakedata.get()
    step = float(step_entry.get())
    dt = float(dtime_entry.get())
    a = time.time()
    amp_ini_00 = float(CH00_amp_ini.get())
    amp_final_00 = float(CH00_amp_final.get())
    nb_amp00 = int(np.abs(amp_ini_00 - amp_final_00) / step)
    f00 = DoubleVar()
    f00.set(Ch0_f_entry_dic[0].get())
    f_00 = float(f00.get())
    p00 = DoubleVar()
    p00.set(Ch0_phase_entry_dic[0].get())
    p_00 = float(p00.get())

    if len(Ch0_amp_entry_dic) > 1:
        amp_ini_01 = float(CH01_amp_ini.get())
        amp_final_01 = float(CH01_amp_final.get())
        nb_amp01 = int(np.abs(amp_ini_01 - amp_final_01) / step)
        f01 = DoubleVar()
        f01.set(Ch0_f_entry_dic[1].get())
        f_01 = float(f01.get())
        p01 = DoubleVar()
        p01.set(Ch0_phase_entry_dic[1].get())
        p_01 = float(p01.get())

    amp_ini_10 = float(CH10_amp_ini.get())
    amp_final_10 = float(CH10_amp_final.get())
    nb_amp10 = int(np.abs(amp_ini_10 - amp_final_10) / step)
    f10 = DoubleVar()
    f10.set(Ch1_f_entry_dic[0].get())
    f_10 = float(f10.get())
    p10 = DoubleVar()
    p10.set(Ch1_phase_entry_dic[0].get())
    p_10 = float(p10.get())

    if len(Ch1_amp_entry_dic) > 1:
        amp_ini_11 = float(CH11_amp_ini.get())
        amp_final_11 = float(CH11_amp_final.get())
        nb_amp11 = int(np.abs(amp_ini_11 - amp_final_11) / step)
        f11 = DoubleVar()
        f11.set(Ch1_f_entry_dic[1].get())
        f_11 = float(f11.get())
        p11 = DoubleVar()
        p11.set(Ch1_phase_entry_dic[1].get())
        p_11 = float(p11.get())

    if len(Ch0_amp_entry_dic) > 1:
        nb_amp = max(nb_amp00, nb_amp01, nb_amp10, nb_amp11)
    else:
        nb_amp = max(nb_amp00, nb_amp10)
    print(nb_amp)

    list_amp_00 = np.linspace(amp_ini_00, amp_final_00, nb_amp + 1)
    if len(Ch0_amp_entry_dic) > 1:
        list_amp_01 = np.linspace(amp_ini_01, amp_final_01, nb_amp + 1)
    list_amp_10 = np.linspace(amp_ini_10, amp_final_10, nb_amp + 1)
    if len(Ch1_amp_entry_dic) > 1:
        list_amp_11 = np.linspace(amp_ini_11, amp_final_11, nb_amp + 1)

    for i in range(0, nb_amp + 1):
        if idx % 2 == 0:
            fenetre.update()
        if running:
            idx += 1
            mt1 = time.time()
            Ch0_amp_entry_dic[0].delete(0, END)
            Ch0_amp_entry_dic[0].insert(1, str(list_amp_00[i]))
            if len(Ch0_amp_entry_dic) > 1:
                Ch0_amp_entry_dic[1].delete(0, END)
                Ch0_amp_entry_dic[1].insert(1, str(list_amp_01[i]))
            Ch1_amp_entry_dic[0].delete(0, END)
            Ch1_amp_entry_dic[0].insert(1, str(list_amp_10[i]))
            if len(Ch1_amp_entry_dic) > 1:
                Ch1_amp_entry_dic[1].delete(0, END)
                Ch1_amp_entry_dic[1].insert(1, str(list_amp_11[i]))
            # add certain time intervall between steps
            data()
            mt2 = time.time() - mt1
            if not takedata:
                if dt > mt2:
                    time.sleep(dt - mt2)
            else:  # Writing header
                header_file_name = 'get_info.dat'
                with open(os.path.join(data_directory, header_file_name), 'w') as file:
                    file.write('CH00: \n    Freq = ' + str(f_00) + '\n')
                    file.write('    Phase = ' + str(p_00) + '\n')
                    file.write('    Amp = ' + str(list_amp_00[i]) + '\n')
                    if len(Ch0_amp_entry_dic) > 1:
                        file.write('CH01: \n    Freq = ' + str(f_01) + '\n')
                        file.write('    Phase = ' + str(p_01) + '\n')
                        file.write('    Amp = ' + str(list_amp_01[i]) + '\n')
                    file.write('CH10: \n    Freq = ' + str(f_10) + '\n')
                    file.write('    Phase = ' + str(p_10) + '\n')
                    file.write('    Amp = ' + str(list_amp_10[i]) + '\n')
                    if len(Ch1_amp_entry_dic) > 1:
                        file.write('CH11: \n    Freq = ' + str(f_11) + '\n')
                        file.write('    Phase = ' + str(p_11) + '\n')
                        file.write('    Amp = ' + str(list_amp_11[i]))

                CH00 = {
                    "Freq": str(f_00),
                    "Phase": str(p_00),
                    "Amp": str(list_amp_00[i])
                    }
                if len(Ch0_amp_entry_dic) > 1:
                    CH01 = {
                        "Freq": str(f_01),
                        "Phase": str(p_01),
                        "Amp": str(list_amp_01[i])
                    }
                else:
                    CHO1 = {}
                CH10 = {
                    "Freq": str(f_10),
                    "Phase": str(p_10),
                    "Amp": str(list_amp_10[i])
                    }
                if len(Ch1_amp_entry_dic) > 1:
                    CH11 = {
                        "Freq": str(f_11),
                        "Phase": str(p_11),
                        "Amp": str(list_amp_11[i])
                    }
                else:
                    CH11 = {}
                

                x = {
                  "CH00": CH00,
                  "CH01": CH01,
                  "CH10": CH10,
                  "CH11": CH11,
                }

                jdata = open("savedata.json", "w")  
                json.dump(x, jdata, indent = 6)  
                jdata.close() 

                os.system("scr_picostream.py")

    b = time.time() - a
    messagebox.showinfo('Done', 'Amplitude changed successfully in {}s'.format(b))

    fenetre_amp.destroy()


##move phase
def Move_Phase():
    global fenetre_phase, CH00_phase_ini, CH01_phase_ini, CH00_phase_final, CH01_phase_final, CH10_phase_ini, CH11_phase_ini, CH10_phase_final, CH11_phase_final, step_entry, dtime_entry, ptakedata
    fenetre_phase = Toplevel(fenetre)

    ptakedata = BooleanVar()
    ptakedata_dic = Checkbutton(fenetre_phase, text='Take data', variable=ptakedata, onvalue=True, offvalue=False)
    ptakedata_dic.grid(row=4, column=5)

    Button(fenetre_phase, text='ok', command=PMove).grid(row=1, column=5)
    Button(fenetre_phase, text='Interrupt', command=Interrupt).grid(row=2, column=5)
    phase_ini = Label(fenetre_phase, text="Initial phase")
    phase_ini.grid(row=0, column=1, sticky=W)
    phase_final = Label(fenetre_phase, text="Final phase")
    phase_final.grid(row=0, column=2, sticky=W)

    Channel00 = Label(fenetre_phase, text="Ch0-0")
    Channel00.grid(row=1, column=0, sticky=W)
    Start_value00 = DoubleVar()
    Start_value00.set(Ch0_phase_entry_dic[0].get())
    CH00_phase_ini = Entry(fenetre_phase, text=Start_value00, state=DISABLED)
    CH00_phase_ini.grid(row=1, column=1)
    Final_value00 = DoubleVar()
    Final_value00.set(Ch0_phase_entry_dic[0].get())  # before it was .set(0)
    CH00_phase_final = Entry(fenetre_phase, text=Final_value00)
    CH00_phase_final.grid(row=1, column=2)

    if len(Ch0_phase_entry_dic) > 1:
        Channel01 = Label(fenetre_phase, text="Ch0-1")
        Channel01.grid(row=2, column=0, sticky=W)
        Start_value01 = DoubleVar()
        Start_value01.set(Ch0_phase_entry_dic[1].get())
        CH01_phase_ini = Entry(fenetre_phase, text=Start_value01, state=DISABLED)
        CH01_phase_ini.grid(row=2, column=1)
        Final_value01 = DoubleVar()
        Final_value01.set(Ch0_phase_entry_dic[1].get())
        CH01_phase_final = Entry(fenetre_phase, text=Final_value01)
        CH01_phase_final.grid(row=2, column=2)

    Channel10 = Label(fenetre_phase, text="Ch1-0")
    Channel10.grid(row=3, column=0, sticky=W)
    Start_value10 = DoubleVar()
    Start_value10.set(Ch1_phase_entry_dic[0].get())
    CH10_phase_ini = Entry(fenetre_phase, text=Start_value10, state=DISABLED)
    CH10_phase_ini.grid(row=3, column=1)
    Final_value10 = DoubleVar()
    Final_value10.set(Ch1_phase_entry_dic[0].get())
    CH10_phase_final = Entry(fenetre_phase, text=Final_value10)
    CH10_phase_final.grid(row=3, column=2)

    if len(Ch1_phase_entry_dic) > 1:
        Channel11 = Label(fenetre_phase, text="Ch1-1")
        Channel11.grid(row=4, column=0, sticky=W)
        Start_value11 = DoubleVar()
        Start_value11.set(Ch1_phase_entry_dic[1].get())
        CH11_phase_ini = Entry(fenetre_phase, text=Start_value11, state=DISABLED)
        CH11_phase_ini.grid(row=4, column=1)
        Final_value11 = DoubleVar()
        Final_value11.set(Ch1_phase_entry_dic[1].get())
        CH11_phase_final = Entry(fenetre_phase, text=Final_value11)
        CH11_phase_final.grid(row=4, column=2)

    step = Label(fenetre_phase, text='phase_step [°]')
    step.grid(row=1, column=3, sticky=W)
    step_value = IntVar()
    step_value.set(1)
    step_entry = Entry(fenetre_phase, text=step_value)
    step_entry.grid(row=1, column=4, sticky=W)

    dtime = Label(fenetre_phase, text='time per step [s] (>1.5s)')
    dtime.grid(row=2, column=3, sticky=W)
    dtime_value = IntVar()
    dtime_value.set(0)
    dtime_entry = Entry(fenetre_phase, text=dtime_value)
    dtime_entry.grid(row=2, column=4, sticky=W)


def PMove():
    global running
    running = True  # Global flag
    idx = 0  # loop index
    takedata = ptakedata.get()
    step = int(step_entry.get())
    dt = float(dtime_entry.get())
    a = time.time()
    phase_ini_00 = int(float(CH00_phase_ini.get()))
    phase_final_00 = int(float(CH00_phase_final.get()))
    nb_phase00 = int(np.abs(phase_ini_00 - phase_final_00) / step)
    f00 = DoubleVar()
    f00.set(Ch0_f_entry_dic[0].get())
    f_00 = float(f00.get())
    a00 = DoubleVar()
    a00.set(Ch0_amp_entry_dic[0].get())
    a_00 = float(a00.get())

    if len(Ch0_phase_entry_dic) > 1:
        phase_ini_01 = int(float(CH01_phase_ini.get()))
        phase_final_01 = int(float(CH01_phase_final.get()))
        nb_phase01 = int(np.abs(phase_ini_01 - phase_final_01) / step)
        f01 = DoubleVar()
        f01.set(Ch0_f_entry_dic[1].get())
        f_01 = float(f01.get())
        a01 = DoubleVar()
        a01.set(Ch0_amp_entry_dic[1].get())
        a_01 = float(a01.get())

    phase_ini_10 = int(float(CH10_phase_ini.get()))
    phase_final_10 = int(float(CH10_phase_final.get()))
    nb_phase10 = int(np.abs(phase_ini_10 - phase_final_10) / step)
    f10 = DoubleVar()
    f10.set(Ch1_f_entry_dic[0].get())
    f_10 = float(f10.get())
    a10 = DoubleVar()
    a10.set(Ch1_amp_entry_dic[0].get())
    a_10 = float(a10.get())

    if len(Ch1_phase_entry_dic) > 1:
        phase_ini_11 = int(float(CH11_phase_ini.get()))
        phase_final_11 = int(float(CH11_phase_final.get()))
        nb_phase11 = int(np.abs(phase_ini_11 - phase_final_11) / step)
        f11 = DoubleVar()
        f11.set(Ch1_f_entry_dic[1].get())
        f_11 = float(f11.get())
        a11 = DoubleVar()
        a11.set(Ch1_amp_entry_dic[1].get())
        a_11 = float(a11.get())

    if len(Ch0_phase_entry_dic) > 1:
        nb_phase = max(nb_phase00, nb_phase01, nb_phase10, nb_phase11)
    else:
        nb_phase = max(nb_phase00, nb_phase10)
    print(nb_phase)

    list_phase_00 = np.linspace(phase_ini_00, phase_final_00, nb_phase + 1)
    if len(Ch0_phase_entry_dic) > 1:
        list_phase_01 = np.linspace(phase_ini_01, phase_final_01, nb_phase + 1)
    list_phase_10 = np.linspace(phase_ini_10, phase_final_10, nb_phase + 1)
    if len(Ch1_phase_entry_dic) > 1:
        list_phase_11 = np.linspace(phase_ini_11, phase_final_11, nb_phase + 1)

    for i in range(0, nb_phase + 1):
        if idx % 2 == 0:
            fenetre.update()
        if running:
            idx += 1
            mt1 = time.time()
            Ch0_phase_entry_dic[0].delete(0, END)
            Ch0_phase_entry_dic[0].insert(1, str(list_phase_00[i]))
            if len(Ch0_phase_entry_dic) > 1:
                Ch0_phase_entry_dic[1].delete(0, END)
                Ch0_phase_entry_dic[1].insert(1, str(list_phase_01[i]))
            Ch1_phase_entry_dic[0].delete(0, END)
            Ch1_phase_entry_dic[0].insert(1, str(list_phase_10[i]))
            if len(Ch1_phase_entry_dic) > 1:
                Ch1_phase_entry_dic[1].delete(0, END)
                Ch1_phase_entry_dic[1].insert(1, str(list_phase_11[i]))
            # add certain time intervall between steps
            data()
            mt2 = time.time() - mt1
            if not takedata:
                if dt > mt2:
                    time.sleep(dt - mt2)
            else:  # Writing header
                header_file_name = 'get_info.dat'
                with open(os.path.join(data_directory, header_file_name), 'w') as file:
                    file.write('CH00: \n    Freq = ' + str(f_00) + '\n')
                    file.write('    Phase = ' + str(list_phase_00[i]) + '\n')
                    file.write('    Amp = ' + str(a_00) + '\n')
                    if len(Ch0_amp_entry_dic) > 1:
                        file.write('CH01: \n    Freq = ' + str(f_01) + '\n')
                        file.write('    Phase = ' + str(list_phase_01[i]) + '\n')
                        file.write('    Amp = ' + str(a_01) + '\n')
                    file.write('CH10: \n    Freq = ' + str(f_10) + '\n')
                    file.write('    Phase = ' + str(list_phase_10[i]) + '\n')
                    file.write('    Amp = ' + str(a_10) + '\n')
                    if len(Ch1_amp_entry_dic) > 1:
                        file.write('CH11: \n    Freq = ' + str(f_11) + '\n')
                        file.write('    Phase = ' + str(list_phase_11[i]) + '\n')
                        file.write('    Amp = ' + str(a_11))

                
                CH00 = {
                    "Freq": str(f_00),
                    "Phase": str(list_phase_00[i]),
                    "Amp": str(a_00)
                    }
                if len(Ch0_amp_entry_dic) > 1:
                    CH01 = {
                        "Freq": str(f_01),
                        "Phase": str(list_phase_01[i]),
                        "Amp": str(a_01)
                    }
                else:
                    CHO1 = {}
                CH10 = {
                    "Freq": str(f_10),
                    "Phase": str(list_phase_10[i]),
                    "Amp": str(a_10)
                    }
                if len(Ch1_amp_entry_dic) > 1:
                    CH11 = {
                        "Freq": str(f_11),
                        "Phase": str(list_phase_11[i]),
                        "Amp": str(a_11)
                    }
                else:
                    CH11 = {}
                

                x = {
                  "CH00": CH00,
                  "CH01": CH01,
                  "CH10": CH10,
                  "CH11": CH11,
                }

                jdata = open("savedata.json", "w")  
                json.dump(x, jdata, indent = 6)  
                jdata.close() 

                os.system("scr_picostream.py")

    b = time.time() - a
    messagebox.showinfo('Done', 'Phase changed successfully in {}s'.format(b))

    fenetre_phase.destroy()

def Move_AP():
    global fenetre_ap, CH00_amp_ini, CH01_amp_ini, CH00_amp_final, CH01_amp_final, CH10_amp_ini, CH11_amp_ini, CH10_amp_final, CH11_amp_final, astep_entry, dtime_entry, aptakedata, pstep_entry,  CH00_phase_ini, CH01_phase_ini, CH00_phase_final, CH01_phase_final, CH10_phase_ini, CH11_phase_ini, CH10_phase_final, CH11_phase_final, step_entry
    fenetre_ap = Toplevel(fenetre)

    aptakedata = BooleanVar()
    aptakedata_dic = Checkbutton(fenetre_ap, text='Take data', variable=aptakedata, onvalue=True, offvalue=False)
    aptakedata_dic.grid(row=4, column=5)

    Button(fenetre_ap, text='ok', command=APMove).grid(row=1, column=5)
    Button(fenetre_ap, text='Interrupt', command=Interrupt).grid(row=2, column=5)
    amp_ini = Label(fenetre_ap, text="Initial Amp")
    amp_ini.grid(row=0, column=1, sticky=W)
    amp_final = Label(fenetre_ap, text="Final Amp")
    amp_final.grid(row=0, column=2, sticky=W)

    phase_ini = Label(fenetre_ap, text="Initial Phase")
    phase_ini.grid(row=6, column=1, sticky=W)
    phase_final = Label(fenetre_ap, text="Final Phase")
    phase_final.grid(row=6, column=2, sticky=W)

    Channela00 = Label(fenetre_ap, text="Ch0-0")
    Channela00.grid(row=1, column=0, sticky=W)
    Start_valuea00 = DoubleVar()
    Start_valuea00.set(Ch0_amp_entry_dic[0].get())
    CH00_amp_ini = Entry(fenetre_ap, text=Start_valuea00, state=DISABLED)
    CH00_amp_ini.grid(row=1, column=1)
    Final_valuea00 = DoubleVar()
    Final_valuea00.set(Ch0_amp_entry_dic[0].get())  # before it was .set(0)
    CH00_amp_final = Entry(fenetre_ap, text=Final_valuea00)
    CH00_amp_final.grid(row=1, column=2)

    Channelp00 = Label(fenetre_ap, text="Ch0-0")
    Channelp00.grid(row=7, column=0, sticky=W)
    Start_valuep00 = DoubleVar()
    Start_valuep00.set(Ch0_phase_entry_dic[0].get())
    CH00_phase_ini = Entry(fenetre_ap, text=Start_valuep00, state=DISABLED)
    CH00_phase_ini.grid(row=7, column=1)
    Final_valuep00 = DoubleVar()
    Final_valuep00.set(Ch0_phase_entry_dic[0].get())  # before it was .set(0)
    CH00_phase_final = Entry(fenetre_ap, text=Final_valuep00)
    CH00_phase_final.grid(row=7, column=2)

    if len(Ch0_amp_entry_dic) > 1:
        Channela01 = Label(fenetre_ap, text="Ch0-1")
        Channela01.grid(row=2, column=0, sticky=W)
        Start_valuea01 = DoubleVar()
        Start_valuea01.set(Ch0_amp_entry_dic[1].get())
        CH01_amp_ini = Entry(fenetre_ap, text=Start_valuea01, state=DISABLED)
        CH01_amp_ini.grid(row=2, column=1)
        Final_valuea01 = DoubleVar()
        Final_valuea01.set(Ch0_amp_entry_dic[1].get())
        CH01_amp_final = Entry(fenetre_ap, text=Final_valuea01)
        CH01_amp_final.grid(row=2, column=2)

        Channelp01 = Label(fenetre_ap, text="Ch0-1")
        Channelp01.grid(row=8, column=0, sticky=W)
        Start_valuep01 = DoubleVar()
        Start_valuep01.set(Ch0_phase_entry_dic[1].get())
        CH01_phase_ini = Entry(fenetre_ap, text=Start_valuep01, state=DISABLED)
        CH01_phase_ini.grid(row=8, column=1)
        Final_valuep01 = DoubleVar()
        Final_valuep01.set(Ch0_phase_entry_dic[1].get())
        CH01_phase_final = Entry(fenetre_ap, text=Final_valuep01)
        CH01_phase_final.grid(row=8, column=2)

    Channela10 = Label(fenetre_ap, text="Ch1-0")
    Channela10.grid(row=3, column=0, sticky=W)
    Start_valuea10 = DoubleVar()
    Start_valuea10.set(Ch1_amp_entry_dic[0].get())
    CH10_amp_ini = Entry(fenetre_ap, text=Start_valuea10, state=DISABLED)
    CH10_amp_ini.grid(row=3, column=1)
    Final_valuea10 = DoubleVar()
    Final_valuea10.set(Ch1_amp_entry_dic[0].get())
    CH10_amp_final = Entry(fenetre_ap, text=Final_valuea10)
    CH10_amp_final.grid(row=3, column=2)

    Channelp10 = Label(fenetre_ap, text="Ch1-0")
    Channelp10.grid(row=9, column=0, sticky=W)
    Start_valuep10 = DoubleVar()
    Start_valuep10.set(Ch1_phase_entry_dic[0].get())
    CH10_phase_ini = Entry(fenetre_ap, text=Start_valuep10, state=DISABLED)
    CH10_phase_ini.grid(row=9, column=1)
    Final_valuep10 = DoubleVar()
    Final_valuep10.set(Ch1_phase_entry_dic[0].get())
    CH10_phase_final = Entry(fenetre_ap, text=Final_valuep10)
    CH10_phase_final.grid(row=9, column=2)

    if len(Ch1_amp_entry_dic) > 1:
        Channela11 = Label(fenetre_ap, text="Ch1-1")
        Channela11.grid(row=4, column=0, sticky=W)
        Start_valuea11 = DoubleVar()
        Start_valuea11.set(Ch1_amp_entry_dic[1].get())
        CH11_amp_ini = Entry(fenetre_ap, text=Start_valuea11, state=DISABLED)
        CH11_amp_ini.grid(row=4, column=1)
        Final_valuea11 = DoubleVar()
        Final_valuea11.set(Ch1_amp_entry_dic[1].get())
        CH11_amp_final = Entry(fenetre_ap, text=Final_valuea11)
        CH11_amp_final.grid(row=4, column=2)

        Channelp11 = Label(fenetre_ap, text="Ch1-1")
        Channelp11.grid(row=10, column=0, sticky=W)
        Start_valuep11 = DoubleVar()
        Start_valuep11.set(Ch1_phase_entry_dic[1].get())
        CH11_phase_ini = Entry(fenetre_ap, text=Start_valuep11, state=DISABLED)
        CH11_phase_ini.grid(row=10, column=1)
        Final_valuep11 = DoubleVar()
        Final_valuep11.set(Ch1_phase_entry_dic[1].get())
        CH11_phase_final = Entry(fenetre_ap, text=Final_valuep11)
        CH11_phase_final.grid(row=10, column=2)

    astep = Label(fenetre_ap, text='amp_step [mV]')
    astep.grid(row=1, column=3, sticky=W)
    astep_value = IntVar()
    astep_value.set(1)
    astep_entry = Entry(fenetre_ap, text=astep_value)
    astep_entry.grid(row=1, column=4, sticky=W)

    pstep = Label(fenetre_ap, text='phase_step [°]')
    pstep.grid(row=7, column=3, sticky=W)
    pstep_value = IntVar()
    pstep_value.set(1)
    pstep_entry = Entry(fenetre_ap, text=pstep_value)
    pstep_entry.grid(row=7, column=4, sticky=W)

    dtime = Label(fenetre_ap, text='time per step [s] (>1.5s)')
    dtime.grid(row=2, column=3, sticky=W)
    dtime_value = IntVar()
    dtime_value.set(0)
    dtime_entry = Entry(fenetre_ap, text=dtime_value)
    dtime_entry.grid(row=2, column=4, sticky=W)


def APMove():
    global running
    running = True  # Global flag
    idx = 0  # loop index
    takedata = aptakedata.get()
    astep = float(astep_entry.get())
    pstep = int(pstep_entry.get())
    dt = float(dtime_entry.get())
    a = time.time()
    amp_ini_00 = float(CH00_amp_ini.get())
    amp_final_00 = float(CH00_amp_final.get())
    phase_ini_00 = int(float(CH00_phase_ini.get()))
    phase_final_00 = int(float(CH00_phase_final.get()))
    nb_amp00 = int(np.abs(amp_ini_00 - amp_final_00) / astep)
    nb_phase00 = int(np.abs(phase_ini_00 - phase_final_00) / pstep)
    f00 = DoubleVar()
    f00.set(Ch0_f_entry_dic[0].get())
    f_00 = float(f00.get())

    if len(Ch0_amp_entry_dic) > 1:
        amp_ini_01 = float(CH01_amp_ini.get())
        amp_final_01 = float(CH01_amp_final.get())
        phase_ini_01 = int(float(CH01_phase_ini.get()))
        phase_final_01 = int(float(CH01_phase_final.get()))
        nb_amp01 = int(np.abs(amp_ini_01 - amp_final_01) / astep)
        nb_phase01 = int(np.abs(phase_ini_01 - phase_final_01) / pstep)
        f01 = DoubleVar()
        f01.set(Ch0_f_entry_dic[1].get())
        f_01 = float(f01.get())

    amp_ini_10 = float(CH10_amp_ini.get())
    amp_final_10 = float(CH10_amp_final.get())
    phase_ini_10 = int(float(CH10_phase_ini.get()))
    phase_final_10 = int(float(CH10_phase_final.get()))
    nb_amp10 = int(np.abs(amp_ini_10 - amp_final_10) / astep)
    nb_phase10 = int(np.abs(phase_ini_10 - phase_final_10) / pstep)
    f10 = DoubleVar()
    f10.set(Ch1_f_entry_dic[0].get())
    f_10 = float(f10.get())

    if len(Ch1_amp_entry_dic) > 1:
        amp_ini_11 = float(CH11_amp_ini.get())
        amp_final_11 = float(CH11_amp_final.get())
        phase_ini_11 = int(float(CH11_phase_ini.get()))
        phase_final_11 = int(float(CH11_phase_final.get()))
        nb_amp11 = int(np.abs(amp_ini_11 - amp_final_11) / astep)
        nb_phase11 = int(np.abs(phase_ini_11 - phase_final_11) / pstep)
        f11 = DoubleVar()
        f11.set(Ch1_f_entry_dic[1].get())
        f_11 = float(f11.get())

    if len(Ch0_amp_entry_dic) > 1:
        nb_amp = max(nb_amp00, nb_amp01, nb_amp10, nb_amp11)
        nb_phase = max(nb_phase00, nb_phase01, nb_phase10, nb_phase11)
    else:
        nb_amp = max(nb_amp00, nb_amp10)
        nb_phase = max(nb_phase00, nb_phase10)
    print("Amplitude steps: ", nb_amp)
    print("Phase steps: ", nb_phase)

    list_amp_00 = np.linspace(amp_ini_00, amp_final_00, nb_amp + 1)
    list_phase_00 = np.linspace(phase_ini_00, phase_final_00, nb_phase + 1)
    if len(Ch0_amp_entry_dic) > 1:
        list_amp_01 = np.linspace(amp_ini_01, amp_final_01, nb_amp + 1)
        list_phase_01 = np.linspace(phase_ini_01, phase_final_01, nb_phase + 1)
    list_amp_10 = np.linspace(amp_ini_10, amp_final_10, nb_amp + 1)
    list_phase_10 = np.linspace(phase_ini_10, phase_final_10, nb_phase + 1)
    if len(Ch1_amp_entry_dic) > 1:
        list_amp_11 = np.linspace(amp_ini_11, amp_final_11, nb_amp + 1)
        list_phase_11 = np.linspace(phase_ini_11, phase_final_11, nb_phase + 1)

    for j in range(0, nb_phase + 1):
        if running:
            Ch0_phase_entry_dic[0].delete(0, END)
            Ch0_phase_entry_dic[0].insert(1, str(list_phase_00[j]))
            if len(Ch0_phase_entry_dic) > 1:
                Ch0_phase_entry_dic[1].delete(0, END)
                Ch0_phase_entry_dic[1].insert(1, str(list_phase_01[j]))
            Ch1_phase_entry_dic[0].delete(0, END)
            Ch1_phase_entry_dic[0].insert(1, str(list_phase_10[j]))
            if len(Ch1_phase_entry_dic) > 1:
                Ch1_phase_entry_dic[1].delete(0, END)
                Ch1_phase_entry_dic[1].insert(1, str(list_phase_11[j]))

            for i in range(0, nb_amp + 1):
                if idx % 2 == 0:
                    fenetre.update()
                if running:
                    idx += 1
                    mt1 = time.time()
                    Ch0_amp_entry_dic[0].delete(0, END)
                    Ch0_amp_entry_dic[0].insert(1, str(list_amp_00[i]))
                    if len(Ch0_amp_entry_dic) > 1:
                        Ch0_amp_entry_dic[1].delete(0, END)
                        Ch0_amp_entry_dic[1].insert(1, str(list_amp_01[i]))
                    Ch1_amp_entry_dic[0].delete(0, END)
                    Ch1_amp_entry_dic[0].insert(1, str(list_amp_10[i]))
                    if len(Ch1_amp_entry_dic) > 1:
                        Ch1_amp_entry_dic[1].delete(0, END)
                        Ch1_amp_entry_dic[1].insert(1, str(list_amp_11[i]))
                    # add certain time intervall between steps
                    data()
                    mt2 = time.time() - mt1
                    if not takedata:
                        if dt > mt2:
                            time.sleep(dt - mt2)
                    else:  # Writing header
                        header_file_name = 'get_info.dat'
                        with open(os.path.join(data_directory, header_file_name), 'w') as file:
                            file.write('CH00: \n    Freq = ' + str(f_00) + '\n')
                            file.write('    Phase = ' + str(list_phase_00[j]) + '\n')
                            file.write('    Amp = ' + str(list_amp_00[i]) + '\n')
                            if len(Ch0_amp_entry_dic) > 1:
                                file.write('CH01: \n    Freq = ' + str(f_01) + '\n')
                                file.write('    Phase = ' + str(list_phase_01[j]) + '\n')
                                file.write('    Amp = ' + str(list_amp_01[i]) + '\n')
                            file.write('CH10: \n    Freq = ' + str(f_10) + '\n')
                            file.write('    Phase = ' + str(list_phase_10[j]) + '\n')
                            file.write('    Amp = ' + str(list_amp_10[i]) + '\n')
                            if len(Ch1_amp_entry_dic) > 1:
                                file.write('CH11: \n    Freq = ' + str(f_11) + '\n')
                                file.write('    Phase = ' + str(list_phase_11[j]) + '\n')
                                file.write('    Amp = ' + str(list_amp_11[i]))

                                            
                        CH00 = {
                            "Freq": str(f_00),
                            "Phase": str(list_phase_00[j]),
                            "Amp": str(list_amp_00[i])
                            }
                        if len(Ch0_amp_entry_dic) > 1:
                            CH01 = {
                                "Freq": str(f_01),
                                "Phase": str(list_phase_01[j]),
                                "Amp": str(list_amp_01[i])
                            }
                        else:
                            CHO1 = {}
                        CH10 = {
                            "Freq": str(f_10),
                            "Phase": str(list_phase_10[j]),
                            "Amp": str(list_amp_10[i])
                            }
                        if len(Ch1_amp_entry_dic) > 1:
                            CH11 = {
                                "Freq": str(f_11),
                                "Phase": str(list_phase_11[j]),
                                "Amp": str(list_amp_11[i])
                            }
                        else:
                            CH11 = {}
                        

                        x = {
                          "CH00": CH00,
                          "CH01": CH01,
                          "CH10": CH10,
                          "CH11": CH11,
                        }

                        jdata = open("savedata.json", "w")  
                        json.dump(x, jdata, indent = 6)  
                        jdata.close() 

                        os.system("scr_picostream.py")

    b = time.time() - a
    messagebox.showinfo('Done', 'Amplitude and Phase changed successfully in {}s'.format(b))

    fenetre_ap.destroy()




def close():
    fenetre.destroy()
    spcm_dwSetParam_i32(hCard, SPC_M2CMD, M2CMD_CARD_STOP)


# **************************************************************************
# main
# **************************************************************************
#

# open card
# uncomment the second line and replace the IP address to use remote
# cards like in a generatorNETBOX


hCard = spcm_hOpen(create_string_buffer(b'/dev/spcm0'))
# hCard = spcm_hOpen (create_string_buffer (b'TCPIP::192.168.1.10::inst0::INSTR'))
if hCard == None:
    sys.stdout.write("no card found...\n")
    exit(1)

# read type, function and sn and check for D/A card
lCardType = int32(0)
spcm_dwGetParam_i32(hCard, SPC_PCITYP, byref(lCardType))
lSerialNumber = int32(0)
spcm_dwGetParam_i32(hCard, SPC_PCISERIALNO, byref(lSerialNumber))
lFncType = int32(0)
spcm_dwGetParam_i32(hCard, SPC_FNCTYPE, byref(lFncType))

sCardName = szTypeToName(lCardType.value)
if lFncType.value == SPCM_TYPE_AO:
    sys.stdout.write("Found: {0} sn {1:05d}\n".format(sCardName, lSerialNumber.value))
else:
    sys.stdout.write(
        "This is an example for D/A cards.\nCard: {0} sn {1:05d} not supported by example\n".format(sCardName,
                                                                                                    lSerialNumber.value))
    spcm_vClose(hCard)
    exit(1)

dwErr = spcm_dwSetParam_i32(hCard, SPC_M2CMD, M2CMD_CARD_RESET)
if dwErr != ERR_OK:
    spcm_dwSetParam_i32(hCard, SPC_M2CMD, M2CMD_CARD_STOP)
    sys.stdout.write("... Error: {0:d}\n".format(dwErr))
    exit(1)

# setup the mode
llChEnable = int64(CHANNEL0)
lMaxSegments = int32(32)
spcm_dwSetParam_i32(hCard, SPC_CARDMODE, SPC_REP_STD_SEQUENCE)
spcm_dwSetParam_i64(hCard, SPC_CHENABLE, CHANNEL0 | CHANNEL1)
spcm_dwSetParam_i32(hCard, SPC_SEQMODE_MAXSEGMENTS, 2)

# setup trigger
spcm_dwSetParam_i32(hCard, SPC_TRIG_ORMASK, SPC_TMASK_SOFTWARE)  # software trigger
spcm_dwSetParam_i32(hCard, SPC_TRIG_ANDMASK, 0)
spcm_dwSetParam_i32(hCard, SPC_TRIG_CH_ORMASK0, 0)
spcm_dwSetParam_i32(hCard, SPC_TRIG_CH_ORMASK1, 0)
spcm_dwSetParam_i32(hCard, SPC_TRIG_CH_ANDMASK0, 0)
spcm_dwSetParam_i32(hCard, SPC_TRIG_CH_ANDMASK1, 0)
spcm_dwSetParam_i32(hCard, SPC_TRIGGEROUT, 0)

# setup the channels
lNumChannels = int32(0)
spcm_dwGetParam_i32(hCard, SPC_CHCOUNT, byref(lNumChannels))
spcm_dwSetParam_i32(hCard, SPC_ENABLEOUT0, 1)
spcm_dwSetParam_i32(hCard, SPC_AMP0, 1000)
spcm_dwSetParam_i32(hCard, SPC_CH0_STOPLEVEL, SPCM_STOPLVL_HOLDLAST)
spcm_dwSetParam_i32(hCard, SPC_ENABLEOUT1, 1)
spcm_dwSetParam_i32(hCard, SPC_AMP1, 1000)
spcm_dwSetParam_i32(hCard, SPC_CH1_STOPLEVEL, SPCM_STOPLVL_HOLDLAST)

# Setup GPIO (X0) port to async output
spcm_dwSetParam_i32 (hCard, SPCM_X0_MODE, SPCM_XMODE_ASYNCOUT) # Set X0 to ASYNC_OUT
spcm_dwSetParam_i32 (hCard, SPCM_XX_ASYNCIO, 0) # Set output to 0

# set samplerate to 860 MHz (M2i) or 50 MHz, no clock output
spcm_dwSetParam_i32(hCard, SPC_CLOCKMODE, SPC_CM_EXTREFCLOCK)
spcm_dwSetParam_i32(hCard, SPC_REFERENCECLOCK, 10000000)
if ((lCardType.value & TYP_SERIESMASK) == TYP_M4IEXPSERIES) or ((lCardType.value & TYP_SERIESMASK) == TYP_M4XEXPSERIES):
    spcm_dwSetParam_i64(hCard, SPC_SAMPLERATE, MEGA(860))
else:
    spcm_dwSetParam_i64(hCard, SPC_SAMPLERATE, MEGA(1))
spcm_dwSetParam_i32(hCard, SPC_CLOCKOUT, 0)

# generate the data and transfer it to the card
lMaxADCValue = int32(0)
spcm_dwGetParam_i32(hCard, SPC_MIINST_MAXADCVALUE, byref(lMaxADCValue))
vDoDataCalculation(lCardType, int32(lMaxADCValue.value - 1))
# (f_c,f_factor)=vDoDataCalculation (lCardType,int32 (lMaxADCValue.value - 1))
sys.stdout.write("... data has been transferred to board memory\n")

# define the sequence in which the segments will be replayed
vConfigureSequence(hCard)
sys.stdout.write("... sequence configured\n")

# We'll start and wait until all sequences are replayed.
spcm_dwSetParam_i32(hCard, SPC_TIMEOUT, 0)
sys.stdout.write("\nStarting the card\n")
dwErr = spcm_dwSetParam_i32(hCard, SPC_M2CMD, M2CMD_CARD_START | M2CMD_CARD_ENABLETRIGGER)
if dwErr != ERR_OK:
    spcm_dwSetParam_i32(hCard, SPC_M2CMD, M2CMD_CARD_STOP)
    sys.stdout.write("... Error: {0:d}\n".format(dwErr))
    exit(1)

sys.stdout.write("\nsequence replay runs, switch to next sequence (3 times possible) with")
if USING_EXTERNAL_TRIGGER == False:
    sys.stdout.write("\n key: c ... change sequence")
else:
    sys.stdout.write("\n a (slow) TTL signal on external trigger input connector")
sys.stdout.write("\n key: ESC ... stop replay and end program\n\n")

lCardStatus = int32(0)
dwSequenceActual = uint32(0)  # first step in a sequence
dwSequenceNext = uint32(0)
lSeqStatusOld = int32(0)

fenetre = Tk()
fenetre.title("AOD Driver")

# Number_Channel
Ch0 = Label(fenetre, text="Ch_H N° Freq")
Ch0.grid(row=1, column=0, sticky=W)
Number_freq_Ch0 = IntVar()
Number_freq_Ch0.set(2)
N_freq0 = Entry(fenetre, text=Number_freq_Ch0, width=20)
N_freq0.grid(row=1, column=1)

Ch1 = Label(fenetre, text="Ch_V N° Freq")
Ch1.grid(row=2, column=0, sticky=W)
Number_freq_Ch1 = IntVar()
Number_freq_Ch1.set(2)
N_freq1 = Entry(fenetre, text=Number_freq_Ch1, width=20)
N_freq1.grid(row=2, column=1)

Label(fenetre, text="Segment used").grid(row=2, column=9, sticky=W)
Segment = IntVar()
Segment.set(0)
Seg = Entry(fenetre, text=Segment, width=20).grid(row=3, column=9, sticky=W)

Button(fenetre, text="Take Data", command=take_data).grid(row=6, column=9)
Button(fenetre, text="Create Interface", command=Create_interface).grid(row=9, column=1)
Button(fenetre, text="Send Data", command=data).grid(row=5, column=9)
Button(fenetre, text="Quit ", command=close).grid(row=11, column=9)
Button(fenetre, text="Move Frequencies", command=Move_Freq).grid(row=7, column=9)
Button(fenetre, text="Move Amplitude", command=Move_Amp).grid(row=8, column=9)
Button(fenetre, text="Move Phase", command=Move_Phase).grid(row=9, column=9)
Button(fenetre, text="Move Amplitude and Phase", command=Move_AP).grid(row=10, column=9)

fenetre.mainloop()
