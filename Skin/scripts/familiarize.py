#!/usr/bin/env python3
'''
Familiarization exercise: drive a sine wave from the 33120A function generator
and measure its amplitude, frequency and phase on the Rigol DS1202Z-E.

This is the remote-control counterpart to doing the same thing by hand on the
front panels. Run it, then reproduce the numbers manually to confirm they agree.

Wiring assumed:
    Function generator output -> scope CHAN1 (the reference)
                              -> the rest of your circuit -> scope CHAN2

CHAN1 is the phase reference, so the reported phase is CHAN2 relative to CHAN1.
With CHAN1 and CHAN2 teed off the same point the phase should read ~0 degrees,
which is a good sanity check before you put anything in between.

Instruments:
    Scope           rigol1 at 142.103.238.1, over LAN
    Function gen    33120A over the USB-to-RS232 converter, found automatically

Programming guide for the scope:
https://beyondmeasure.rigoltech.com/acton/attachment/1579/f-af444326-0551-4fd5-a277-bf8fff6f53cb/1/-/-/-/-/DS1000Z-E_ProgrammingGuide_EN.pdf
'''

import sys
import time
import argparse
import pyvisa as visa
from pyvisa import constants

# The Rigol returns this sentinel from a :MEAS: query when it cannot make the
# measurement, for example when the trace is off screen or there is no signal.
RIGOL_INVALID = 9.9e37


def find_fgen_id(rm):
    # The 33120A is on serial via the USB-to-RS232 converter, so it appears as
    # an ASRL resource. Match on that rather than a list index.
    instruments = rm.list_resources()
    asrl = [x for x in instruments if x.startswith('ASRL')]
    if len(asrl) < 1:
        print('No serial function generator found in', instruments)
        print('Check the USB-to-RS232 converter is plugged in and the 33120A is on.')
        sys.exit(-1)
    return asrl[0]


def setup_fgen(rm, fgen_id):
    print("Opening function generator at {0}".format(fgen_id))
    inst = rm.open_resource(fgen_id)

    # Set the timeout before any query, not after. The serial link is slow and
    # the default 2 s is not always enough for the first exchange.
    inst.timeout = 20000

    # IMPORTANT, don't touch. The 33120A needs hardware flow control.
    inst.set_visa_attribute(constants.VI_ATTR_ASRL_FLOW_CNTRL,
                            constants.VI_ASRL_FLOW_DTR_DSR)

    # Clear any half-finished exchange left by a previous run, then take remote
    # control. Without this a stale reply sitting in the buffer desynchronises
    # every query that follows.
    try:
        inst.clear()
    except Exception:
        pass
    inst.write("*CLS")
    inst.write("SYSTEM:REMOTE")
    time.sleep(0.5)

    # Drain queued errors, but give up rather than hanging or crashing. A
    # timeout here usually means the generator needs a power cycle, or that
    # someone pressed a front panel key and knocked it out of remote mode.
    for attempt in range(20):
        try:
            response = inst.query("SYST:ERR?").strip()
        except Exception:
            print("  warning: no reply to SYST:ERR? on attempt {0}".format(attempt + 1))
            time.sleep(0.5)
            continue
        if response.startswith("+0") or response.startswith("0"):
            break
        print("  clearing queued error: {0}".format(response))
    else:
        print("  warning: could not clear the error queue, continuing anyway")

    print("  IDN: {0}".format(inst.query("*IDN?").strip()))
    return inst


def setup_scope(rm, scope_id):
    print("Opening scope at {0}".format(scope_id))
    scope = rm.open_resource(scope_id, timeout=20000, chunk_size=1024000)
    print("  IDN: {0}".format(scope.query("*IDN?").strip()))

    scope.write(":ACQuire:TYPE NORM")

    # Turn both channels on. A channel whose display is off returns the
    # invalid sentinel from every :MEAS: query no matter what is plugged in.
    scope.write(":CHAN1:DISP ON")
    scope.write(":CHAN2:DISP ON")
    time.sleep(0.3)

    # Report the probe attenuation and coupling rather than forcing them. A
    # 10x setting with a plain BNC cable makes every reading ten times too
    # large, and that is easy to miss.
    for ch in (1, 2):
        print("  CHAN{0}: probe {1}x, coupling {2}".format(
            ch,
            scope.query(":CHAN{0}:PROB?".format(ch)).strip(),
            scope.query(":CHAN{0}:COUP?".format(ch)).strip()))

    # Edge trigger on CHAN1, which is the clean reference signal
    scope.write(":TRIG:SWEEP NORM")
    scope.write(":TRIG:MODE EDGE")
    scope.write(":TRIG:EDG:SOUR CHAN1")
    scope.write(":TRIG:EDG:SLOP NEG")
    scope.write(":TRIG:EDG:LEV 0.")

    # Phase is measured as CHAN2 relative to CHAN1
    scope.write(":MEAS:SETup:PSA CHAN1")
    scope.write(":MEAS:SETup:PSB CHAN2")

    return scope


def configure_display(scope, f, vpp, ch2_scale):
    # Fit roughly 6 cycles across the 12 horizontal divisions
    time_per_div = (1.0 / f) * 6 / 12
    scope.write(":TIM:SCAL {:.1E}".format(time_per_div))

    # Deliberately generous vertical scales. Clipping cannot be undone, an
    # undersized trace can simply be rescaled afterwards.
    scope.write(":CHAN1:SCAL {:.1E}".format(vpp / 2))
    scope.write(":CHAN2:SCAL {:.1E}".format(ch2_scale))
    time.sleep(0.2)


