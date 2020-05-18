#   ANTgen -- the AMBAL-based NILM Trace generator
#
#   Copyright (C) 2019  Andreas Reinhardt <reinhardt@ieee.org>, TU Clausthal
#
#   Permission is hereby granted, free of charge, to any person obtaining a copy
#   of this software and associated documentation files (the "Software"), to deal
#   in the Software without restriction, including without limitation the rights
#   to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#   copies of the Software, and to permit persons to whom the Software is
#   furnished to do so, subject to the following conditions:
#
#   The above copyright notice and this permission notice shall be included in all
#   copies or substantial portions of the Software.
#
#   THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#   IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#   FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#   AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#   LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#   OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#   SOFTWARE.

import numpy as np
from bitarray import bitarray

# let's define some constants
secs_per_block = 900  # 600=10min, 900=15min, 1200=20min, 1800=30min, 3600=60min
block_separator = 6  # space blocks apart every n hours

# internal variables
weekdays = {0: 'monday', 1: 'tuesday', 2: 'wednesday', 3: 'thursday', 4: 'friday', 5: 'saturday', 6: 'sunday'}
secs_per_day = 86400
blocks_per_day = int(secs_per_day / secs_per_block)
blocks_per_hour = int(blocks_per_day / 24)

# Helper to get a bitmap of user presence at home
def get_bitmap_from_timerange(comma_separated_timerange):
    bmp = bitarray(secs_per_day)  # always return *one* day of bits
    bmp.setall(False)

    for time_range in comma_separated_timerange.split(','):
        if '-' not in time_range: continue
        (fr, to) = time_range.split('-')
        if ':' not in fr or ':' not in to: continue

        # parse 'from' time
        (hr, mn) = fr.split(':')
        if int(hr) >= 24: hr = 24; mn = 0
        from_offset = 60 * (int(hr) * 60 + int(mn))

        # parse 'to' time
        (hr, mn) = to.split(':')
        if int(hr) >= 24: hr = 24; mn = 0
        to_offset = 60 * (int(hr) * 60 + int(mn))

        bmp[from_offset:to_offset] = True
    # iterating over all time ranges completed

    return bmp


def get_bitmap_from_weekday_list(weekday_list, num_days, start_day=0):
    bmp = bitarray(secs_per_day * num_days)
    bmp.setall(True)

    # read daily ranges (well, at least for the days defined)
    timespans = {}
    for day in weekdays.values():
        if day in weekday_list:
            timespans[day] = get_bitmap_from_timerange(weekday_list.get(day))

    for i in range(num_days):
        day = weekdays.get(int((start_day + i) % 7))
        if day in timespans.keys():
            bmp[i * secs_per_day:(i + 1) * secs_per_day] &= timespans[day]
        else:
            bmp[i * secs_per_day:(i + 1) * secs_per_day] = False
    # All availability levels should be initialized by now

    return bmp


def count(bitmap, value=True):
    return bitmap.count(value)


def visualize_header(start_day = 0):
    out = ' ' * 6
    if blocks_per_hour == 1:
        for i in range(0, 24):
            out += '{:1x} '.format(i%12)
            if i != 0 and (1 + i) % block_separator == 0:
                out += '  '
    else:
        for i in range(0, 24):
            start_time = str(i)
            start_time += 'h' if blocks_per_hour > 2 else ''
            out += '{:<s}{} '.format(start_time, ' ' * (blocks_per_hour-len(start_time)))
            if i != 0 and (1+i) % block_separator == 0:
                out += '  '
    return out

def visualize_map(bitmap, start_day=0):
    out = []

    if not isinstance(bitmap, bitarray):
        out.append("[No bit map to display]")
        return out

    for i in range(int(len(bitmap) / secs_per_day)):
        buf = '[{:3.3}] '.format(weekdays[((start_day + i) % 7)])
        for j in range(blocks_per_day):
            if j % blocks_per_hour == 0 and j != 0:
                buf += ' '
                if int(j/blocks_per_hour) % block_separator == 0:
                    buf += '| '
            ones = count(bitmap[i * secs_per_day + j * secs_per_block: i * secs_per_day + (j+1) * secs_per_block], True)
            # visualize fraction availability using 'boxy' unicode chars
            buf += chr(9601 + int(np.floor(7 * ones/secs_per_block)))
        out.append(buf)

    return out


def get_earliest(bitmap):
    try:
        return bitmap.index(True)
    except ValueError:
        return None


def get_latest(bitmap):
    bmp = bitmap.copy()
    bmp.reverse()
    off = get_earliest(bmp)
    if off is not None and off >= 0:
        return len(bitmap) - off
    return None
