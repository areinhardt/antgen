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
import os.path
import Tools
import timeit
import numpy as np
from bitarray import bitarray


class ActivityModel:
    """A wrapper for composite activity models. Takes a configuration file name as input and parses which
       appliance models are required to synthesize it into a trace. Note: All required appliances (can be
       figured out by calling *unique_appliances()* need a binding to an ApplianceModel to be synthesized."""

    def __init__(self, model_file):
        self.logger = logging.getLogger(__name__)

        # Check if file actually exists
        if not os.path.isfile(model_file):
            raise ValueError("Configuration file {} not found. Terminating...".format(model_file))

        # Parse the file
        self.logger.debug("Creating a new activity model from {}...".format(model_file))
        config = configparser.ConfigParser()
        try:
            config.read(model_file)
            assert all(_ in config for _ in ['GENERAL', 'devices', 'sequence']) and 'name' in config['GENERAL']
            self.activity_type = config.get('GENERAL', 'name')
        except AssertionError:
            raise ValueError("Invalid activity configuration file {}. Terminating...".format(model_file))
        # configuration file seems to exist and be valid

        # check required appliance types
        self.required_appliances = []
        self.appliance_binding = {}
        self.appliance_lookup = {0: 'None'}

        for device_id in config['devices']:
            device_type = config.get('devices', device_id)
            self.required_appliances.append(device_type)
            self.appliance_lookup[int(device_id)] = device_type
            self.appliance_binding[device_type] = None
        self.logger.debug("Required appliance models: {}".format(self.required_appliances))

        self.state_machine = {}
        for state_id in config['sequence']:
            self.state_machine[int(state_id)] = config.get('sequence', state_id)

        self.logger.debug("Activity model '{}' created ({} required appliance{}, {} state{})"
                          .format(self.activity_type, len(self.required_appliances),
                                  's' if len(self.required_appliances) != 1 else '',
                                  len(self.state_machine), 's' if len(self.state_machine) != 1 else ''))

    # Check which appliance models are needed to synthesize this model
    def unique_appliances(self):
        return list(set(self.required_appliances))

    # Assign an appliance model to this activity model (i.e., the model of the device to be synthesized)
    def bind_to_appliance(self, appliance_type, appliance_model):
        if appliance_type in self.required_appliances and appliance_type in self.appliance_binding.keys():
            self.appliance_binding[appliance_type] = appliance_model
            self.logger.info("Binding '{}' to activity '{}' ({}/{} requirements bound)".format(appliance_type,
                             self.activity_type, sum(d is not None for d in self.appliance_binding.values()),
                             len(self.appliance_binding)))
        else:
            self.logger.warning("No binding requested for appliance type {} - ignoring...".format(appliance_type))

    # Return whether all required appliance models have been provided (and if not, which ones are missing)
    def all_bindings_satisfied(self):
        if sum(d is None for d in self.appliance_binding.values()) == 0:
            return True, None
        else:
            return False, ', '.join(s for s in self.appliance_binding.keys() if self.appliance_binding.get(s) is None)

    # Get an operation flow from the sequence model
    def process_model(self, model_varies):
        schedule = {}
        total_duration = 0
        user_min_time = None
        user_max_time = 0

        if model_varies is True:
            for dev in self.appliance_binding.values():
                dev.pick_another_model()

        self.logger.debug("Executing state machine for activity '{}'...".format(self.activity_type))

        # And now for something different: A supercalifragilisticexpialidocious state machine interpreter
        current_state = 0
        while current_state < len(self.state_machine):
            cmd = self.state_machine.get(current_state)

            # state ID, name, min_duration, max_duration, involves_user, must_complete_before_transition, device, prob_for_a, state_a, state_b
            fmt = (str, int, int, lambda v: v == 'true', lambda v: v == 'true', int, float, int, int)
            try:
                (snm, mn, mx, usr, fin, devID, pa, sa, sb) = [type(val) for (type, val) in zip(fmt, cmd.replace(' ', '').split(','))]
            except ValueError as e:
                self.logger.warning("Incorrect state machine: {}".format(e))
                self.logger.warning("Skipping activity '{}'".format(self.activity_type))
                return 0, None, 0, 0

            if user_min_time is None and usr is True:  # this state is the first one to actively involve the user
                user_min_time = total_duration  # note: total_duration contains the current offset of the state machine

            # confirm that a valid state duration is given
            if mn == mx == 0 and devID == 0:
                self.logger.warning("Invalid duration of state '{}'! Will assume 5-10 seconds...".format(snm))
                mn = 5
                mx = 10

            # calculate total_duration of this state (0 or * => use default appliance runtime)
            if mn == mx == 0 and devID != 0:
                appliance_runtime = self.appliance_binding[self.appliance_lookup[devID]].usual_duration
            else:
                appliance_runtime = random.randint(min(mn, mx), max(mn, mx))

            self.logger.debug(
                "Activity '{}' - state {:02d}/{:02d} [{}] '{}': Running appliance '{}' for {} seconds from offset t={}"
                .format(self.activity_type, 1 + current_state, 1 + len(self.state_machine), 'USER' if usr else 'AUTO',
                        snm, self.appliance_lookup[devID], appliance_runtime, total_duration))

            if devID != 0:  # the 'null' device is reserved for states (like 'init') where no appliance is running
                schedule[total_duration] = (self.appliance_binding[self.appliance_lookup[devID]], appliance_runtime)

                if fin is True:
                    total_duration += appliance_runtime
                else:
                    # introduce some jitter in-between the operation of different appliances needed for this activity
                    total_duration += random.randint(5, 10)
            else:
                # skip ahead, but don't run anything
                total_duration += appliance_runtime

            # the initial state must define how long the user needs to set things up
            if usr is True:
                user_max_time = total_duration
                # self.logger.info("Updating max user involvement time to t={}".format(user_max_time))

            # progress to next state
            if random.random() < float(pa):
                current_state = int(sa)
            else:
                current_state = int(sb)
        # end of processing the state machine

        self.logger.debug("Activity '{}' - state {:02d}/{:02d} [NONE] 'final': Appliance operation completed at t={}s"
                          .format(self.activity_type, 1 + len(self.state_machine), 1 + len(self.state_machine),
                                  total_duration))

        if user_min_time is not None:
            self.logger.debug("Activity '{}': Appliance involves user during offsets {}->{} (total: {})"
                              .format(self.activity_type, user_min_time, user_max_time, user_max_time-user_min_time))

        return total_duration, schedule, user_min_time, user_max_time

    # Synthesize appliance power consumption and return it within the 'power' parameter
    def synthesize(self, powers, events, num_days, runs_per_day, time_of_run, user_available, start_day, vary_appliance):
        activity_power = np.zeros([1, num_days * Tools.secs_per_day])

        # sanity check (should never return missing dependencies, but let's make sure nonetheless)
        status, missing = self.all_bindings_satisfied()
        if status is False:
            self.logger.warning("Unsatisfied bindings ({})! Will NOT synthesize this activity!".format(missing))
            return activity_power

        # NOTE: powers is pass-by-reference, so anything we add here will be visible in the total tally
        if self.activity_type not in powers.keys():
            powers[self.activity_type] = np.zeros([1, num_days * Tools.secs_per_day])

        # track failures, if any to warn the user
        scheduling_failures = 0
        scheduling_success = 0

        # Iterate over the number of days to synthesize
        for d in range(num_days):
            iteration_start_time = timeit.default_timer()

            # work out if (and how many times) the given activity shall run
            if float(runs_per_day) >= 1:
                reps = round(float(runs_per_day + random.random() - 0.5))
            else:
                reps = 0 if random.random() > float(runs_per_day) else 1
            self.logger.debug("Trying to schedule {} instance{} of activity '{}' today".format(reps, 's' if reps != 1 else '', self.activity_type))

            day_filter = bitarray(num_days * Tools.secs_per_day)
            day_filter.setall(False)
            day_filter[d * Tools.secs_per_day:(d + 1) * Tools.secs_per_day] = True

            # then try to schedule it as often as needed
            scheduled_activities = 0
            for r in range(reps):
                (duration, appliance_schedule, user_earliest, user_latest) = self.process_model(vary_appliance)

                if appliance_schedule is None:
                    self.logger.warning("Could not find a suitable schedule for {}".format(self.activity_type))
                    scheduling_failures += reps
                    break
                # note: "duration" will be shorter than actual operation for devices that run unattended!

                # use a visualization to help troubleshoot if needed
                self.logger.debug('               {}'.format(Tools.visualize_header(start_day)))
                if user_latest != 0:  # activity requires user's presence to be executed
                    self.logger.debug("User available {}".format(Tools.visualize_map(user_available, start_day)[d]))
                self.logger.debug("Appl available {}".format(Tools.visualize_map(time_of_run, start_day)[d]))

                # figure out when the user is available and when the activity may run
                if user_earliest is not None:  # activity operation requires user interaction
                    availability = user_available & time_of_run & day_filter
                else:
                    availability = time_of_run & day_filter

                self.logger.debug("Possible times {}".format(Tools.visualize_map(availability, start_day)[d]))

                earliest_start, latest_start = Tools.get_earliest(availability), Tools.get_latest(availability)
                # self.logger.debug("Possible time ranges for activity: {} -> {}".format(earliest_start, latest_start))

                # terminate early if it's clear this activity cannot fit into the day
                if earliest_start is None or latest_start is None or earliest_start > latest_start + 1 - duration:
                    self.logger.debug("No suitable time slot for {} found today".format(self.activity_type))
                    if (time_of_run & day_filter).count() > 0:
                        scheduling_failures += 1
                    break

                # this variable stores the designated starting offset of this activity's operation, -1 = undefined
                starting_time = -1

                #  This probe is to find a time slot that fits the activity's operation. It may (or not) succeed
                for attempt in range(10):
                    # We don't cross day boundaries when picking a starting time yet - should we?
                    starting_time = random.randint(earliest_start, latest_start + 1 - duration)
                    candidate_bitmap_snippet = availability[starting_time:starting_time + duration]
                    # check that we can fully fit the snippet in
                    if candidate_bitmap_snippet.all() and starting_time + duration <= num_days * Tools.secs_per_day:
                        break  # found a suitable spot
                    else:
                        starting_time = -1

                # Doh, our random attempts were unsuccessful, so let's try out all options
                if starting_time == -1:
                    for starting_time in range(earliest_start, latest_start + 1 - duration):
                        candidate_bitmap_snippet = availability[starting_time:starting_time + duration]
                        if candidate_bitmap_snippet.all() and starting_time + duration <= num_days * Tools.secs_per_day:
                            break
                        else:
                            starting_time = -1

                if starting_time == -1:
                    #self.logger.warning("No suitable time slot left for a '{}' found today".format(self.activity_type))
                    scheduling_failures += 1
                    break

                # if we get here, we've found a suitable start time!
                success = True
                scheduled_activities += 1

                if user_earliest is not None and user_latest > 0:
                    #self.logger.debug("Marking user busy for {} samples from t={} to t={}"
                    #                 .format(duration, starting_time+user_earliest,
                    #                        starting_time + user_latest))
                    user_available[starting_time+user_earliest:starting_time + user_latest] = False
                else:
                    # self.logger.debug("Autonomous appliance - not impacting user availability")
                    pass

                # Avoid overlapping instances of the same activity
                time_of_run[starting_time:starting_time + duration] = False  # mark activity time as busy
                self.logger.debug("Appl operation {}".format(Tools.visualize_map(~(time_of_run), start_day)[d]))
                self.logger.debug("Activity successfully scheduled at offset t={} for duration of {} samples".format(starting_time, duration))
                #self.logger.debug("Update user av {}".format(Tools.visualize_map(user_available, start_day)[d]))

                # note: app_start is relative to activity, i.e., always starts at 0
                events.append("{};ACT;{};START".format(starting_time, self.activity_type))
                final = 0
                for (app_start, (app, dur)) in appliance_schedule.items():
                    # self.logger.info("Scheduling underyling appliance {} at offset {} for {}s".format(app.appliance_name, starting_time, dur))
                    events.append("{};DEV;{};ON".format(starting_time + app_start, app.appliance_type))
                    # self.logger.info("Logging device {} on at {}".format(app.appliance_name, starting_time+app_start))
                    app_power = app.synthesize(starting_time + app_start, dur)
                    activity_power += app_power
                    powers[self.activity_type] += app_power
                    events.append("{};DEV;{};OFF".format(starting_time + app_start + dur - 1, app.appliance_type))
                    if starting_time + app_start + dur - 1 > final:
                        final = starting_time + app_start + dur - 1
                    # self.logger.info("Logging device {} off at {}".format(app.appliance_name, starting_time+app_start+dur))
                events.append("{};ACT;{};END".format(final, self.activity_type))

                # self.logger.debug("Synthesis of '{}' completed".format(self.activity_type))
                # self.logger.debug("Appl scheduled {}".format(Tools.visualize_map(time_of_run, start_day)[d]))
            # done

            if num_days <= 10 or 1+d == num_days or d % 10 == 9 or d == 0:  # avoid too much logging
                self.logger.info("Activity '{}' synthesized {}x on day {:3d}/{:3d} in {:.2f} seconds".format(self.activity_type, scheduled_activities, 1+d, num_days, timeit.default_timer() - iteration_start_time))
            scheduling_success += scheduled_activities
        # all days processed

        if scheduling_success == 0:
            self.logger.warning("Synthesis of '{}' failed: Could not fit any of the {:d} runs".format(self.activity_type, scheduling_failures))
        elif scheduling_failures > 0:
            self.logger.info("Synthesis of '{}' done: {:d} scheduled, {:d} didn't fit".format(self.activity_type, scheduling_success, scheduling_failures))
        else:
            self.logger.info("Synthesis of '{}' done: {:d} runs scheduled".format(self.activity_type, scheduling_success))

        return activity_power
