#!/usr/bin/env python3

import asyncio
import datetime
import evdev
import json
import requests
import time

from typing import Optional, NamedTuple

import key

TColour = NamedTuple("TColour", [('bri', float), ('ct', float)])

_current_colour = TColour(bri=1.0, ct=1.0)
_current_on_state = False
_current_schedule_paused = False


def get_colour_for_now() -> TColour:
    global _current_schedule_paused
    if _current_schedule_paused:
        return TColour(bri=1.0, ct=0.5)
    now = datetime.datetime.now()
    # Day time is bright and white
    if now.hour > 8 and now.hour < 21:
        return TColour(bri=1.0, ct=0.0)
    # Up to midnight gets darker and more orange
    elif now.hour >= 21:
        # 9pm => p = 0.0, midnight => p = 1.0
        p = ((now.hour - 21) * 60 + now.minute) / (3.0 * 60.0)
        return TColour(bri=1.0 - p * 0.8, ct=p * 0.8 + 0.2)
    # Middle of the night is very dark and orange
    else:
        return TColour(bri=0.2, ct=1.0)


def set_state(on: Optional[bool] = None, colour: Optional[TColour] = None
              ) -> None:
    global _current_on_state
    data = {}
    if on is not None:
        _current_on_state = on
        data['on'] = on
    if colour is not None:
        data['ct'] = int(colour.ct * (500 - 153) + 153)
        data['bri'] = int(colour.bri * 255)
    data_json = json.dumps(data)
    for i in range(0, 5):
        requests.put('%s/lights/%d/state' % (key.API_URL, i), data=data_json)


def get_on_state() -> bool:
    global _current_on_state
    on = json.loads(requests.get(key.API_URL + '/lights/1').text)['state']['on']
    _current_on_state = on
    return on


async def button_loop(device: evdev.InputDevice) -> None:
    global _current_on_state
    global _current_schedule_paused
    async for event in device.async_read_loop():
        if event.value == 1:
            double_click_start_time = time.time()
            double_click = False
            while (time.time() - double_click_start_time) < 0.35 \
                    and not double_click:
                event = device.read_one()
                while event is not None:
                    if event.value == 1:
                        double_click = True
                        break
                    event = device.read_one()
                asyncio.sleep(0.1)
            if double_click:
                if _current_schedule_paused:
                    print('Double click, NOT pausing already paused schedule')
                else:
                    _current_schedule_paused = True
                    colour = get_colour_for_now()
                    print('Double click, pausing schedule, forcing on, ' +
                          'setting colour to: ', colour)
                    set_state(on=True, colour=colour)
            else:  # Single click
                if _current_schedule_paused:
                    _current_schedule_paused = False
                    colour = get_colour_for_now()
                    print('Button press -> unpausing schedule with: ', colour)
                    set_state(colour=colour)
                else:
                    _current_on_state = not _current_on_state
                    colour = get_colour_for_now()
                    print('Button press, on going from %s to %s, colour %s' % (
                          not _current_on_state, _current_on_state, colour))
                    set_state(on=_current_on_state, colour=colour)


async def schedule_loop() -> None:
    global _current_on_state
    while True:
        colour = get_colour_for_now()
        print('Schedule loop setting colour to: ', colour)
        set_state(colour=colour)
        await asyncio.sleep(60 * 5)


device = None
for device_file in evdev.list_devices():
    candidate_device = evdev.InputDevice(device_file)
    if candidate_device.name.startswith('ThinkPad Extra Buttons') or \
            candidate_device.name.startswith('Puck.js'):
        device = candidate_device
        break
get_on_state()
print('Starting with on state: ', _current_on_state)
if device is None:
    print('No button found')
else:
    print('Running with device: ', device.fn)
    asyncio.ensure_future(button_loop(device))
asyncio.ensure_future(schedule_loop())
loop = asyncio.get_event_loop()
loop.run_forever()
