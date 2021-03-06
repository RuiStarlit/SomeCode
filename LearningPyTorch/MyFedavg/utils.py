# -*- coding:utf-8 -*-
"""
Author: RuiStarlit
File: utils
Project: LearningPyTorch
Create Time: 2021-07-07

"""
import copy
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torchvision import datasets, transforms
from sampling import cifar10_noniid, DatasetSplit, cifar100_noniid, cifar10_iid
from sampling import mnist_iid, mnist_noiid


def average_weights(w):
    """
    对参数进行加权求和
    权重为每个用户拥有的数据样本占该轮通信的所有数据样本的比例；
    """
    w_avg = copy.deepcopy(w[0])
    for key in w_avg.keys():
        for i in range(1, len(w)):
            w_avg[key] += w[i][key]
        w_avg[key] = torch.div(w_avg[key], len(w))
    return w_avg


class LocalUpdate(object):
    def __init__(self, args, dataset, idxs):
        self.args = args
        self.trainloader, self.validloader, self.testloader = self.train_val_test(
            dataset, list(idxs))
        self.device = args.device
        # self.device = "cuda" if torch.cuda.is_available() else "cpu"
        # Default criterion set to NLL loss function
        # self.criterion = nn.NLLLoss().to(self.device)
        self.criterion = nn.CrossEntropyLoss().to(self.device)

    def train_val_test(self, dataset, idxs):
        """
        Returns train, validation and test dataloaders for a given dataset
        and user indexes.
        """
        # split indexes for train, validation, and test (80, 10, 10)
        idxs_train = idxs[:int(0.8 * len(idxs))]
        idxs_val = idxs[int(0.8 * len(idxs)):int(0.9 * len(idxs))]
        idxs_test = idxs[int(0.9 * len(idxs)):]

        trainloader = DataLoader(DatasetSplit(dataset, idxs_train),
                                 batch_size=self.args.local_bs, shuffle=True)
        validloader = DataLoader(DatasetSplit(dataset, idxs_val),
                                 batch_size=int(len(idxs_val) / 10), shuffle=False)
        testloader = DataLoader(DatasetSplit(dataset, idxs_test),
                                batch_size=int(len(idxs_test) / 10), shuffle=False)
        return trainloader, validloader, testloader

    def update_weights(self, model, global_round):
        # Set mode to train model
        model.train()
        epoch_loss = []

        # Set optimizer for the local updates
        if self.args.optimizer == 'sgd':
            optimizer = torch.optim.SGD(model.parameters(), lr=self.args.lr,
                                        momentum=0.5)
        elif self.args.optimizer == 'adam':
            optimizer = torch.optim.Adam(model.parameters(), lr=self.args.lr,
                                         weight_decay=1e-4)

        for iter in range(self.args.local_ep):
            batch_loss = []
            for batch_idx, (images, labels) in enumerate(self.trainloader):
                images, labels = images.to(self.device), labels.to(self.device)

                model.zero_grad()
                log_probs = model(images)
                # loss = self.criterion(log_probs, labels)
                loss = torch.nn.functional.cross_entropy(log_probs, labels)
                loss.backward()
                optimizer.step()

                if self.args.verbose and (batch_idx % 10 == 0):
                    print('| Global Round : {} | Local Epoch : {} | [{}/{} ({:.0f}%)]\tLoss: {:.6f}'.format(
                        global_round, iter, batch_idx * len(images),
                        len(self.trainloader.dataset),
                                            100. * batch_idx / len(self.trainloader), loss.item()))
                batch_loss.append(loss.item())
            epoch_loss.append(sum(batch_loss) / len(batch_loss))
            if hasattr(torch.cuda, 'empty_cache'):
                torch.cuda.empty_cache()

        return model.state_dict(), sum(epoch_loss) / len(epoch_loss)

    def inference(self, model):
        """ Returns the inference accuracy and loss.
        """

        model.eval()
        loss, total, correct = 0.0, 0.0, 0.0

        for batch_idx, (images, labels) in enumerate(self.testloader):
            images, labels = images.to(self.device), labels.to(self.device)

            # Inference
            with torch.no_grad():
                outputs = model(images)
            batch_loss = self.criterion(outputs, labels)
            loss += batch_loss.item()

            # Prediction
            # _, pred_labels = torch.max(outputs, 1)
            # pred_labels = pred_labels.view(-1)
            # correct += torch.sum(torch.eq(pred_labels, labels)).item()
            correct += (outputs.argmax(1) == labels).type(torch.float).sum().item()
            total += len(labels)

        accuracy = correct / total
        return accuracy, loss


