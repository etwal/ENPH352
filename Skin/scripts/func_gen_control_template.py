# Connect Agilent/HP33120A Function Generator to Pi via USB->RS232 converter
# Note that a null modem cable will be required for 33120A RX/TX swap (as we are doing here)
#
# For arbitrary waveforms, the maximum amplitude will be limited if
# the data points do not span the full range of the output DAC (Digitalto-Analog Converter)

# Imports
import pyvisa as visa
from pyvisa import constants

### INIT ####

arbWave = False

# Connect to function gen
print("Initialising 33120A...")
rm = visa.ResourceManager('@py')
rm.list_resources()
inst = rm.open_resource('ASRL/dev/ttyUSB0::INSTR')

# IMPORTANT, don't touch
print("setting DSR DTR flow control")
inst.set_visa_attribute(constants.VI_ATTR_ASRL_FLOW_CNTRL, constants.VI_ASRL_FLOW_DTR_DSR)

# Set remote
print("Setting remote access")
inst.write("SYSTEM:REMOTE")

status = 1
while(status == 1):
    print("Clearing Errors")
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

# NOTES: AS YOU'VE PROBABLY DISCERNED, THE QUERY COMMAND ASKS THE MACHINE ABOUT IT'S CURRENT CONFIGURATION, AND THE WRITE COMMAND ALLOWS YOU TO TELL THE MACHINE EITHER INSTRUCTIONS OR TO SET THE VALUE OF CERTAIN PARAMETERS PERTINENT TO THE EXPERIMENT AT HAND

#1 Select the waveform frequency, amplitude, and offset. (p138)
# APPLy:USER [<frequency> [,<amplitude> [,<offset>] ]]
#          Example, for 2kHz 1V sine wave w/ 500mV offset:
#                                APPL:SIN 2.0E+3, 1.0, 0.5

### DATA TRANSFER ### (EXAMPLE of playing a sin pulse at 100kHz)
print("Setting USER [<frequency> [,<amplitude> [,<offset>]]")
inst.write("APPLy:SIN 1E+4, 4.0, 0.0")

if arbWave:

    # Example about how to download the data points into volatile memory
    #   Two ways of doing this:
    #       i) floating-point: DATA VOLATILE, <value>, <value>, . . .
    #                           Download floating-point values between -1 and +1 into volatile memory.
    #                           You can download between 8 and 16,000 points per waveform
    #       ii) binary: DATA:DAC VOLATILE, {<binary block>|<value>, <value>, . . . }
    #                   Download binary integer values between -2047 and +2047 into volatile
    #                   memory. You can download between 8 and 16,000 points per waveform
    #                   in IEEE-488.2 binary block format or as a list of values. The binary range
    #                   of values corresponds to the values available using internal 12-bit DAC
    #(                  Digital-to-Analog Converter) codes. 
    # If you export from Intuilinks as CSV, join lines in notepad++ with:
    #   Highlight the lines you want to join (or use Ctrl + A to select everything)
    #           Choose Edit > Line Operations > Join Lines from the menu or press
    #           inst.write("DATA VOLATILE, 1,.75,.5,.25,0,-.25,-.5,-.75,-1")

    print("Writing user data to volatile memory...")
    inst.write("DATA VOLATILE, 1,.75,.5,.25,0,-.25,-.5,-.75,-1")
    print("                                       done.")
    print("    system err?")
    print(inst.query("SYST:ERR?"))

    #3 Optional: Copy the arbitrary waveform to non-volatile memory.
    # TODO

    ### DATA OUTPUT ###
    #4 Select the arbitrary waveform to output.
    # FUNCtion:USER {<arb name>|VOLATILE}

    print("Selecting volatile memory as the location of the waveform to output")
    inst.write("FUNCtion:USER VOLATILE")

    #5 Output the currently selected arbitrary waveform.
    print("Output waveform...")
    inst.write("FUNCtion:SHAPe USER") 

    print("End.")





