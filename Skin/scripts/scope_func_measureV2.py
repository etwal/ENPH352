#!/usr/bin/env python3

'''

2024-02-05 Modified by Josh Kraan (V2):
- Added sleep to function generator clearing loop
- Changed scope ID to representative string (change this to match your scope)
- Switched to autoscaling for vertical scales (removed setup_scope).

This script performs a sweep across all frequencies and automates data 
collection of waveform properties using the "measure" features of the 
oscilloscope.

For each frequency: The script performs the following tasks:
1.  Re-initialize oscilloscope and function generator to run a waveform of the 
    specified frequency (this made data collection more reliable and caused the 
    hardware to hang less for some reason)

2.  Set the timescale on the oscilloscope to show roughly 6 cycles of the wave

3.  Set the vertical scale of channel 1 to half the specified Vpp. This is too 
    large of a scale size but will be corrected for later. This may seem 
    counterproductive (why not just set the scale a bit smaller to start with) 
    but is necessary because the function generator amplitude was not 
    consistent and increased with frequency for the same Vpp setting. Setting a 
    smaller scale size resulted in clipping which could not be corrected for. I 
    found it better to specify the scale slightly to large and correct for it 
    instead, even if it means iterating over the same frequency more times.

4.  Use the inputted "--init_scale" argument to set the channel 2 vertical 
    scale initially. Again, this will be corrected for. As with channel 1, I 
    found it easier to set a scale too large and let the script correct for it 
    rather than risk intense clipping. 

5.  Collect oscilloscope data using the "MEASURE" function

6.  Dynamically adjust the vertical scale of both channels. This part:
        a.  Checks the maximum value measured by the oscilloscope
        b.  Compares it with the current scale (volts/div)
        c.  adjusts the scale so that the maximum voltage is roughly between 
            the 3rd and 4th vertical division
        d.  Re-runs part 5. and iterates until the condition in part c is 
            satisfied 

7.  Stores the oscilloscope measurement data in a dictionary

8.  Nests the data dictionary in a high-level dictionary, with the key being 
    the frequency

    The generated structure is:
    {
        f1:
            "CHAN1":    chan1 data dict
            "CHAN2":    chan2 data dict
        f2:
            "CHAN1":    chan1 data dict
            "CHAN2":    chan2 data dict
        .
        .
        .
    }

The final high-level dictionary is saved as a json file for later analysis in 
json_data/{MATERIAL TYPE}_{timestamp}.json

The script draws heavily from the provided 
func_gen_scope_together.py (M Halpern, A Jaffray, J Wong, 2023)

That script itself is based on examples in e.g.
 - https://gist.github.com/prhuft/8d961e2983bfdf8fdf1effcc1aae61a9
 - https://gist.github.com/pklaus/7e4cbac1009b668eafab
 - https://www.codeproject.com/Articles/869421/Interfacing-Rigol-Oscilloscopes-with-C

Programming guide for the oscilloscope:
https://beyondmeasure.rigoltech.com/acton/attachment/1579/f-af444326-0551-4fd5-a277-bf8fff6f53cb/1/-/-/-/-/DS1000Z-E_ProgrammingGuide_EN.pdf
'''

import numpy as np
import os
import sys
import pyvisa as visa
import time
import argparse
from datetime import datetime
import time
import json

def setup_fgen(rm,fgen_id):
    inst = rm.open_resource(fgen_id)

    # IMPORTANT, don't touch
    print("setting DSR DTR flow control")
    inst.set_visa_attribute(visa.constants.VI_ATTR_ASRL_FLOW_CNTRL, visa.constants.VI_ASRL_FLOW_DTR_DSR)

    # Set remote
    print("Setting remote access")
    inst.write("SYSTEM:REMOTE")

    status = 1
    while(status == 1):
        print("Clearing Errors")
        time.sleep(1)
        if int(inst.query("SYST:ERR?")[1]) ==0:
            status = 0

    # set timeout for query (currently 3min20s)
    print("setting timeout") # Transer time might be >2mins for a lot of data!
    inst.timeout = 200000 # [ms]

    # ask the machine what it is
    print("Finding IDN...")
    print(inst.query("*IDN?"))

    print("Testing")
    print(inst.query("*TST?"))

    return inst

def acquire_from_scope(scope, f, average):
    trig = int(scope.query(":TRIG:EDG:SOUR?")[4])
    print(trig)
    print("Starting Data Acquisition Run")
    
    # run the scope
    scope.write(":RUN")
    time.sleep(.5)

    # Set scope to average acquisition data for more accurate measurements
    scope.write(":ACQ:TYPE AVER")
    scope.write(":ACQ:AVER {0}".format(average))

    # Wait enough time to ensure all wavepoints are averaged
    sleeptime = average/f + 0.5 # extra 0.5 seconds in case this is really small
    time.sleep(sleeptime)

    # stop the scope to collect the current trace data
    scope.write(":STOP")
    print("Finished Acquiring Data")

    # Note: not :WAV:POIN:MODE, which is for other DS1000-series Rigol scopes
    # Byte return format is a value between 0 and 255
    scope.write(":WAV:SOUR CHAN1")
    scope.write(":WAV:FORM BYTE") # Other: ascii and raw
    scope.write(":WAV:MODE RAW") # just trust, it works

    # get measurements for both channels by reading them consecutively
    print("Querying data averaged over %s cycles "%average)
    scope.write(":WAV:SOUR CHAN{0}".format(1))
    chan1_data = get_data(scope)
    time.sleep(0.2)
    
    scope.write(":WAV:SOUR CHAN{0}".format(2))
    time.sleep(0.5)
    chan2_data = get_data(scope)

    # store data for each channel in dict together
    waveform_info = {
        "CHAN1": chan1_data,
        "CHAN2": chan2_data
    }

    return waveform_info

