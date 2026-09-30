# Smart Door System Operation

**Project:** Facial Recognition Smart Door Access System  
**Author:** Pradip Sapkota

This document explains how the Smart Door prototype works from the software and hardware-control point of view, based on the project source code and the supplied prototype images.

---

## 1. High-Level System

The system uses a Raspberry Pi as the main controller. It combines:

- Raspberry Pi camera
- Facial-recognition software
- START and STOP push buttons
- 16x2 character LCD
- Status LED
- Relay module
- 12 V solenoid/electromagnetic door-lock actuator
- A trained database of authorized faces

The basic control sequence is:

```text
Camera sees person
        |
        v
Face detected
        |
        v
Face encoding generated
        |
        v
Compare against enrolled users
        |
   +----+----+
   |         |
 Match     No match
   |         |
   v         v
Unlock     Stay locked
relay ON   relay OFF
   |
   v
Hold unlocked for ~4 seconds
   |
   v
Relay OFF
   |
   v
Door returns to locked state
```

---

## 2. Face Enrollment and Training

The system does not recognize a person automatically until that person has been enrolled.

### Step 1 — Capture face images

`src/capture_faces.py` uses the Raspberry Pi camera to collect training images.

Example:

```bash
python3 src/capture_faces.py --name "Pradip"
```

Images are stored under:

```text
dataset/Pradip/
```

Several photographs should be captured with small changes in:

- facial angle
- expression
- lighting
- distance from the camera

This gives the recognition system more useful examples.

### Step 2 — Generate face encodings

Run:

```bash
python3 src/train_model.py
```

The training script:

1. Reads images in the dataset.
2. Detects the face location in each image.
3. Converts each detected face into a numerical facial encoding.
4. Associates that encoding with the person's name.
5. Saves all known encodings and names into:

```text
encodings.pickle
```

The main smart-door application later loads this file.

> `dataset/` and `encodings.pickle` should not be uploaded to a public repository because they contain biometric information.

---

## 3. Raspberry Pi GPIO Assignments

The main application uses BCM GPIO numbering.

| Device / Function | BCM GPIO |
|---|---:|
| START push button | 17 |
| STOP push button | 27 |
| Status LED | 22 |
| Door-lock relay | 5 |
| LCD RS | 25 |
| LCD Enable | 24 |
| LCD D4 | 23 |
| LCD D5 | 18 |
| LCD D6 | 15 |
| LCD D7 | 14 |

The START and STOP buttons are configured with internal pull-up resistors, so pressing a button pulls its input toward ground.

---

## 4. START and STOP Buttons

The system has two physical operating states.

### Recognition OFF

At startup, facial recognition is disabled.

The LCD displays:

```text
Recognition OFF
Press START
```

The software also forces:

```text
Status LED = OFF
Lock relay = OFF
```

This means the program is not authorizing anybody to enter.

### START button

Pressing START calls the recognition-start routine.

The software:

1. Sets `recognition_enabled = True`.
2. Makes sure the relay starts from its non-unlock state.
3. Turns the status LED off until somebody is recognized.
4. Changes the LCD to:

```text
Recognition ON
Scanning...
```

The camera then begins processing faces for access control.

### STOP button

Pressing STOP immediately:

1. Disables recognition.
2. Clears the current detected-face list.
3. Cancels the unlock timer.
4. Turns the status LED off.
5. Turns the relay off.
6. Displays:

```text
Recognition OFF
Press START
```

So STOP acts as a software lock/reset control for the access system.

---

## 5. Camera and Facial Recognition

The Pi Camera is configured for:

```text
1280 x 720
```

For recognition, the program reduces each frame to one quarter of its original width and height.

This is done to reduce the amount of image data that must be processed and improve real-time performance.

The program then:

1. Converts the frame from OpenCV BGR format to RGB.
2. Locates faces.
3. Generates a face encoding for each detected face.
4. Compares each encoding with the stored authorized encodings.

The recognition result for each face becomes either:

```text
Authorized person's name
```

or:

```text
Unknown
```

