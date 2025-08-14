import datetime
import os
from picoscope import ps5000a
from picoscope import picobase as ps
import time
from requests.exceptions import Timeout
import json
import re

client = None
port = None


def streamingReady(handle, nSamples, startIndex, overflow, triggerAt,
                   triggered, autoStop, parameter):
    global CHANNELS
    global save_file
    endInd = startIndex + nSamples
    if len(CHANNELS) == 1:
        save_data = (data[startIndex:endInd])
    else:
        save_data = (data[:, startIndex:endInd]).T
    save_data.tofile(save_file)


if __name__ == "__main__":
    # MEL TOUCH 

    # CONSTANTS 

    with open('get_info.dat') as f:
        contents = f.read()

    
        # This pattern allows for either one frequency or two frequencies separated by "/"
        channel_pattern = r"(CH\d+):\s+Freq = ([\d.]+)(?:\s*/\s*([\d.]+))?\s+Phase = ([\d.]+)\s+Amp = ([\d.]+)(?:\s*/\s*([\d.]+))?(?:\s+Polarization = ([\d.]+ deg))?"

        # Define regex pattern for metadata fields
        metadata_pattern = r"(SampleInterval|Resolution|Pressure TC|Channels|Channel \d+:|Channel \d+ VRange):\s*([\w\.\-]+)"

        # Extract channel data
        channel_matches = re.findall(channel_pattern, contents)

        # Extract metadata
        metadata_matches = re.findall(metadata_pattern, contents)

        # Parse the channel data into a dictionary
        channel_data = {}
        for match in channel_matches:
            channel, freq1, freq2, phase, amp1, amp2, polarization = match
            channel_data[channel] = {
                "Freq": (float(freq1), float(freq2)) if freq2 else (float(freq1),),
                "Phase": float(phase),
                "Amp": (float(amp1), float(amp2)) if amp2 else (float(amp1),),
                "Polarization": polarization.strip() if polarization else None
            }

        # Parse metadata into a dictionary
        metadata = {}
        for key, value in metadata_matches:
            metadata[key] = value

        # Output the results
        #print("Channel Data:")
        #for channel, data in channel_data.items():
        #    print(f"{channel}:")
        #    for key, value in data.items():
        #        print(f"    {key}: {value}")

        #print("\nMetadata:")
        #for key, value in metadata.items():
        #    print(f"{key}: {value}")
    if freq2:
        jumprot = 1
    else:
        jumprot = 0

    f = open('savedata.json')
 
    # returns JSON object as 
    # a dictionary
    svdata = json.load(f)  
    # Closing file
    f.close()

    Channel = "CH00"        #Channel info saved in filetitle!!!!!!!!

    print(Channel)
    POLARIZATION = "V"
    ####MURAD CHANGE
    #PRESSURE_GAUGE = 0.1
    FREQUENCY = str(round(channel_data.get(Channel, {}).get("Freq", (None, None))[0],3))
    AMPLITUDE = channel_data.get(Channel, {}).get("Amp", (None, None))[0]
    if jumprot:
        DETUNING = str(abs(round((float(channel_data.get(Channel, {}).get("Freq", (None, None))[1])-float(FREQUENCY))*1e3,1)))
    else:
        DETUNING = str(0)
    PHASE = channel_data.get(Channel, {}).get("Phase", (None, None))

    print(DETUNING)
    ####MURAD CHANGE (file name)
    #DESCRIPTOR = "interaction"
    DESCRIPTOR = POLARIZATION #PRESSURE_GAUGE #"3mbar"
    ####MURAD CHANGE(folder name)
    TRIAL_NAME ='standing_wave_AOD_calib_50kstep_1'#'det-scan-pos4-V-5'#'pos2-60-lp'#'det-scan-pos1-cons-int'#
    NAME = "{}_Freq_{}MHz".format(Channel, FREQUENCY)
    #NAME = "Freq_{}_AODvolt_{}mV".format(FREQUENCY,AMPLITUDE)#"{}_P={:.3g}mbar_{}MHz_{}deg_{}mV".format(DESCRIPTOR,
                                       #@PRESSURE, FREQUENCY, PHASE, AMPLITUDE)

    TRACE_DURATION = 1#2#  # seconds
    SAMPLING_INTERVAL = 200e-9#200e-9  # s 
    RES = '14'
    #!!!!!!!!!!!!!!!!!!!!!!!!!!!
    CHANNELS = ["B","C","D"]#,"C","D"]#["A",'B']
    CHANNEL_LABELS =['DC_particle','PDH', 'fwd_det']#['het1-1.1', 'het2-1.1']#,, "power-stability"]
    CHANNEL_VRANGE = [20,20,20]
    ####MURAD CHANGE
    DIRECTORY = r'C:\Users\iurii\Documents\Data'

    # MEL NO TOUCH

    # Preparing data path
    date_time = datetime.datetime.now()
    date = date_time.strftime("%Y%m%d")
    timestamp = date_time.strftime("%Y%m%d_%H%M%S")

    data_directory = os.path.join(DIRECTORY, " - ".join((date, TRIAL_NAME)))

    if not os.path.isdir(data_directory):
        os.mkdir(data_directory)

    data_directory = os.path.join(data_directory, "Traces")

    if not os.path.isdir(data_directory):
        os.mkdir(data_directory)

    save_file_name = "_".join((timestamp,NAME))+".bin"

    # Initialization
    save_file = None
    ps = ps5000a.PS5000a()
    ps.setChannel(channel="A", enabled=False)
    ps.setChannel(channel="B", enabled=False)
    ps.setChannel(channel="C", enabled=False)
    ps.setChannel(channel="D", enabled=False)

    for i, channel in enumerate(CHANNELS):
        ps.setChannel(channel=channel, coupling='DC', VRange=CHANNEL_VRANGE[i], VOffset=0.0, enabled=True, BWLimited=False, probeAttenuation=1.0)

    ps.setNoOfCaptures(noCaptures=1)
    ps.memorySegments(noSegments=1)
    ps.setResolution(RES)
    si = ps.setSamplingInterval(SAMPLING_INTERVAL, 1)
    print("SI: {:.3g}".format(si[0]))

    data = ps.allocateDataBuffers(channels=CHANNELS, numSamples=0,
                                  downSampleMode=0)
    data = data.squeeze()


    # Writing header
    header_file_name = save_file_name.replace(".bin", "_header.dat")
    json_file_name = save_file_name.replace(".bin", "_header.json")

    
    with open(os.path.join(data_directory, header_file_name), 'w') as file:
        file.write(contents + '\n \n')
        file.write("SampleInterval:\t{:5g}\n".format(si[0]))
        file.write("Resolution:\t{}\n".format(RES))
        #file.write("Pressure Gauge:\t{}\n".format(PRESSURE_GAUGE))
        file.write("Channels:\t{}\n".format("".join(CHANNELS)))
        for i in range(len(CHANNELS)):
            file.write("Channel {}:\t{}\n".format(i+1, CHANNEL_LABELS[i]))
        for i in range(len(CHANNELS)):
            file.write("Channel {} VRange:\t{:d}\n".format(i+1, CHANNEL_VRANGE[i]))

    svdata["SampleInterval"] = si[0]
    svdata["Resolution"] = RES
    svdata["Channels"] = "".join(CHANNELS)
    for i in range(len(CHANNELS)):
        svdata["Channel" + str(i)] = CHANNEL_LABELS[i]
    for i in range(len(CHANNELS)):
        svdata["Channel" + str(i) + " VRange"] = CHANNEL_VRANGE[i]
    svdata["Detuning"] = DETUNING
    jdata = open(os.path.join(data_directory, json_file_name), "w")
    json.dump(svdata, jdata, indent = 6)  
    jdata.close()

    # Stream data
    with open(os.path.join(data_directory, save_file_name), 'wb') as save_file:
        ps.runStreaming(bAutoStop=False, downSampleMode=0, downSampleRatio=1)
        t = 0
        t0 = datetime.datetime.now()
        while t <= TRACE_DURATION:
            ps.getStreamingLatestValues(callback=streamingReady)
            t = (datetime.datetime.now() - t0).total_seconds()
        ps.stop()
        ps.close()
        
    print(save_file_name)