def get_dataset(args):
    if args.dataset == 'cifar10':
        data_dir = '../data/cifar10/'
        apply_transform = transforms.Compose(
            [
             transforms.ToTensor(),
             transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]), ])
        # ToTensor()能够把灰度范围从0-255变换到0-1之间，而后面的transform.Normalize()则把0-1变换到(-1,1)

        train_dataset = datasets.CIFAR10(data_dir, train=True, download=True,
                                         transform=apply_transform)

        test_dataset = datasets.CIFAR10(data_dir, train=False, download=True,
                                        transform=apply_transform)
        user_groups = cifar10_noniid(train_dataset, args)
        return train_dataset, test_dataset, user_groups
    elif args.dataset == 'cifar100':
        data_dir = '../data/cifar100/'
        apply_transform = transforms.Compose(
            [
             transforms.ToTensor(),
             transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]), ])

        train_dataset = datasets.CIFAR100(data_dir, train=True, download=True,
                                          transform=apply_transform)

        test_dataset = datasets.CIFAR100(data_dir, train=False, download=True,
                                         transform=apply_transform)
        user_groups = cifar100_noniid(train_dataset, args)
        return train_dataset, test_dataset, user_groups
    elif args.dataset == 'cifar10iid':
        data_dir = '../data/cifar10/'
        apply_transform = transforms.Compose(
            [
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]), ])

        train_dataset = datasets.CIFAR10(data_dir, train=True, download=True,
                                         transform=apply_transform)

        test_dataset = datasets.CIFAR10(data_dir, train=False, download=True,
                                        transform=apply_transform)

        # sample training data amongst users
            # Sample IID user data from Mnist
        user_groups = cifar10_iid(train_dataset, args.num_users)
        return train_dataset, test_dataset, user_groups
    elif args.dataset == 'cifar100iid':
        data_dir = '../data/cifar100/'
        apply_transform = transforms.Compose(
            [
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]), ])

        train_dataset = datasets.CIFAR100(data_dir, train=True, download=True,
                                         transform=apply_transform)

        test_dataset = datasets.CIFAR100(data_dir, train=False, download=True,
                                        transform=apply_transform)

        # sample training data amongst users
            # Sample IID user data from Mnist
        user_groups = cifar10_iid(train_dataset, args.num_users)
        return train_dataset, test_dataset, user_groups
    elif args.dataset == 'mnist_iid' or args.dataset == 'mnist_noiid':
        data_dir = '../data/mnist/'
        apply_transform = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize((0.1307,), (0.3081,))])

        train_dataset = datasets.MNIST(data_dir, train=True, download=True,
                                       transform=apply_transform)

        test_dataset = datasets.MNIST(data_dir, train=False, download=True,
                                      transform=apply_transform)
        if args.dataset == 'mnist_iid':
            user_groups = mnist_iid(train_dataset, args.num_users)
        elif args.dataset == 'mnist_noiid':
            user_groups = mnist_noiid(train_dataset, args)
        else:
            raise NotImplementedError()
        return train_dataset, test_dataset, user_groups

    else:
        raise NotImplementedError()


def test_inference(args, model, test_dataset):
    """ Returns the test accuracy and loss.
    """

    model.eval()
    loss, total, correct = 0.0, 0.0, 0.0

    device = args.device
    # device = "cuda" if torch.cuda.is_available() else "cpu"
    criterion = nn.NLLLoss().to(device)
    testloader = DataLoader(test_dataset, batch_size=128,
                            shuffle=False)

    for batch_idx, (images, labels) in enumerate(testloader):
        images, labels = images.to(device), labels.to(device)

        # Inference
        with torch.no_grad():
            outputs = model(images)
        batch_loss = criterion(outputs, labels)
        loss += batch_loss.item()

        # Prediction
        _, pred_labels = torch.max(outputs, 1)
        pred_labels = pred_labels.view(-1)
        correct += torch.sum(torch.eq(pred_labels, labels)).item()
        total += len(labels)

    accuracy = correct / total
    return accuracy, loss
