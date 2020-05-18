#!/usr/bin/env python3

#   ANTgen nilmtk_converter -- NILMTK output for the AMBAL-based NILM Trace generator
#
#   Copyright (c) 2019-2020  Andreas Reinhardt <reinhardt@ieee.org>, Christoph Klemenjak
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

import argparse, os
import difflib
from pathlib import Path


def input_type(valid_types, intended = None):
    tps = list(valid_types)
    for idx, t in enumerate(tps):
        print('[{:3d}] {:23.23s} '.format(1+idx, t), end = '')
        if idx % 4 == 3:
            print('') # line break after every 4 items

    # now let the user pick one
    if intended is not None:
        val = input('\nChoose ID for "{}": '.format(intended))
    else:
        val = input("\nChoose ID: ")

    try:
        v = int(val)
    except ValueError:
        v = 0

    if 0 < v < len(tps):
        return tps[int(val)-1]
    return "unknown"


def match_type(provided_type, valid_types):
    matches = difflib.get_close_matches(provided_type, valid_types)
    if len(matches) == 0:
        print('-> No NILMTK appliance with exact name match found. Select one from the following list:')
        ap_type = input_type(valid_types, provided_type)
    else:
        cnt = 1
        for m in matches:
            print('[{}] {}'.format(cnt, matches[cnt-1]))
            cnt += 1
        print('[{}] One not in this list'.format(cnt))
        response = input("Select appliance ID: ")

        try:
            resp = int(response)
        except ValueError:
            resp = 0

        if 0 < resp <= len(matches):
            ap_type = matches[int(response)-1]
        else:
            ap_type = input_type(valid_types, provided_type)
    return ap_type


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-t', '--typelist', help='file containing a list of valid NILMTK appliance types', default='nilm.types')
    parser.add_argument('path', help='directory of ANTgen output', nargs='?', default='../output/')
    args = parser.parse_args()

    if not os.path.exists(args.path):
        print("Invalid path to ANTgen data {}".format(os.path.realpath(args.path)))
        exit(1)

    # Let's go
    print("Generating metadata for ANTgen output in {}".format(args.path))

    # Read list of valid types
    type_counts = {}
    if args.typelist is not None and os.path.exists(args.typelist):
        with open(args.typelist) as file:
            for ap_type in sorted(file, key=lambda s: s.lower()):
                atype = ap_type.rstrip("\n")
                type_counts[atype] = 1
        print('Found {} appliance types supported by NILMTK...'.format(len(type_counts)))
    else:
        print("ERROR: No list of device types given, please pass a list using the '-t nilm.types' argument!")        
        exit(1)

    # Locate ANTgen files and match to NILMTK types
    entries = []
    counter = 2
    for filename in os.listdir(args.path):
        if filename.endswith(".csv") and os.path.splitext(filename)[0].isupper():
            print("="*80)
            ap_type = os.path.splitext(filename)[0]

            print("-> Found appliance of type '{}'. Looking up valid mappings...".format(ap_type.capitalize()))
            type = match_type(ap_type.capitalize(), type_counts.keys())
            entries.append("""- original_name: {}
  type: {}
  description: simulated {} device
  instance: {}
  meters: [{}]
""".format(ap_type, type, ap_type.lower(), type_counts[type], counter))
            counter += 1
            type_counts[type] += 1
    ## All entries populated. Let's write them to a file...

    subdir='metadata/'
    Path(subdir).mkdir(exist_ok=True)
    with open(os.path.join(subdir, 'building1.yaml'), 'w') as writer:
        writer.write('''instance: 1
original_name: ANTgen
elec_meters:
  1: &simulator_mains
    site_meter: true
    device_model: simulator
  2: &simulator
    submeter_of: 0
    device_model: simulator
''')

        for i in range(3, 3+(len(entries)-1)):
            writer.write('  {}: *simulator\n'.format(i))
        writer.write('\nappliances:\n\n')

        for entry in entries:
            writer.write('{}\n'.format(entry))

        writer.write('construction_year: 2020\n')
    print("Metadata successcully created in the '{}' subdirectory".format(subdir))

if __name__ == "__main__":
    main()
