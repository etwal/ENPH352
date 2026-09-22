#!/usr/bin/env python3

import numpy as np
import sys
import pyvisa as visa
from matplotlib import pyplot as plt
import time
import click

# This is the channel we'll fetch the trace from.

# Based on examples in e.g.
# https://gist.github.com/prhuft/8d961e2983bfdf8fdf1effcc1aae61a9
# https://gist.github.com/pklaus/7e4cbac1009b668eafab
# https://www.codeproject.com/Articles/869421/Interfacing-Rigol-Oscilloscopes-with-C 

# Programming guide for this oscilloscope:
# https://beyondmeasure.rigoltech.com/acton/attachment/1579/f-af444326-0551-4fd5-a277-bf8fff6f53cb/1/-/-/-/-/DS1000Z-E_ProgrammingGuide_EN.pdf

# TODO: check against an actually running scope that the various ranges
# here are correctly interpreted. These are based on best guesses
# from the manual but there are definitely contradictory things online.

####################################################################
# get_data method for reading out values from memory. Do not change. 
#
# Authors: M Halpern, A Jaffray, J Wong 2023
#   - Jan 20 2023 AJ - Correct placement of ACQ:MDEP write 
#                      MUST BE BETWEEN :RUN and :STOP
####################################################################
def get_data(scope,mdepth) :

    channel = int(scope.query(":WAV:SOUR?")[4])

    #print("About to fetch data...")
    fulldata = []
    points_list = list(range(489, mdepth, 489))
    points_list.append(mdepth)
    for thisindex, endpoint in enumerate(points_list) :
        if thisindex != 0 :
            startpoint = points_list[thisindex-1]+1
        else :
            startpoint = 1
        scope.write(":WAV:STAR {0}".format(startpoint))
        scope.write(":WAV:STOP {0}".format(endpoint)) # 489 is the maximum distance between start and end
        # Switched to "I" and new scaling following Mark's lead
        print("getting start and stop",startpoint,endpoint,"...")
        try :
          rawdata = scope.query_binary_values(':WAV:DATA?', datatype = 'I', container = np.array)
        except :
          # fill it with zeros
          print("Data collection failed for points",startpoint,endpoint)
          rawdata = np.zeros(489)
        fulldata = np.append(fulldata,rawdata)

        # NOTE: 
        # After retrieving data, you will get a crash if you
        # attempt to check :WAV:STOP. It is fine before, but
        # broken after. You can still set it but you can't read it.

    # Need to convert to real voltage values.
    # Using the scale info has proven confusing, so we'll actually just take the maximum
    # and minimum in the channel.
    scope.write(":MEAS:SOUR CHAN{0}".format(channel))
    vmin = float(scope.query(":MEAS:VMIN?"))
    vmax = float(scope.query(":MEAS:VMAX?"))
    rawmin = np.amin(fulldata)
    rawmax = np.amax(fulldata)
    slope = (vmax - vmin)/(rawmax - rawmin)
    intercept = vmin - slope*rawmin
    vals = fulldata*slope + intercept

    return vals

####################################################################
# Trace Capture Code: Feel free to edit, just be careful with your 
#                     choices as they directly influence your 
#                     measurements
#
####################################################################

@click.command()
@click.option('-t','--trig',type=click.IntRange(min=1),default=1,help='Channel to trigger on (can be 1 or 2)')
@click.option('-d','--depth',type=click.IntRange(min=6000), default=6000, help='memory depth: number of discretizations across the screen, more means higher time resolution, less means faster reading')
@click.option('-o','--outfilestem', default="output",
              help='output file name stem (default "output"). This will result in '+
                   'a voltage file output-voltage.dat and time-axis file output-time.dat')
@click.option('-v','--verbose',type=click.BOOL,help='toggle verbose')
@click.option('-h', is_flag=True, help='same as --help')
@click.pass_context

