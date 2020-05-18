#!/usr/bin/env python3

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

import argparse
import configparser
import logging, logging.config
from time import gmtime, strftime, time
import sys
import os.path
import random
import re
import Tools
import numpy as np
import pandas as pd

from ApplianceModel import ApplianceModel
from UserModel import UserModel


def init_logger(name, ttyLevel = logging.INFO):
    global logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # create console handler
    format1 = logging.Formatter('%(name)+15s [%(levelname).1s] %(message)s') #:%(lineno)4d
    ch = logging.StreamHandler()
    ch.setLevel(ttyLevel)
    ch.setFormatter(format1)
    logger.addHandler(ch)

    # create file handler
    # format2 = logging.Formatter('%(asctime)s - %(levelname)-8s - %(message)s')
    # fh = logging.FileHandler("{}.log".format(name))
    # fh.setLevel(logging.DEBUG)
    # fh.setFormatter(format2)
    # logger.addHandler(fh)
# end of logger initialization


# read the n-th word from the local Python file to determine the current name of the tool
def init_progname_from_code(num):
    global progname
    counter = 0
    with open(__file__, "r") as file:
        for line in file:
            for word in line.split():
                counter += 1
                if counter is num:
                    progname = word
                    return progname


def is_file(filename):
    if not os.path.isfile(filename):
        msg = "{0} is not a valid file".format(filename)
        raise argparse.ArgumentTypeError(msg)
    else:
        return filename


# overriding the ArgumentParser class to always print usage
# (from https://stackoverflow.com/questions/4042452/)
class AlwaysPrintUsageParser(argparse.ArgumentParser):
    def error(self, message):
        sys.stderr.write('error: %s\n' % message)
        self.print_help()
        sys.exit(2)


def terminate(message):
    logger.error(message)
    logging.shutdown()
    sys.exit(1)


# populate the argument list with all available scripts
parser = AlwaysPrintUsageParser()  # argparse.ArgumentParser()
parser.add_argument("-o", "--output", metavar="DST", help="directory in which to store the output files")
parser.add_argument("-w", "--overwrite", action='store_true', help="Overwrite output files if they exist")
parser.add_argument("-s", "--seed", type=int, help="Initial value for the random number generator (overwritten by .conf)")
parser.add_argument("-a", "--alternate", action='store_true', help="Vary appliance models across operations")
parser.add_argument("-m", "--mapping", metavar="MAPFILE", help="Appliance mapping file (overwritten by .conf)", type=is_file)
parser.add_argument("-n", "--noise", metavar="NOISECFG", help="Noise configuration", type=str)
parser.add_argument("-d", "--days", metavar="DAYS", type=int, help="Number of days to generate data for (overrides .conf)")
parser.add_argument("-p", "--plot", action='store_true', help="Show resulting traces as plots")
parser.add_argument("-v", "--verbose", action='store_true', help="Output more progress messages")
parser.add_argument("configfile", help="configuration file to process", type=is_file)
args = parser.parse_args()


######################## LET'S GO ########################

