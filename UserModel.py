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
import configparser
import random
import Tools
import os.path
from bitarray import bitarray
import numpy as np
from ActivityModel import ActivityModel


class UserModel:
    """Wrapper for a user model. Takes path to configuration file, number of days to allocate buffers for,
       and the weekday (0-6) on which to start synthesis as parameters. """

    def __init__(self, model_file, num_days, start_day):
        self.logger = logging.getLogger(__name__)
        self.availability = bitarray(num_days * 86400)
        self.availability.setall(True)
        self.days = num_days

        # Check if file actually exists
        if not os.path.isfile(model_file):
            raise ValueError("Configuration file {} not found. Terminating...".format(model_file))

        # Parse the file
        config = configparser.ConfigParser()
        try:
            config.read(model_file)
            assert all(_ in config for _ in ['GENERAL', 'presence']) and 'name' in config['GENERAL']
            self.name = config.get('GENERAL', 'name')
        except AssertionError:
            raise ValueError("Invalid format in configuration file {}!".format(model_file))
        except configparser.DuplicateOptionError as ex:
            raise ValueError("Duplicate option: {}".format(str(ex)))
        # configuration file seems to exist and be valid

        self.logger.debug("Parsing configuration for '{}' user...".format(self.name))

        # Populate presence vector
        self.availability = Tools.get_bitmap_from_weekday_list(config['presence'], num_days, start_day)

        self.activities = {}
        self.runs_per_day = {}
        self.possible_runtimes = {}
        for activity_index, activity_entry in enumerate([s for s in config.sections() if s.startswith('activity_')]):

            # check if entry has all fields required
            if not all(_ in config[activity_entry] for _ in ['model', 'daily_runs']):
                self.logger.warning("Incomplete activity '{}' in {}. Ignoring...".format(activity_entry, model_file))
                continue

            self.logger.debug("Adding activity model #{:02d} (from {}) to user..."
                              .format(1+activity_index, config.get(activity_entry, 'model')))

            activity_name = activity_entry.replace('activity_', '')
            self.activities[activity_name] = ActivityModel(os.path.join('activities', config.get(activity_entry, 'model')))
            self.runs_per_day[activity_name] = config.getfloat(activity_entry, 'daily_runs')
            self.possible_runtimes[activity_name] = Tools.get_bitmap_from_weekday_list(config[activity_entry],
                                                                                       num_days, start_day)

        self.logger.info("User model successfully created for '{}' ({} activit{})"
                          .format(self.name, len(self.activities), 'y' if len(self.activities) == 1 else 'ies'))

    def get_required_devices(self):
        li = []
        for a in self.activities.values():
            li.extend(a.unique_appliances())
        return list(set(li))  # list -> set -> list to remove duplicates

    def bind_appliance_model(self, dev_type, model):
        for a in self.activities.values():
            if dev_type in a.unique_appliances():
                a.bind_to_appliance(dev_type, model)

    def synthesize(self, all_powers, all_events, start_day, vary_appliance_runs = False):
        duration = self.days * Tools.secs_per_day
        all_powers[self.name] = np.zeros([1, duration])

        #self.logger.debug("Availability of user '{}' before scheduling any activities:".format(self.name))
        #user_avail = Tools.visualize_map(self.availability, start_day)
        #for e in user_avail:
        #    self.logger.debug(e)

        # Shuffle activities before trying to schedule them (give long-lasting ones a chance on crowded days)
        for i, (name, acti) in enumerate(sorted(self.activities.items(), key=lambda x: random.random())):
            self.logger.info("Generating load signature(s) for activity {}/{} ({}) for {} day{}..."
                             .format(1+i, len(self.activities), name, self.days, 's' if self.days != 1 else ''))
            total = acti.synthesize(all_powers, all_events, self.days, self.runs_per_day[name],
                                    self.possible_runtimes[name], self.availability, start_day, vary_appliance_runs)
            all_powers[self.name] += total
            all_powers['total'] += total

        #self.logger.debug("Availability of user '{}' after scheduling activities:".format(self.name))
        #user_avail = Tools.visualize_map(self.availability, start_day)
        #for e in user_avail:
        #    self.logger.debug(e)