def capturetrace(ctx, trig,depth, outfilestem, verbose,h):
    """capture <ntraces> multiple traces from the scope on <channel>"""
    if h: # allow option -h as alternate help flag
        click.echo(ctx.get_help())
        ctx.exit()
    # Make the pyvisa resource manager
    rm = visa.ResourceManager('@py')
    # Get the USB device, e.g. 'USB0::0x1AB1::0x0588::DS1ED141904883'
    instruments = rm.list_resources()
    usb = list(filter(lambda x: 'DS1Z' in x, instruments))
    if len(usb) < 1:
        print('Bad instrument list', instruments)
        sys.exit(-1)
    print("Will open instrument",usb[0]) # usually this usb[0] is the right instrument, but if you have 2 scopes you might have to choose a different one
    
    # bigger timeout for long mem
    scope = rm.open_resource(usb[0], timeout=20000, chunk_size=1024000) 

    if verbose:
        # Check initial trigger and aquisition status
        print("Acquire type:",scope.query("ACQuire:TYPE?"))
        print("Trigger status:",scope.query("trig:status?"))
    
    # SET acquire type to single trace (can also set to AVER, etc... as per manual but better to do it one by one)
    scope.write("ACQuire:TYPE NORM")
    
    if verbose:
        # Check initial trigger and aquisition status
        print("Acquire type:",scope.query("ACQuire:TYPE?"))

    # SET MEM DEPTH TO THAT CHOSEN IN CMD LINE ARGS
    # - 12000 for single channel
    # - 6000 if you have two channels enabled
    # If you're getting weird errors, go to AUTO:
    # it will be slower to run but that's life.
    mdepth = depth
    
    # SET X-AXIS SCALE 
    # ADJUST THIS TO YOUR FREQUENCY OF INTEREST
    scope.write(":TIM:SCAL 0.00002") 
    time.sleep(0.1) # sleep to make sure it's registered, maybe not necessary

    # GET THE SAMPLING RATE
    srat = float(scope.query("ACQ:SRAT?"))

    # GET THE TIMESCALE
    # This is in seconds per division.
    timescale = float(scope.query(":TIM:SCAL?"))
    used_mdepth = int(srat*timescale*12) # 12 is the number of horizontal scales in a DS1202Z-E display
    if verbose:
        # CHECK MEM DEPTH
        print("Mem depth: ",mdepth)

        # Let's check the mode of your axes. 
        # You probably want MAIN here.
        print("Time axis mode:",scope.query(":TIMebase:MODE?"))
    
    # Set your trigger and let's turn it on.
    # Your options are AUTO, NORM, and SING
    # You probably want NORM for physics
    # AUTO just makes sure something is happening so you can test this
    scope.write(":TRIG:SWEEP NORM") 
    if verbose:
        print("Set Trigger Sweep:",scope.query(":TRIG:SWEEP?"))

    # SET TRIGGER TO EDGE MODE ON CHANNEL 1 and NEGATIVE SLOPE
    scope.write(":TRIG:MODE EDGE") 
    scope.write(":TRIG:EDG:SOUR CHAN{0}".format(trig)) # trigger on specified channel
    scope.write(":TRIG:EDG:SLOP NEG") # trigge on the rising edge

    # SET TRIGGER LEVEL [V]
    scope.write(":TRIG:EDG:LEV 0.") #  volts

    if verbose:
        print("Trigger mode:",scope.query(":TRIG:MODE?"))
        print("Trigger status:",scope.query("trig:status?"))
    
    print("Starting Data Acquisition Run")
    scope.write(":RUN")
    time.sleep(.1)
    scope.write(":ACQ:MDEP {0}".format(mdepth))
    # Wait a second to make sure we trigger
    time.sleep(.5)
    # Grab the raw data from channel 1
    scope.write(":STOP")
    print("Finished Acquiring Data")

    # Get the timescale offset
    timeoffset = float(scope.query(":TIM:OFFS?"))
    # Get the y axis range (volts) of trigger channel
    # Scale is # of volts per division, and there are 8 divisions on the screen.
    voltscale = float(scope.query(':CHAN{0}:SCAL?'.format(trig)))
    # And the voltage offset
    voltoffset = float(scope.query(":CHAN{0}:OFFS?".format(trig)))
    
    # Check the sample rate
    sample_rate = scope.query(':ACQ:SRAT?')
    if verbose:
        print("Sample rate:", sample_rate)
    
    # Note: not :WAV:POIN:MODE, which is for other DS1000-series Rigol scopes
    # Byte return format is a value between 0 and 255
    scope.write(":WAV:SOUR CHAN1")
    scope.write(":WAV:FORM BYTE") # Other: ascii and raw
    scope.write(":WAV:MODE RAW") # NORM instead of RAW, which takes the whole buffer?
    
    if verbose:
        # Make sure things are what we want them to be.
        print("Check some values.")
        print("timescale:",timescale)
        print("timeoffset:",timeoffset)
        print("voltscale:",voltscale)
        print("voltoffset",voltoffset)
        print("Wave form:",scope.query(":WAV:FORM?"))
        print("Mode:",scope.query("WAV:MODE?"))
    
    # GET THE TRACE FOR BOTH CHANNELS BY CONSECUTIVELY READING THEM
    print("Collecting CHAN1 trace from memory using mdepth ",mdepth)
    chan1_data = np.array(get_data(scope,mdepth))
    time.sleep(0.5)
    print("Collecting CHAN2 trace from memory using mdepth ",mdepth)
    scope.write(":WAV:SOUR CHAN{0}".format(2))
    time.sleep(0.1)
    chan2_data = np.array(get_data(scope,mdepth))
    tracedata = np.stack([chan1_data,chan2_data],axis=0)

    # Now we need to do some parsing to understand it, using the 
    # scale info we collected before.
    
    # We know the time increment between all our measurements and the offset of the first value,
    # so we can make a time axis for our data.
    # CALCULATE TIME ARRAY CORRESPONDENT TO MEASUREMENT
    time_axis = np.linspace(timeoffset - 6 * timescale, timeoffset + 6 * timescale, num=np.size(tracedata,1))

    #save all of our voltages that were stored in myArray
    np.savetxt(outfilestem+'-Voltages.dat', tracedata, delimiter=",")
    print('saved to {0}-Voltages.dat'.format(outfilestem))
    #save the time axis array as well. We'll need this
    np.savetxt(outfilestem+'-Times.dat', time_axis, delimiter=",")
    print('saved to {0}-Times.dat'.format(outfilestem))
    
    #############################
    
    # Release scope for next call
    rm.close()
    scope.close()

if __name__ == "__main__":
    capturetrace()
