#!/usr/bin/env python3

#   ANTgen nilmtk_converter -- NILMTK output for the AMBAL-based NILM Trace generator
#
#   Copyright (c) 2019-2020  Christoph Klemenjak <klemenjak@ieee.org>, Andreas Reinhardt
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

import argparse, sys, yaml, os
import pandas as pd

from nilmtk.datastore import Key
from nilmtk.measurement import LEVEL_NAMES
from nilmtk.utils import get_datastore
from nilm_metadata import convert_yaml_to_hdf5


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('inpath', help='input directory (ANTgen output)', nargs='?', default='../output')
    parser.add_argument('outfile', help='output file (HDF5 file)', nargs='?', default='../output/ANTgen.h5')
    args = parser.parse_args()

    if not os.path.exists('metadata') or not os.path.isfile('metadata/building1.yaml'):
        print("No metadata found. Please run 'generate_metadata.py' before using this tool...")
        exit(1)

    print("Converting ANTgen output from '{}' to file '{}'".format(args.inpath, args.outfile))

    with open('metadata/building1.yaml', 'r') as f:
        yaml_dict = yaml.load(f, Loader=yaml.FullLoader)

    channel_list = ['total']  # pre-populate with aggregate data (total.csv)
    for app in yaml_dict['appliances']:
        channel_list.append(app['original_name'])

    store = get_datastore(args.outfile, 'HDF', mode='w')

    for i, app_name in enumerate(channel_list):
        print("Adding virtual meter ID {:02d}: {}".format(1+i, app_name))
        key = Key(building=1, meter=(i + 1))

        csvfile = os.path.join(args.inpath, str(app_name)+'.csv')
        try:
            df = pd.read_csv(csvfile, sep=';', encoding='utf-8', index_col=0)
            df.columns = pd.MultiIndex.from_tuples([('power', 'active') for x in df.columns], names=LEVEL_NAMES)
            df.index = pd.to_datetime(df.index)

            tz_naive = df.index
            tz_aware = tz_naive.tz_localize(tz='Europe/Vienna', ambiguous=True, nonexistent=pd.Timedelta('1H'))
            df.index = tz_aware

            df = df.tz_convert('Europe/Vienna')

            store.put(str(key), df)
        except FileNotFoundError:
            print("Input file '{}' not found - your HDF5 file will be incomplete!".format(csvfile))
            continue

    print('Adding metadata...')
    convert_yaml_to_hdf5('metadata/', args.outfile)


if __name__ == "__main__":
    main()
