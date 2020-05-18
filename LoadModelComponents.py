#   ANTgen -- the AMBAL-based NILM Trace generator
#
#   Copyright (C) 2020  Andreas Reinhardt <reinhardt@ieee.org>, TU Clausthal
#                       based on work by Nadezda Buneeva
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
from lxml import etree as ET


def exponential_fct(x, a, b, c):
    return a + b * np.exp(-c * x)  # for decay model


def logarithmic_fct(x, a, b, c):
    return a + b * np.log(c * x)  # for growth model


# definition of the fundamental appliance model types
class OnOffModel:
    type = "ON_OFF"

    def __init__(self):
        pass

    def init_with_values(self, on_power, duration):
        self.on = on_power
        self.dur = duration
        return self

    def init_from_xml(self, xml_component):
        self.on = float(xml_component.find('onPower').get('value'))
        self.dur = float(xml_component.find('duration').get('value'))
        return self

    def synthesize(self, length):
        return np.linspace(self.on, self.on, length)

    def __str__(self):
        return "f(x) = {:0.3f}".format(self.on)

    def append_as_xml_to(self, root, total_duration):
        load = ET.SubElement(root, "load", type=self.type)
        ET.SubElement(load, "onPower", value=str(self.on))
        ET.SubElement(load, "duration", value=str(1.0 * self.dur / total_duration))
        return load


class LinearModel:
    type = "LINEAR"

    def __init__(self):
        pass

    def init_with_values(self, start_power, end_power, duration):
        self.dur = duration
        self.sta = start_power
        self.end = end_power
        return self

    def init_from_xml(self, xml_component):
        self.dur = float(xml_component.find('duration').get('value'))
        self.sta = float(xml_component.find('startPower').get('value'))
        self.end = float(xml_component.find('endPower').get('value'))
        return self

    def synthesize(self, length):
        return np.linspace(self.sta, self.end, length)

    def __str__(self):
        return "f(x) = {:0.3f} -> ... -> {:0.3f}".format(self.sta, self.end)

    def append_as_xml_to(self, root, total_duration):
        load = ET.SubElement(root, "load", type=self.type)
        ET.SubElement(load, "startPower", value=str(self.sta))
        ET.SubElement(load, "endPower", value=str(self.end))
        ET.SubElement(load, "duration", value=str(1.0 * self.dur / total_duration))
        return load


class OnOffDecayModel:
    type = "ON_OFF_DECAY"

    def __init__(self):
        pass

    def init_with_values(self, on_power, add_power, decay, duration):
        self.on = on_power
        self.add = add_power
        self.dec = decay
        self.dur = duration
        return self

    def init_from_xml(self, xml_component):
        self.on = float(xml_component.find('activePower').get('value'))
        self.add = float(xml_component.find('peakPower').get('value'))
        self.dec = float(xml_component.find('decayRate').get('value'))
        self.dur = float(xml_component.find('duration').get('value'))
        return self

    def synthesize(self, length):
        return exponential_fct(np.linspace(0, length-1, length), self.on, self.add-self.on, self.dec)

    def __str__(self):
        return "f(x) = {:0.3f} {} {:0.4f} * exp({:0.3f} * x)".format(self.on, '-' if self.add < 0 else '+', abs(self.add-self.on), self.dec)

    def append_as_xml_to(self, root, total_duration):
        load = ET.SubElement(root, "load", type=self.type)
        ET.SubElement(load, "activePower", value=str(self.on))
        ET.SubElement(load, "peakPower", value=str(self.on + self.add))  # peak = static ON + offset
        ET.SubElement(load, "decayRate", value=str(self.dec))
        ET.SubElement(load, "duration", value=str(1.0 * self.dur / total_duration))
        return load


class OnOffGrowthModel:
    type = "ON_OFF_GROWTH"

    def __init__(self):
        pass

    def init_with_values(self, base_power, scale, stretch, duration):
        self.bas = base_power
        self.sca = scale
        self.stf = stretch
        self.dur = duration
        return self

    def init_from_xml(self, xml_component):
        self.bas = float(xml_component.find('basePower').get('value'))
        self.sca = float(xml_component.find('growthRate').get('value'))
        try:
            self.stf = float(xml_component.find('stretchFactor').get('value'))  # not part of the original AMBAL format
        except AttributeError:
            self.stf = 1
        self.dur = float(xml_component.find('duration').get('value'))
        return self

    def synthesize(self, length):
        return logarithmic_fct(np.linspace(1, length, length), self.bas, self.sca, self.stf)

    def __str__(self):
        return "f(x) = {:0.3f} {} {:0.4f} * log({:0.3f} * (x+1) )".format(self.bas, '-' if self.sca < 0 else '+', abs(self.sca), self.stf)

    def append_as_xml_to(self, root, total_duration):
        load = ET.SubElement(root, "load", type=self.type)
        ET.SubElement(load, "basePower", value=str(self.bas))
        ET.SubElement(load, "growthRate", value=str(self.sca))
        ET.SubElement(load, "stretchFactor", value=str(self.stf))
        ET.SubElement(load, "duration", value=str(1.0 * self.dur / total_duration))
        return load


class NoiseModel:
    type = "NOISE"

    def __init__(self):
        pass

    def init_with_values(self, low, mean, stdev, high, duration):
        self.dur = duration
        self.low = low
        self.mean = mean
        self.stdev = stdev
        self.high = high
        return self

    def init_from_xml(self, xml_component):
        self.dur = float(xml_component.find('duration').get('value'))
        self.low = float(xml_component.find('lower').get('value'))
        self.mean = float(xml_component.find('mean').get('value'))
        self.stdev = float(xml_component.find('stdev').get('value'))
        self.high = float(xml_component.find('upper').get('value'))
        return self

    def bound(self, val):
        while val > self.high or val < self.low:
            val = np.random.normal(self.mean, self.stdev)
        return val

    def synthesize(self, length):
        data = np.random.normal(self.mean, self.stdev, length)
        return np.array([self.bound(x) for x in data])

    def __str__(self):
        return "f(x) = {:0.3f} +- {:0.3f} with {0.3f} <= f(x) <= {:0.3f})".format(self.mean, self.stdev, self.low, self.high)

    def append_as_xml_to(self, root, total_duration):
        load = ET.SubElement(root, "load", type=self.type)
        ET.SubElement(load, "lower", value=str(self.low))
        ET.SubElement(load, "mean", value=str(self.mean))
        ET.SubElement(load, "stdev", value=str(self.stdev))
        ET.SubElement(load, "upper", value=str(self.high))
        ET.SubElement(load, "duration", value=str(1.0 * self.dur / total_duration))
        return load
