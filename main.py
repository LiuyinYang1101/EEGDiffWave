import os
import argparse
import json
from preprocess import get_data

from torch.utils.data import Dataset
from torch.utils.data import DataLoader
from torch.utils.data import random_split

import numpy as np
import torch
import torch.nn as nn
from torch.utils.tensorboard import SummaryWriter


from util import rescale, find_max_epoch, print_size
from util import training_loss, calc_diffusion_hyperparams

from distributed_util import init_distributed, apply_gradient_allreduce, reduce_tensor

from models import WaveNet_vocoder as WaveNet


class CustomDataset(torch.utils.data.Dataset):

    def __init__(self, data_path, sub, LOSO, isStandard, purpose):
        if purpose == 1:
            self.Data, _, self.Labels, _, _, _ = get_data(data_path, sub, LOSO, isStandard)

        elif purpose == 2:
            _, _, _, self.Data, _, self.Labels = get_data(data_path, sub, LOSO, isStandard)

    def __len__(self):
        return self.Data.shape[0]

    def __getitem__(self, idx):
        data = self.Data[idx, :, :, :]
        label = self.Labels[idx]
        return data, label


def train(num_gpus, rank, group_name, output_directory, tensorboard_directory,
          ckpt_iter, n_iters, iters_per_ckpt, iters_per_logging,
          learning_rate, batch_size_per_gpu):
    """
    Parameters:
    num_gpus, rank, group_name:     parameters for distributed training
    output_directory (str):         save model checkpoints to this path
    tensorboard_directory (str):    save tensorboard events to this path
    ckpt_iter (int or 'max'):       the pretrained checkpoint to be loaded;
                                    automitically selects the maximum iteration if 'max' is selected
    n_iters (int):                  number of iterations to train, default is 1M
    iters_per_ckpt (int):           number of iterations to save checkpoint,
                                    default is 10k, for models with residual_channel=64 this number can be larger
    iters_per_logging (int):        number of iterations to save training log, default is 100
    learning_rate (float):          learning rate
    batch_size_per_gpu (int):       batchsize per gpu, default is 2 so total batchsize is 16 with 8 gpus
    """

    # generate experiment (local) path
    local_path = "ch{}_T{}_betaT{}".format(wavenet_config["res_channels"],
                                           diffusion_config["T"],
                                           diffusion_config["beta_T"])
    # Create tensorboard logger.
    if rank == 0:
        tb = SummaryWriter(os.path.join('exp', local_path, tensorboard_directory))

    # distributed running initialization
    if num_gpus > 1:
        init_distributed(rank, num_gpus, group_name, **dist_config)

    # Get shared output_directory ready
    output_directory = os.path.join('exp', local_path, output_directory)
    if rank == 0:
        if not os.path.isdir(output_directory):
            os.makedirs(output_directory)
            os.chmod(output_directory, 0o775)
        print("output directory", output_directory, flush=True)

    # map diffusion hyperparameters to gpu
    for key in diffusion_hyperparams:
        if key is not "T":
            diffusion_hyperparams[key] = diffusion_hyperparams[key].cuda()

    # predefine model
    net = WaveNet(**wavenet_config).cuda()
    print_size(net)

    # apply gradient all reduce
    if num_gpus > 1:
        net = apply_gradient_allreduce(net)

    # define optimizer
    optimizer = torch.optim.Adam(net.parameters(), lr=learning_rate)

    # load checkpoint
    if ckpt_iter == 'max':
        ckpt_iter = find_max_epoch(output_directory)
    if ckpt_iter >= 0:
        try:
            # load checkpoint file
            model_path = os.path.join(output_directory, '{}.pkl'.format(ckpt_iter))
            checkpoint = torch.load(model_path, map_location='cpu')

            # feed model dict and optimizer state
            net.load_state_dict(checkpoint['model_state_dict'])
            if 'optimizer_state_dict' in checkpoint:
                optimizer.load_state_dict(checkpoint['optimizer_state_dict'])

            print('Successfully loaded model at iteration {}'.format(ckpt_iter))
        except:
            ckpt_iter = -1
            print('No valid checkpoint model found, start training from initialization.')
    else:
        ckpt_iter = -1
        print('No valid checkpoint model found, start training from initialization.')

    # training
    n_iter = ckpt_iter + 1
    while n_iter < n_iters + 1:
        for sub in range(9):
            data_path = 'C:/Users/YLY/Documents/bci-comp-iv2a/rawData/'
            LOSO = False
            isStandard = True

            data_train = CustomDataset(data_path, sub, LOSO, isStandard, 1)
            train, valid = random_split(data_train, [np.floor(len(data_train) * 0.8).astype(int),
                                                     (len(data_train) - np.floor(len(data_train) * 0.8)).astype(int)])
            test_dataset = CustomDataset(data_path, sub, LOSO, isStandard, 2)
            train_loader = DataLoader(
                train, batch_size=64, shuffle=False
            )
            vali_loader = DataLoader(
                valid, batch_size=64, shuffle=False
            )
            test_loader = DataLoader(
                test_dataset, batch_size=64, shuffle=False
            )
            # load training data
            # print('Data loaded')
            for i, data in enumerate(train_loader, 0):
                # get the inputs; data is a list of [inputs, labels]
                eeg, labels = data[0].squeeze(1).cuda(), data[1].type(torch.LongTensor).cuda()
                # load audio and mel spectrogram
                # mel_spectrogram = mel_spectrogram.cuda()
                # audio = audio.unsqueeze(1).cuda()

                # back-propagation
                optimizer.zero_grad()
                X = (labels, eeg.float())
                loss = training_loss(net, nn.MSELoss(), X, diffusion_hyperparams)
                # print(loss)
                if num_gpus > 1:
                    reduced_loss = reduce_tensor(loss.data, num_gpus).item()
                else:
                    reduced_loss = loss.item()
                loss.backward()
                optimizer.step()

                # output to log
                # note, only do this on the first gpu
                if n_iter % iters_per_logging == 0 and rank == 0:
                    # save training loss to tensorboard
                    print("iteration: {} \treduced loss: {} \tloss: {}".format(n_iter, reduced_loss, loss.item()))
                    tb.add_scalar("Log-Train-Loss", torch.log(loss).item(), n_iter)
                    tb.add_scalar("Log-Train-Reduced-Loss", np.log(reduced_loss), n_iter)

                # save checkpoint
                if n_iter > 0 and n_iter % iters_per_ckpt == 0 and rank == 0:
                    checkpoint_name = '{}.pkl'.format(n_iter)
                    torch.save({'model_state_dict': net.state_dict(),
                                'optimizer_state_dict': optimizer.state_dict()},
                               os.path.join(output_directory, checkpoint_name))
                    print('model at iteration %s is saved' % n_iter)

                n_iter += 1

    # Close TensorBoard.
    if rank == 0:
        tb.close()


if __name__ == "__main__":
    # Parse configs. Globals nicer in this case
    with open('configure.json') as f:
        data = f.read()
    config = json.loads(data)
    train_config = config["train_config"]  # training parameters
    global dist_config
    dist_config = config["dist_config"]  # to initialize distributed training
    global wavenet_config
    wavenet_config = config["wavenet_config"]  # to define wavenet
    global diffusion_config
    diffusion_config = config["diffusion_config"]  # basic hyperparameters
    global trainset_config
    trainset_config = config["trainset_config"]  # to load trainset
    global diffusion_hyperparams
    diffusion_hyperparams = calc_diffusion_hyperparams(
        **diffusion_config)  # dictionary of all diffusion hyperparameters

    torch.backends.cudnn.enabled = True
    torch.backends.cudnn.benchmark = True
    train(1, 0, "test", **train_config)