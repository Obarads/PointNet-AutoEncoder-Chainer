import chainer
from chainer import serializers
from chainer import functions
from chainer import optimizers
from chainer import training
from chainer import iterators
from chainer.dataset import to_device
from chainer.datasets import TransformDataset
from chainer.training import extensions as E
from chainer.dataset.convert import concat_examples
from chainer.datasets.concatenated_dataset import ConcatenatedDataset

import numpy as np
import os
import argparse
from distutils.util import strtobool

# self made
import models.pointnet_ae as ae
import dataset

def main():
    parser = argparse.ArgumentParser(
        description='AutoEncoder ShapeNet')
    # parser.add_argument('--conv-layers', '-c', type=int, default=4)
    parser.add_argument('--batchsize', '-b', type=int, default=32)
    parser.add_argument('--dropout_ratio', type=float, default=0)
    parser.add_argument('--num_point', '-n', type=int, default=1024)
    parser.add_argument('--gpu', '-g', type=int, default=-1)
    parser.add_argument('--out', '-o', type=str, default='result')
    parser.add_argument('--epoch', '-e', type=int, default=250)
    parser.add_argument('--model_filename','-m', type=str, default='model.npz')
    parser.add_argument('--resume','-r', type=str, default='')
    parser.add_argument('--trans','-t', type=strtobool, default='true')
    parser.add_argument('--use_bn', type=strtobool, default='true')
    parser.add_argument('--residual', type=strtobool, default='false')
    parser.add_argument('--use_val','-v', type=strtobool, default='true')
    parser.add_argument('--class_choice','-c', type=str, default='Chair')
    args = parser.parse_args()

    batch_size = args.batchsize
    dropout_ratio = args.dropout_ratio
    num_point = args.num_point
    device = args.gpu
    out_dir = args.out
    epoch = args.epoch
    model_filename = args.model_filename
    resume = args.resume
    trans = args.trans
    use_bn = args.use_bn
    residual = args.residual
    use_val = args.use_val
    class_choice = args.class_choice

    trans_lam1 = 0.001
    trans_lam2 = 0.001
    out_dim = 3
    in_dim = 3
    middle_dim = 64

    try:
        os.makedirs(out_dir, exist_ok=True)
        import chainerex.utils as cl
        fp = os.path.join(out_dir, 'args.json')
        cl.save_json(fp, vars(args))
        print('save args to', fp)
    except ImportError:
        pass

    # Network
    print('Train PointNet-AutoEncoder model... trans={} use_bn={} dropout={}'
          .format(trans, use_bn, dropout_ratio))
    model = ae.PointNetAE(out_dim=out_dim, in_dim=in_dim, middle_dim=middle_dim, dropout_ratio=dropout_ratio, use_bn=use_bn,
                          trans=trans, trans_lam1=trans_lam1, trans_lam2=trans_lam2, residual=residual,output_points=num_point)

    print("Dataset setting... num_point={} use_val={}".format(num_point, use_val))
    # Dataset preparation

    train = dataset.ChainerPointCloudDatasetDefault(split="train", class_choice=[class_choice],num_point=num_point)
    if use_val:
        val = dataset.ChainerPointCloudDatasetDefault(split="val", class_choice=[class_choice],num_point=num_point)
        val_iter = iterators.SerialIterator(ConcatenatedDataset(*([val])), batch_size, repeat=False, shuffle=False)
    train_iter = iterators.SerialIterator(ConcatenatedDataset(*([train])), batch_size)

    print("GPU setting...")
    # gpu setting
    if(device >= 0):
        print('using gpu {}'.format(device))
        chainer.backends.cuda.get_device_from_id(device).use()
        model.to_gpu()

    # Optimizer
    optimizer = optimizers.Adam()
    optimizer.setup(model)

    # traning
    converter = concat_examples
    updater = training.StandardUpdater(
        train_iter, optimizer, device=device, converter=converter)
    trainer = training.Trainer(updater, (epoch, 'epoch'), out=out_dir)

    from chainerex.training.extensions import schedule_optimizer_value
    from chainer.training.extensions import observe_value
    # trainer.extend(observe_lr)
    observation_key = 'lr'
    trainer.extend(observe_value(
        observation_key,
        lambda trainer: trainer.updater.get_optimizer('main').alpha))
    trainer.extend(schedule_optimizer_value(
        [10, 20, 100, 150, 200, 230],
        [0.003, 0.001, 0.0003, 0.0001, 0.00003, 0.00001]))

    if use_val:
        trainer.extend(E.Evaluator(val_iter, model,
                                   converter=converter, device=device))
        trainer.extend(E.PrintReport(
            ['epoch', 'main/loss','main/dist_loss', 'main/trans_loss1',
             'main/trans_loss2', 'validation/main/loss','validation/main/dist_loss',
             'validation/main/trans_loss1', 'validation/main/trans_loss2',
             'lr', 'elapsed_time']))
    else:
        trainer.extend(E.PrintReport(
            ['epoch', 'main/loss', 'main/dist_loss', 'main/trans_loss1',
             'main/trans_loss2', 'lr', 'elapsed_time']))
    trainer.extend(E.snapshot(), trigger=(epoch, 'epoch'))
    trainer.extend(E.LogReport())
    trainer.extend(E.ProgressBar(update_interval=10))

    resume = ''
    if resume:
        serializers.load_npz(resume, trainer)
    print("Traning start.")
    trainer.run()

    # --- save classifier ---
    # protocol = args.protocol
    # classifier.save_pickle(
    #     os.path.join(out_dir, args.model_filename), protocol=protocol)
    serializers.save_npz(
        os.path.join(out_dir, model_filename), model)


if __name__ == '__main__':
    main()
