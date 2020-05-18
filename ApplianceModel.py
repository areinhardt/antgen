#   ANTgen -- the AMBAL-based NILM Trace generator
#
#   Copyright (C) 2019-2020  Andreas Reinhardt <reinhardt@ieee.org>, TU Clausthal
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

import logging
import Tools
import xml.etree.ElementTree as ET
import numpy as np
import random
import os.path
import LoadModelComponents
from bitarray import bitarray


class ApplianceModel:
    """A wrapper for composite appliance models"""

    def __init__(self, type, model_dir, num_days):
        self.logger = logging.getLogger(__name__)
        self.model_folder = model_dir.strip(os.path.sep)
        self.appliance_type = type
        self.busy = bitarray(num_days * Tools.secs_per_day)
        self.busy.setall(False)
        self.total_power = np.zeros([1, num_days * Tools.secs_per_day])

        # Check if file actually exists
        if not os.path.isdir(self.model_folder):
            raise ValueError("Configuration folder {} not found. Terminating...".format(model_dir))

        p = self.model_folder.rsplit(os.path.sep, 2)
        num_models = len([_ for _ in os.listdir(model_dir) if os.path.isfile(os.path.join(model_dir, _))])
        self.logger.info("Initialized model for {} (from {}) with {} AMBAL instance{}..."
                         .format(self.appliance_type, self.model_folder, num_models, 's' if num_models != 1 else ''))
        self.pick_another_model()

    def pick_another_model(self):
        model_file = random.choice(
            [x for x in os.listdir(self.model_folder) if os.path.isfile(os.path.join(self.model_folder, x))])

        # Parse the file
        # self.logger.debug("Initializing a new instance of appliance {} from file '{}'...".format(self.appliance_type, model_file))
        tree = ET.parse(os.path.join(self.model_folder, model_file))
        # configuration file seems to exist and be valid

        self.usual_duration = int(tree.getroot().get('duration'))
        if self.appliance_type.lower() != tree.getroot().get('type').lower():
            self.logger.warning("Specified appliance type ({}) does not match modeled device ({})".format(self.appliance_type, tree.getroot().get('type')))
        self.comps = []

        components = tree.getroot().findall('./load')
        for c in components:
            model_type = c.get('type')
            if model_type == 'ON_OFF':
                model = LoadModelComponents.OnOffModel().init_from_xml(c)
            elif model_type == 'LINEAR':
                model = LoadModelComponents.LinearModel().init_from_xml(c)
            elif model_type == 'ON_OFF_DECAY':
                model = LoadModelComponents.OnOffDecayModel().init_from_xml(c)
            elif model_type == 'ON_OFF_GROWTH':
                model = LoadModelComponents.OnOffGrowthModel().init_from_xml(c)
            elif model_type == 'NOISE':
                model = LoadModelComponents.NoiseModel().init_from_xml(c)
            else:
                self.logger.warning("Unsupported model type '{}'".format(model_type))
                continue
            self.comps.append(model)

        self.logger.debug("Appliance model updated (type {}, {} components, duration {})"
                          .format(self.appliance_type, len(self.comps), self.usual_duration))

    def synthesize(self, offset, duration):
        self.logger.debug("Creating synthetic {} consumption of {} samples length".format(self.appliance_type, duration))
        this_cycle_power = np.zeros(self.total_power.shape)
        entry = this_cycle_power[0]

        start_offset = 0
        for idx, c in enumerate(self.comps):
            end_offset = start_offset + int(round(c.dur * duration))  # scale fraction up to absolute number of samples
            synth_len = end_offset - start_offset
            # self.logger.debug("Synthesizing {} for {:.2f}% of the time, i.e., {}s (from {}->{})"
            #                   .format(c, 100.0*c.dur, synth_len, start_offset, end_offset))
            if synth_len <= 0 or synth_len > 86400:
                self.logger.debug("Skipping model component of length {} - probably you are operating a long-lasting model for a shorter time only".format(synth_len))
                continue  # skip segments shorter than 1 second or longer than one day
            #self.logger.debug("Relative duration of component {:02d}/{:02d} ({}) is {:.2f}%, scheduled from {}->{}"
            #                 .format(1+idx, len(self.comps), c.type, 100.0*c.dur, start_offset, end_offset))
            entry[offset + start_offset:offset + end_offset] += c.synthesize(synth_len)
            start_offset = end_offset

        self.total_power += this_cycle_power
        self.busy[offset:offset + duration] = True

        return this_cycle_power