The program also calculates the distance between the detected face encoding and the saved encodings and selects the closest match when the face-recognition library reports a valid match.

---

## 6. What Happens When a Face Is Recognized

The important access-control logic is:

```python
recognized_name = next(
    (name for name in face_names if name != "Unknown"),
    None,
)
```

Therefore, if at least one currently visible face is recognized as an enrolled person, the system considers access authorized.

When this occurs:

```python
lock_hold_until = time.time() + LOCK_HOLD_TIME
status_led.on()
lock_relay.on()
```

with:

```python
LOCK_HOLD_TIME = 4
```

The system therefore:

1. Turns on the status LED.
2. Commands the relay into the unlock state.
3. Displays the recognized person's name on the LCD.
4. Starts/resets a four-second unlock timer.

The LCD shows approximately:

```text
Face:
Pradip
```

---

## 7. Four-Second Unlock Hold

The four-second timer is important.

The code does **not** relock immediately when the recognized face disappears from the camera.

Every successful recognition executes:

```python
lock_hold_until = time.time() + 4
```

If recognition is temporarily lost but the current time is still before `lock_hold_until`, the program continues to command:

```python
status_led.on()
lock_relay.on()
```

and the LCD displays:

```text
Unlocked
Hold Time
```

This gives the authorized user several seconds to physically open the door.

### Example timing

```text
0.0 s   Face recognized
        Relay commanded ON
        Door unlocks

1.0 s   Person begins moving through doorway

2.0 s   Face is no longer visible
        Door remains unlocked

3.0 s   Timer still active
        Door remains unlocked

4.0+ s  Unlock timer expires
        Relay commanded OFF
        Door returns to locked state
```

If the face is recognized again while the timer is active, the timer is reset to four seconds from that latest recognition.

---

## 8. Unknown Face Behavior

If the camera sees a face but it does not match an enrolled user:

```text
Face Status:
Not Recognized
```

The program keeps:

```text
Status LED = OFF
Lock relay = OFF
```

Therefore, an unknown face does not generate an unlock command.

If no face is present, the LCD displays:

```text
Scanning...
No Face
```

---

## 9. Relay Control

The software defines the relay as:

```python
lock_relay = OutputDevice(
    LOCK_RELAY_PIN,
    active_high=False,
    initial_value=False,
)
```

The important part is:

```python
active_high=False
```

This indicates that the relay interface used by the prototype is treated as **active-low**.

### Active-low meaning

On many relay modules, the input becomes active when its control pin is pulled LOW rather than HIGH.

`gpiozero.OutputDevice` hides that electrical inversion from the rest of the application.

Therefore the application can use:

```python
lock_relay.on()
```

to mean:

```text
Activate the relay / command unlock
```

and:

```python
lock_relay.off()
```

to mean:

```text
Deactivate the relay / return to locked state
```

even though the physical GPIO voltage may be LOW when the relay is energized.

### Logical view

| Software command | Intended system function |
|---|---|
| `lock_relay.on()` | Unlock door |
| `lock_relay.off()` | Lock / normal state |

This is the safest way to describe the system because the code explicitly defines the relay as active-low.

---

## 10. How the Relay and 12 V Lock Work Electrically

The Raspberry Pi GPIO should **not directly power a 12 V solenoid lock**.

The code identifies GPIO 5 as the relay-control output and describes the controlled load as a 12 V solenoid lock.

The normal architecture for this type of setup is:

```text
                     LOW-VOLTAGE CONTROL SIDE

 Raspberry Pi
 +-------------+
 |             |
 | GPIO 5  ---------> Relay IN
 |             |
 | 5V/3.3V -----> Relay module power*
 | GND ---------> Relay module ground*
 +-------------+

                  ELECTRICALLY SWITCHED SIDE

 12 V Supply (+)
       |
       |
       +------ Relay COM
                  |
                  |  relay contact closes
                  v
               Relay NO
                  |
                  |
             Solenoid Lock
                  |
                  |
             12 V Supply (-)
```