def main():
    init_progname_from_code(4)  # work out what this tool is called

    # Set verbose logging if requested
    if args.verbose:
        init_logger(progname, logging.DEBUG)
    else:
        init_logger(progname)
    logger.info("{} started using '{}' on {}".format(progname, os.path.basename(args.configfile),
                                                     strftime("%d-%m-%Y at %H:%M:%S"), gmtime()))

    # Validate and interpret the configuration file
    config = configparser.ConfigParser()
    try:
        config.optionxform = str  # this disallows line-end comments, but preserves capitalization
        config.read(args.configfile)
        assert all(_ in config for _ in ['GENERAL', 'users'])
        assert 'name' in config['GENERAL']
    except AssertionError:
        terminate("Invalid configuration file invalid. Terminating...".format(args.configfile))
    # if we get here, the configuration file seems to be valid

    logger.debug("*" * 80)

    # Where to store the output?
    output_directory = os.path.join('.', 'output')
    if args.output:
        if os.path.isfile(args.output.rstrip(os.path.sep)):
            terminate("Cannot create output directory '{}' because a file of the same name exists".format(args.output))
        else:
            output_directory = args.output
    os.makedirs(output_directory, exist_ok=True)
    logger.info("Output files will be stored in {}".format(output_directory))

    # Check if we are supposed to use a particular random seed
    seed = int(round(time() * 1000))
    if 'seed' in config['GENERAL']:
        seed = config.getint('GENERAL', 'seed')
    elif args.seed is not None and int(args.seed) >= 0:
        seed = int(args.seed)
    random.seed(seed)
    logger.info("Initializing the random number generator with seed {}".format(seed))

    # Get number of users and days (for activities where needed)
    days = config.getint('GENERAL', 'days') if 'days' in config['GENERAL'] else 1
    if args.days is not None and int(args.days) > 0:
        days = int(args.days)
    logger.info("Preparing to output {} day{} of synthetic data...".format(days,('s' if days != 1 else '')))

    first_day = random.randint(0,6)
    logger.info("Starting synthetic trace output on a {}...".format(Tools.weekdays[first_day]))

    logger.debug("*"*80)

    # Read all required user models to process this configuration
    users = {}
    for u in config['users']:
        try:
            users[u] = UserModel(os.path.join('users', config.get('users', u)), days, first_day)
        except ValueError as v:
            terminate(str(v))
    # user models initialized

    logger.info("*"*80)

    # Read all required input models to process this configuration
    appliances = {}
    mapping = None

    # Load basic appliance mapping file and overwrite individual entries if specified
    if args.mapping is not None:
        logger.info("Loading appliance-to-model mapping from file {}".format(args.mapping))
        try:
            config2 = configparser.ConfigParser()
            config2.optionxform = str  # this disallows line-end comments, but preserves capitalization
            config2.read(args.mapping)
            assert 'devices' in config2.sections()
            mapping = config2['devices']
        except AssertionError:
            terminate("Mapping file {} invalid. Terminating...".format(args.mapping))

    if 'devices' in config.sections():
        if mapping is None:
            mapping = config['devices']
        else:
            for entry in config['devices']:
                logger.debug("Overriding model file for {}".format(entry))
                mapping[entry] = config['devices'].get(entry)

    if mapping is None:
        terminate("No appliance-to-model mapping! Add [devices] to the configuration or use the -m option. Terminating...")

    for appliance_key in mapping:
        try:
            am = ApplianceModel(appliance_key, os.path.join('appliances', mapping.get(appliance_key)), days)
        except ValueError as v:
            terminate(str(v))
        appliances[am.appliance_type] = am
        logger.debug("ID {}: Appliance model for {} created successfully with {} components"
                    .format(appliance_key, am.appliance_type, len(am.comps)))
    # required appliance models loaded

    logger.info("*"*80)

    # Validate that required appliance models for all activities are available
    logger.info("Binding appliance models to activities...")
    for user in users.values():
        required_devices = user.get_required_devices()
        if len(required_devices) == 0:
            logger.warning("User '{}' does not operate any appliances!".format(user.name))
        for rd in required_devices:
            logger.debug("Looking up a binding for appliance type '{}'...".format(rd))
            if rd in appliances.keys():
                user.bind_appliance_model(rd, appliances[rd])
            else:
                terminate("Cannot bind appliance type {} - no model available!".format(rd))
    # Done checking if all required appliance models are present and binding them to activities

    logger.info("*"*80)

    # Synthesize users, activities, and appliances together!
    start_time = time()
    duration = days * Tools.secs_per_day
    all_events = []
    all_powers = {'total': np.zeros([1, duration])}
    vary_runs = True if args.alternate is not None and args.alternate is True else False
    logger.info("Synthesizing '{}' for {} samples".format(config.get('GENERAL', 'name'), duration))
    for uid, user in users.items():
        logger.info("Synthesizing data for user ID '{}' ({})".format(uid, user.name))
        user.synthesize(all_powers, all_events, first_day, vary_runs)
    logger.info("Synthesis completed in {:0.3f} seconds".format(time() - start_time))
    # That's it. Easy, huh?

    logger.info("*"*80)

    # Generate fake starting date
    start_day = str(20010101 + first_day)
    date_range = pd.date_range(start=start_day, freq='S', periods=days * Tools.secs_per_day).strftime('%Y-%m-%d %H:%M:%S')

    # create event log, (and dump it when verbose, just in case)
    df = pd.DataFrame()
    for line in all_events:
        entry = line.split(';')
        if len(entry) != 4:
            logger.warning("Invalid log entry: {}".format(line))
            continue
        tstp = date_range[int(entry[0])]
        tp = entry[1]
        src = entry[2]
        evt = entry[3]
        d = pd.Series([tstp, tp, src, evt], index=['Time', 'Type', 'Source', 'Event'])
        df = df.append(d, ignore_index=True)
    df = df.sort_values(['Time', 'Event'], ascending=(True, False))[['Time', 'Type', 'Source', 'Event']].reset_index(drop=True)
    for idx, row in df.iterrows():
        logger.debug("Event {:3d}/{:3d}: {:>8s} [{:3s}] {:>30s} {:>5s}".format(1+idx, len(all_events), row['Time'], row['Type'], row['Source'], row['Event']))

    for an, ap in appliances.items():
        all_powers[an] = ap.total_power

    # Add noise if configured
    ncfg = re.compile('[A-Z][0-9]+')
    if args.noise is not None and ncfg.match(args.noise):
        if args.noise.startswith("G"):
            amplitude = abs(int(args.noise[1:]))
            all_powers['total'] += np.random.normal(amplitude, amplitude/10, len(all_powers['total'][0]))
            threshold_indices = all_powers['total'][0] < 0
            all_powers['total'][0][threshold_indices] = 0
            noise_config = "Gaussian {}W".format(amplitude)
        elif args.noise.startswith("C"):
            amplitude = abs(int(args.noise[1:]))
            all_powers['total'] += amplitude
            noise_config = "Constant {}W".format(amplitude)
        else:
            noise_config = "invalid"
    else:
        noise_config = "none"

    logger.debug("*"*80)

    # Write CSV data to files
    logger.info("Writing the resulting data to CSV via DataFrame...")
    file_counter = 0
    for k in all_powers.keys():
        outname = os.path.join(output_directory, '{}.csv'.format(k.replace(' ','_')))
        if os.path.isfile(outname) and args.overwrite is not True:
            logger.warning("Output file {} exists! To overwrite it, use the -w flag.".format(outname))
        else:
            logger.info("Writing load signature of '{}' to {}".format(k, outname))
            dfr = pd.DataFrame(all_powers[k].T, date_range)
            dfr.to_csv(outname, header=None, float_format='%.1f', sep=";")
            file_counter += 1

    # write event log
    outname = os.path.join(output_directory, 'events.csv')
    if os.path.isfile(outname) and args.overwrite is not True:
        logger.warning("Output file {} exists! To overwrite it, use the -w flag.".format(outname))
    else:
        logger.info("Writing event log to {}".format(outname))
        df.to_csv(outname, columns=['Time','Source','Event'], sep=";", index=False)
        file_counter += 1
    logger.info("=> {:d} out of {:d} output files written!".format(file_counter, 1+len(all_powers)))

    # Plot the data
    if args.plot is True:
        try:
            mpl_logger = logging.getLogger('matplotlib')  # silence plot-related logging
            mpl_logger.setLevel(logging.WARNING)
            import matplotlib.pyplot as plt  # added only here to allow running ANTgen on headless machines

            logger.info("Plotting aggregate data...")
            plt.rcParams['toolbar'] = 'None'
            global fig; fig = plt.figure(num=None, figsize=(16, 9), dpi=80, facecolor='w', edgecolor='k')
            plt.subplots_adjust(bottom=0.05, top=0.96, left=0.05, right=0.99,hspace=0.5)
            plt.tight_layout()

            ax = {}
            global lined; lined = dict()
            for i in range(4):
                ax[i] = plt.subplot(411+i)
                ax[i].set_xlim([0, days * Tools.secs_per_day])
                ax[i].set_xlabel("Time [hrs]")
                ax[i].set_ylabel("Power [W]")
                ax[i].title.set_size(9)
                tix = range(0, 1 + days * Tools.secs_per_day, 3600 * days)
                ax[i].set_xticks(tix)
                ax[i].set_xticklabels([int(t/3600) for t in tix])
                lines = []

                if i == 0:
                    ax[i].set_title("Aggregate consumption")
                    p = all_powers['total']
                    line, = ax[i].plot(p.reshape((days*Tools.secs_per_day,)), label="total")

                elif i == 1:
                    ax[i].set_title("Per-user consumption")
                    for n in users.values():
                        p = all_powers[n.name]
                        p = p.reshape((days*Tools.secs_per_day,))
                        if max(p) > 0:
                            line, = ax[i].plot(p, label=n.name)
                            lines.append(line)

                elif i == 2:
                    ax[i].set_title("Per-activity consumption")
                    acits = dict()
                    for u in users.values():
                        for a in u.activities.values():
                            if a.activity_type in acits.keys():
                                logger.debug("NOTE: Multiple users execute activity '{}'!".format(a.activity_type))
                            else:
                                acits[a.activity_type] = a

                    for a in acits.values():
                        p = all_powers[a.activity_type]
                        p = p.reshape((days*Tools.secs_per_day,))
                        if max(p) > 0:
                            line, = ax[i].plot(p, label=a.activity_type)
                            lines.append(line)

                elif i == 3:
                    ax[i].set_title("Per-appliance consumption")
                    for n, a in appliances.items():
                        p = a.total_power
                        p = p.reshape((days*Tools.secs_per_day,))
                        if max(p) > 0:
                            line, = ax[i].plot(p, label=a.appliance_type)
                            lines.append(line)

                leg = ax[i].legend(loc=2, fontsize=10-int(len(ax[i].lines)/4), ncol=1+int(len(ax[i].lines)/5))

                # add handles to diagram lines to 'lined' dict (for toggling)
                for legline, origline in zip(leg.get_lines(), lines):
                    legline.set_picker(5)  # 5 pts tolerance
                    lined[legline] = origline

            # allow toggling individual curves by clicking on the legend entry
            cid = fig.canvas.mpl_connect('pick_event', on_legend_click)

            logger.info("Done. Close plot window to terminate...")
            plt.show()
            # Waiting for the user to close the plot
        except ImportError as e:
            logger.warning("Plotting failed. Are you sure you have matplotlib installed?")
            print(e)
    # (optional) plotting completed

    logger.info("*"*80)

    concurrency = 0
    maximum_concurrency = 0
    for row in df['Event']:
        if 'ON' in row:
            concurrency = concurrency + 1
            if concurrency > maximum_concurrency: maximum_concurrency = concurrency
        elif 'OFF' in row:
            concurrency = concurrency - 1

    logger.info("Trace duration (days)  : {:14d}".format(days))
    logger.info("First weekday          : {:>14s}".format(Tools.weekdays[first_day]))
    logger.info("# active devices       : {:14d}".format(len(df['Source'].value_counts())))
    logger.info("# appliance operations : {:14d}".format(int(sum(df['Source'].value_counts())/2)))
    logger.info("-"*39)
    for n, _ in appliances.items():
        logger.info("{:>16s} #runs : {:14d}".format(n, int(len(df[df.Source.eq(n)]) / 2)))
    logger.info("-"*39)
    logger.info("Max. appl. concurrency : {:14d}".format(maximum_concurrency))
    logger.info("Random seed            : {:14d}".format(seed))
    logger.info("Added noise            : {:>14s}".format(noise_config))

    logger.info("*"*80)

    logger.info("{} completed using '{}' on {}".format(progname, os.path.basename(args.configfile), strftime("%d-%m-%Y at %H:%M:%S"), gmtime()))
    logging.shutdown()


# visibility toggling, adapted from https://matplotlib.org/3.1.0/gallery/event_handling/legend_picking.html
def on_legend_click(event):
    global lined
    global fig
    legline = event.artist
    origline = lined[legline]
    vis = not origline.get_visible()
    origline.set_visible(vis)
    legline.set_alpha(1.0) if vis else legline.set_alpha(0.2)
    fig.canvas.draw()

######################## DONE ########################


if __name__ == "__main__":
    main()