def get_data(scope):
    channel = int(scope.query(":WAV:SOUR?")[4])
    scope.write(":MEAS:SOUR CHAN{0}".format(channel))

    # query scope measurements
    vmin = float(scope.query(":MEAS:VMIN?"))
    vmax = float(scope.query(":MEAS:VMAX?"))
    vpp = float(scope.query(":MEAS:VPP?"))
    vrms = float(scope.query(":MEAS:VRMS?"))
    phase_diff = float(scope.query(":MEAS:RPH?"))

    return {
        "vmin": vmin,
        "vmax": vmax,
        "vpp": vpp,
        "vrms": vrms,
        "phi": phase_diff,
    }

def run_data_collection(f, average, vpp):
    # initialize resources
    rm = visa.ResourceManager('@py')
    inst_list = rm.list_resources()

    fgen_id = inst_list[0]
    scope_id = 'TCPIP0::rigol3.phas.ubc.ca::INSTR' # TODO update this to match your scope

    scope = rm.open_resource(scope_id, timeout=20000, chunk_size=1024000)
    fgen = setup_fgen(rm,fgen_id)

    # set the function generator to output sine wave with the correct frequency and vpp
    fgen.write("APPLy:SIN {:.0E}, {:.1f}, 0.0".format(f, vpp))

    # Let autoscale choose initial vertical scales, then later adjust to maximize resolution
    scope.write(":autoscale")

    # set scope x-scale to include roughly 6 cycles of the wave    
    period = 1/float(f)
    time_per_tick = period * 6/12 # want 6 periods to fit in window (12 divs)    
    scope.write(":TIM:SCAL {:.1E}".format(time_per_tick))

    # Trigger on channel 2 rising edge (the function generator input)
    scope.write(":TRIG:SWEEP NORM")
    scope.write(":TRIG:MODE EDGE")
    scope.write(":TRIG:EDG:SOUR CHAN2")
    scope.write(":TRIG:EDG:SLOP NEG")

    # set the trigger level [V]
    scope.write(":TRIG:EDG:LEV {}".format(vpp/4)) #  volts

    # Adjust vertical scales
    waveform_data = acquire_from_scope(scope, f, average)
    vmax1 = waveform_data["CHAN1"]["vmax"]
    vmax2 = waveform_data["CHAN2"]["vmax"]
    scope.write(":channel1:offset 0")
    scope.write(":channel2:offset 0")
    scope.write(":CHAN1:SCAL {:.1E}".format(vmax1/3.5))
    scope.write(":CHAN2:SCAL {:.1E}".format(vmax2/3.5))

    return acquire_from_scope(scope, f, average)

parser = argparse.ArgumentParser(description='Generate a waveform for each '
                                             'frequency and collect waveform '
                                             'data from the "MEASURE" function '
                                             'of the oscilloscope')
parser.add_argument('-a', '--amplitude', type=float, default=4.0,
                    help='Set the function generation output amplitude')
parser.add_argument('-m', '--material', type=str, choices=["AIR", "CU", "AL"],
                    help='The material inside the coil (air, copper, aluminum)')                                    

args = parser.parse_args()

frequency_range = [1e2, 2e2, 5e2,
                   1e3, 2e3, 5e3, 8e3,
                   1e4, 2e4, 3e4, 4e4, 5e4, 6e4, 7e4, 8e4]

data_dict = {}
for f in frequency_range:
    print("ACQUIRING DATA FOR f={:.0E}".format(f))
    waveform_dict = run_data_collection(f, 1024, args.amplitude*2)
    print(
        "Data Summary: ch1 vpp = {:.2E}, ch2 vpp = {:.2E}, ch2 phase = {:.2f}"
        .format(waveform_dict["CHAN1"]["vpp"],
                waveform_dict["CHAN2"]["vpp"],
                waveform_dict["CHAN1"]["phi"])
    )

    # add data to high-level dict organized by frequency
    data_dict[f] = waveform_dict

timestamp = datetime.now().strftime("%Y-%m-%d_%H_%M_%S")
outfile_name = "data/json_data/{}_{}.json".format(args.material, timestamp)

if not os.path.isdir("data/"):
    os.mkdir("data/")
    
if not os.path.isdir("data/json_data/"):
    os.mkdir("data/json_data/")

# output to json file
with open(outfile_name, "w") as outfile:
    json.dump(data_dict, outfile)

# Close everything now that you're done - not sure if necessary?
# scope.close()
# fgen.close()
# rm.close()
