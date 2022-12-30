# EEGDiffWave
Diffusion for EEG 

# Version 2.0: training for deeper network 

1. to run new experiemnts: use new_main.py and eegWave-new.ipynb<br />
2. To run the code, change the following paths in the configure.json file:<br />
  a)  data_path field of the trainset_config should be your bci-comp-iv2a directory, which can be downloaded through this link:
      http://bnci-horizon-2020.eu/database/data-sets<br />
3. Change the configure.json file in the new_main.py or the eegWave-new.ipynb depends on your choice of the network to train: <br />
  a) configure-same.json: use the same number of channels as the eeg data in the residual blocks: 0.8M parameters <br />
  b) configure-deep.json: use 128 channels in the residual blocks: 5.9M parameters <br />
  c) change the name (line 186 in the new_main.py) <br />



# Version 1.0: training for unconditional EEG generation  

1. main.py shares the exact same content as the jupyter notebook file (eegWave.ipynb)<br />
2. To run the code, change the following paths:<br />
  a) line 122 in main.py: data_path should be your bci-comp-iv2a directory, which can be downloaded through this link:
      http://bnci-horizon-2020.eu/database/data-sets<br />
  b) check points and logs are saved in the directory defined in the configure.json , if you want to continue training the same network, do not change anything in that json file.<br />
3. To run on multiple GPUs, read the description of the train function in main.py. You should provide several parameters.<br />
