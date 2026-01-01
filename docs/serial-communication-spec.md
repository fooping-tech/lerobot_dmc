# Serial Communication Specification

## Overview
This controller streams left/right wheel commands to the host over USB serial.
Each control frame is a single ASCII line and is safe to parse line-by-line.
On boot, the device starts in calibration mode and does not emit control frames
until calibration completes.

## Transport
- Interface: USB CDC serial (M5AtomS3 USBSerial)
- Framing: newline-delimited ASCII lines (`\n`)
- Baud rate: not configured in firmware (USB CDC); select any baud in the host tool
  if required by the serial monitor.

## Message Format
```
L:<left>,R:<right>\n
```

### Fields
- `left`: signed integer command for the left wheel
- `right`: signed integer command for the right wheel

### Value Semantics
- Range: `-1000` to `1000` (normal)
- Positive: forward
- Negative: backward
- Dead zone: values in `-40` to `40` are sent as `0`
- L button held: left output is doubled and clamped to `-2000` to `2000`
- R button held: right output is doubled and clamped to `-2000` to `2000`

### Calibration
- At startup, the user is prompted to rotate both sticks through their full range.
- The observed min/max values are used to map raw input to `-1000` to `1000`.
- After full range is detected, the device waits 0.5 seconds before entering
  control mode.
- Pressing the device button returns to calibration mode at any time.

## Update Rate
The main loop is paced by a 10 ms timer tick, so the command stream is
approximately 100 Hz when the device is running normally.

## Examples
```
L:0,R:0
L:250,R:240
L:-300,R:-310
```

## Notes
- The firmware may print other human-readable status lines during startup; a
  robust parser should ignore any line that does not start with `L:`.
- The controller displays the current mode and latest `L`/`R` values on the
  device screen for quick verification.
