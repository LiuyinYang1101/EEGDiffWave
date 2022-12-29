# EEGDiffWave
Diffusion for EEG 

# Version 1.0: training for unconditional EEG generation

1. main.py shares the exact same content as the jupyter notebook file (eegWave.ipynb)
2. To run the code, change the following paths:
  a) line 122 in main.py: data_path should be your bci-comp-iv2a directory, which can be downloaded through this link:
      http://bnci-horizon-2020.eu/database/data-sets
  b) check points and logs are saved in the directory defined in the configure.json , if you want to continue training the same network, do not change anything in that json file.
3. To run on multiple GPUs, read the description of the train function in main.py. You should provide several parameters.