`*` Exact relay-module supply wiring depends on the relay board that was used.

### What the relay accomplishes

The relay lets the Raspberry Pi control a higher-voltage/higher-current circuit without trying to power the lock from a GPIO pin.

The Pi produces only a control signal.

The separate 12 V supply provides the actual energy used by the door-lock actuator.

### When access is granted

Conceptually:

```text
Face recognized
      |
      v
GPIO 5 control changes
      |
      v
Relay energizes
      |
      v
Relay contact changes state
      |
      v
12 V lock circuit changes state
      |
      v
Solenoid unlocks door
```

After the four-second timer:

```text
Relay de-energizes
      |
      v
12 V lock circuit returns to normal
      |
      v
Door locks again
```

---

## 11. Normally Open vs Normally Closed Relay Contact

A common relay has three switched terminals:

```text
COM = Common
NO  = Normally Open
NC  = Normally Closed
```

Which contact should be used depends on the physical lock and whether it is intended to be fail-safe or fail-secure.

### Typical NO arrangement

A solenoid that unlocks only while powered can commonly be wired through:

```text
12 V +  -> COM
NO      -> Solenoid +
Solenoid - -> 12 V -
```

With the relay inactive, COM and NO are disconnected.

When the relay activates, COM and NO connect and power reaches the solenoid.

That would produce behavior consistent with:

```text
relay ON  -> unlock
relay OFF -> lock
```

### Important limitation

The provided Python code establishes the **software command behavior**, but it does not contain the actual COM/NO/NC wiring of the physical relay.

Therefore, whether the prototype physically used NO or NC cannot be proven from the Python source alone.

The exact final wiring should be verified from the relay module and physical prototype before documenting the terminal connection as definitive.

---

## 12. Solenoid / Electromagnetic Lock Behavior

The software is written around the assumption:

```text
Relay activated   = door unlocked
Relay deactivated = door locked
```

That implies the lock hardware and relay contacts were arranged so that the relay's active state produces the unlock condition.

The software intentionally returns the relay to the inactive state whenever:

- recognition is disabled,
- STOP is pressed,
- no authorized face has been recognized and the timer expires,
- or the application shuts down.

This creates a predictable default software state.

---

## 13. Status LED

GPIO 22 controls the status LED.

The LED is turned on when:

- an authorized face has been recognized, or
- the four-second unlock hold period is still active.

It is turned off when:

- recognition is stopped,
- no user is authorized,
- or the lock hold timer has expired.

Therefore the LED acts as a local visual indication of the software's unlock/authorization state.

---

## 14. LCD Status Messages

The 16x2 LCD provides a simple human-machine interface.

Typical states include:

### Recognition disabled

```text
Recognition OFF
Press START
```

### Recognition enabled

```text
Recognition ON
Scanning...
```

### No face

```text
Scanning...
No Face
```

### Unknown person

```text
Face Status:
Not Recognized
```

### Authorized face

```text
Face:
<person name>
```

### Unlock timer active

```text
Unlocked
Hold Time
```

### Program stopped

```text
System Stopped
```

The program also avoids rewriting the LCD if the text has not changed, which reduces unnecessary display updates and flicker.

---

## 15. Shutdown Behavior

The main application uses a `try / finally` structure.

When the program is interrupted, it performs cleanup:

```text
Status LED OFF
Relay OFF
LCD "System Stopped"
LCD cleared
Camera stopped
```

This is important for an electromechanical access-control prototype because the relay should not intentionally be left in its commanded unlock state when the application exits normally.

---

## 16. Optional Automatic Startup

The repository contains:

```text
systemd/smart-door.service
```

A `systemd` service allows the Raspberry Pi to start the smart-door application automatically during boot instead of requiring somebody to manually open a terminal and launch Python.

Typical sequence:

```text
Raspberry Pi powers on
        |
        v
Linux boots
        |
        v
systemd starts smart-door.service
        |
        v
smart_door.py launches
        |
        v
System waits for START button
```

The service file contains example paths and should be edited to match the actual Raspberry Pi username and repository location.