def autorange_channel(scope, channel, start_scale):
    """Step the vertical scale down until the trace is measurable.

    A pickup coil signal can be a few mV against a default of 100 mV/div,
    which puts it well under a single division and unmeasurable.
    """
    scale = start_scale
    for _ in range(8):
        scope.write(":CHAN{0}:SCAL {1:.1E}".format(channel, scale))
        time.sleep(0.4)
        vpp = float(scope.query(":MEAS:VPP?"))
        if valid(vpp) and vpp > scale:
            # Aim to fill roughly 4 of the 8 vertical divisions
            final = max(vpp / 4.0, 1e-3)
            scope.write(":CHAN{0}:SCAL {1:.1E}".format(channel, final))
            time.sleep(0.4)
            return final
        scale = scale / 5.0
        if scale < 1e-3:
            break
    print("  CHAN{0}: could not find a working scale, signal may be absent"
          .format(channel))
    return scale


def measure_channel(scope, channel):
    scope.write(":MEAS:SOUR CHAN{0}".format(channel))
    time.sleep(0.2)
    return {
        "vpp": float(scope.query(":MEAS:VPP?")),
        "vrms": float(scope.query(":MEAS:VRMS?")),
        "vmax": float(scope.query(":MEAS:VMAX?")),
        "vmin": float(scope.query(":MEAS:VMIN?")),
        "freq": float(scope.query(":MEAS:FREQ?")),
    }


def valid(x):
    return abs(x) < RIGOL_INVALID / 10


def show(label, m):
    print("\n{0}".format(label))
    if not valid(m["vpp"]):
        print("  no valid measurement (scope returned its invalid sentinel)")
        print("  check the probe is connected and the trace is on screen")
        return
    print("  amplitude  Vpp  = {:.4f} V".format(m["vpp"]))
    print("             Vrms = {:.4f} V".format(m["vrms"]))
    print("             Vmax = {:.4f} V   Vmin = {:.4f} V".format(m["vmax"], m["vmin"]))
    if valid(m["freq"]):
        print("  frequency       = {:.4f} Hz".format(m["freq"]))
    else:
        print("  frequency       = no valid measurement")


parser = argparse.ArgumentParser(
    description='Generate a sine wave and measure its amplitude, frequency '
                'and phase on the oscilloscope')
parser.add_argument('-f', '--frequency', type=float, default=1e4,
                    help='Drive frequency in Hz (default 10 kHz)')
parser.add_argument('-a', '--amplitude', type=float, default=2.0,
                    help='Function generator amplitude in Vpp (default 2.0)')
parser.add_argument('-s', '--ch2_scale', type=float, default=100e-3,
                    help='Initial CHAN2 vertical scale in V/div')
# This bench uses rigol1 (142.103.238.1). rigol2-4 belong to other benches;
# do not point this at them.
parser.add_argument('--scope', type=str, default='TCPIP0::142.103.238.1::INSTR',
                    help='VISA address of the oscilloscope. Defaults to rigol1, '
                         'which is this bench')
args = parser.parse_args()

rm = visa.ResourceManager('@py')
scope = setup_scope(rm, args.scope)
fgen = setup_fgen(rm, find_fgen_id(rm))

print("\nDriving a sine wave: {:.4g} Hz, {:.2f} Vpp, 0 V offset"
      .format(args.frequency, args.amplitude))
fgen.write("APPLy:SIN {:.4E}, {:.4f}, 0.0".format(args.frequency, args.amplitude))
time.sleep(0.5)

configure_display(scope, args.frequency, args.amplitude, args.ch2_scale)

scope.write(":RUN")
time.sleep(1.0)
scope.write(":STOP")

ch1 = measure_channel(scope, 1)

# CHAN2 carries the small pickup signal, so hunt for a usable scale
scope.write(":MEAS:SOUR CHAN2")
time.sleep(0.2)
if not valid(float(scope.query(":MEAS:VPP?"))):
    print("\nCHAN2 unmeasurable at {0:.3g} V/div, auto-ranging..."
          .format(args.ch2_scale))
    found = autorange_channel(scope, 2, args.ch2_scale)
    print("  settled on {0:.3g} V/div".format(found))

ch2 = measure_channel(scope, 2)

phase = float(scope.query(":MEAS:RPH?"))

print("\n" + "=" * 52)
print("MEASURED  (drive set to {:.4g} Hz)".format(args.frequency))
print("=" * 52)
show("CHAN1 (reference, straight from the generator)", ch1)
show("CHAN2 (through the circuit)", ch2)

print("\nphase CHAN2 relative to CHAN1")
if valid(phase):
    print("  phi             = {:.3f} degrees".format(phase))
else:
    print("  no valid measurement, which usually means CHAN2 has no signal")

if valid(ch1["freq"]):
    err = ch1["freq"] - args.frequency
    print("\nfrequency check: scope reads {:+.4f} Hz off the commanded value "
          "({:+.3f} %)".format(err, 100 * err / args.frequency))

print("\nNow reproduce these numbers using the front panel controls.")

scope.close()
fgen.close()
rm.close()
