# Converting an ANTgen data set for NILMTK

## Requirements

The NILMTK converter for ANTgen relies on a small number of Python libraries to fully function. Install them by typing:

```bash
pip3 install -r requirements.txt
```

## Workflow

1. Use ANTgen to create a synthetic dataset (see https://github.com/areinhardt/antgen for instructions)

2. Generate the required metadata by assigning each of the contained appliances a device type used in NILMTK.
This step is used to create compatibility with other data sets, so make sure to assign one of the NILMTK device
types to each of the (synthetic) appliances in the ANTgen output. In case of doubt, choose "unknown".

```bash
python3 generate_metadata.py ../output/
```

3. Use our NILMTK dataset exporter to create a HDF5 file:

```bash
python3 convert_antgen.py ../output/ ANTgen.h5 
```

4. Have fun with ANTgen in NILMTK

```python
from nilmtk import DataSet

ant = DataSet('ANTgen.h5')
elec = ant.buildings[1].elec
print(elec)
```

## Known Issues

### Issue with hdfdatastore module

In case you receive the following error:

```
Traceback (most recent call last):
  File "convert_antgen.py", line 84, in <module>
    main()
  File "convert_antgen.py", line 49, in main
    convert_antgen(output_filename='../output/ANTgen.h5', input_path='../output/')
  File "convert_antgen.py", line 73, in convert_antgen
    store.put(str(key), df)
  File "/Users/christoph/anaconda/envs/antgen/lib/python3.6/site-packages/nilmtk/docinherit.py", line 46, in f
    return self.mthd(obj, *args, **kwargs)
  File "/Users/christoph/anaconda/envs/antgen/lib/python3.6/site-packages/nilmtk/datastore/hdfdatastore.py", line 171, in put
    expectedrows=len(value), index=False)
TypeError: put() got an unexpected keyword argument 'expectedrows'
```


Remove the keyword argument *expectedrows* from line 170 in `nilmtk/datastore/hdfdatastore.py`:

```python
self.store.put(key, value, format='table', index=False)
```

## Copyright notice

MIT Licence

Copyright (c) 2019-2020  Christoph Klemenjak <klemenjak@ieee.org>, Andreas Reinhardt

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