---

## 17. Complete System State Sequence

A normal authorized entry looks like this:

```text
1. Raspberry Pi boots
2. Smart-door program starts
3. LCD says "Recognition OFF / Press START"
4. User presses START
5. Camera scans continuously
6. Face enters camera view
7. Software detects a face
8. Face encoding is generated
9. Encoding is compared with saved authorized encodings
10. Match is found
11. LCD displays recognized person's name
12. Status LED turns on
13. GPIO 5 commands the active-low relay
14. Relay changes the 12 V lock circuit
15. Door unlocks
16. Four-second hold timer starts
17. Person opens/passes through the door
18. Face can disappear from the camera
19. Relay remains in unlock state until the timer expires
20. Relay returns to inactive state
21. Door returns to locked state
22. Camera continues scanning for the next person
```

---

## 18. Software State Diagram

```text
                       +------------------+
                       | Recognition OFF  |
                       | Relay OFF        |
                       +--------+---------+
                                |
                         START pressed
                                |
                                v
                       +------------------+
                       |    SCANNING      |
                       | Relay OFF        |
                       +----+--------+----+
                            |        |
                    known face     unknown/no face
                            |        |
                            v        |
                       +------------+ |
                       | AUTHORIZED | |
                       | Relay ON   | |
                       +-----+------+ |
                             |        |
                       reset 4 s      |
                       timer          |
                             |        |
                             v        |
                       +------------+ |
                       | HOLD OPEN  | |
                       | Relay ON   | |
                       +-----+------+ |
                             |        |
                      timer expires   |
                             |        |
                             +--------+
                                  |
                                  v
                              SCANNING

At any point:
STOP pressed -> Recognition OFF + Relay OFF
```

---

## 19. Important Hardware Engineering Considerations

For a production-quality version, the following hardware details should be documented and verified:

### Relay driver

The exact relay module and its:

- coil/input voltage,
- GPIO compatibility,
- transistor/optocoupler interface,
- contact current rating,
- and active-low behavior.

### Solenoid supply

The 12 V supply must be able to provide enough current for the lock without using the Raspberry Pi power rail.

### Flyback / inductive transient protection

A solenoid is an inductive load. When current is interrupted it can generate a voltage spike.

Depending on the lock and relay module, appropriate suppression may include:

- flyback diode for a DC solenoid,
- TVS protection,
- snubber circuitry,
- or protection already integrated into the lock/driver.

### Electrical isolation

The Raspberry Pi logic circuitry should be protected from the lock's higher-current circuit.

### Lock type

Document whether the final lock is:

- fail-secure, or
- fail-safe.

This determines what happens during a power failure.

---

## 20. What Is Proven by the Project Files vs. Inferred

### Directly supported by the software

The source code confirms:

- Raspberry Pi GPIO-based control
- GPIO 5 used for the lock relay
- an active-low relay configuration
- a 12 V solenoid lock is the intended controlled device
- GPIO 22 status LED
- START button on GPIO 17
- STOP button on GPIO 27
- 16x2 LCD interface
- face recognition through stored encodings
- authorized/unknown decision logic
- four-second unlock hold
- relay shutdown when recognition is disabled
- camera cleanup at program termination

### Hardware behavior inferred from standard implementation practice

The Python source does **not** specify:

- the exact 12 V power-supply model,
- relay COM/NO/NC terminal connections,
- exact solenoid-lock model,
- relay contact rating,
- whether a flyback diode was external or integrated,
- exact wire colors,
- or whether the final lock is formally fail-safe or fail-secure.

The relay/12 V explanation in this document therefore describes the electrical architecture consistent with the source code, but those physical wiring details should be verified against the actual prototype before being stated as exact as-built connections.

---

## 21. One-Sentence Engineering Description

> Designed and implemented a Raspberry Pi facial-recognition access-control prototype integrating camera-based biometric authentication, GPIO push-button control, a 16x2 LCD and status LED, and an active-low relay interface driving a 12 V door-lock actuator with a timed four-second unlock cycle.

