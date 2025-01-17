r"""
this script is used to train/fine-tune and validate/test the models
"""

#from dataset import *
from options import get_options
from model import *
import dgl
import pickle
import numpy as np
import os
from MyDataLoader2 import *
from time import time
from random import shuffle
import itertools


def DAG2UDG(g):
    r"""

    used to transform a (directed acyclic graph)DAG into a undirected graph

    :param g: dglGraph
        the target DAG

    :return:
        dglGraph
            the output undirected graph
    """
    edges = g.edges()
    reverse_edges = (edges[1],edges[0])
    # add the reversed edges
    new_edges = (th.cat((edges[0],reverse_edges[0])),th.cat((edges[1],reverse_edges[1])))
    udg =  dgl.graph(new_edges,num_nodes=g.num_nodes())

    # copy the node features
    for key, value in g.ndata.items():
        # print(key,value)
        udg.ndata[key] = value
    # copy the edge features
    udg.edata['direction'] = th.cat((th.zeros(size=(1,g.number_of_edges())).squeeze(0),th.ones(size=(1,g.number_of_edges())).squeeze(0)))

    return udg

def get_reverse_graph(g):
    edges = g.edges()
    reverse_edges = (edges[1], edges[0])

    rg = dgl.graph(reverse_edges, num_nodes=g.num_nodes())
    for key, value in g.ndata.items():
        # print(key,value)
        rg.ndata[key] = value
    for key, value in g.edata.items():
        # print(key,value)
        rg.edata[key] = value
    return rg



def load_model(device,options):
    r"""
    Load the model

    :param device:
        the target device that the model is loaded on
    :param options:
        some additional parameters
    :return:
        param: new options
        model : loaded model
        mlp: loaded mlp
    """
    print('----------------Loading the model and hyper-parameters----------------')
    model_dir = options.model_saving_dir
    # if there is no model in the target directory, break
    if os.path.exists(os.path.join(model_dir, 'model.pkl')) is False:
        print("No model, please prepocess first , or choose a pretrain model")
        assert False

    # read the pkl file that saves the hype-parameters and the model.
    with open(os.path.join(model_dir,'model.pkl'), 'rb') as f:
        # param: hyper-parameters, e.g., learning rate;
        # classifier: the model
        param, classifier = pickle.load(f)
        param.model_saving_dir = options.model_saving_dir
        classifier = classifier.to(device)

        # make some changes to the options
        if options.change_lr:
            param.learning_rate = options.learning_rate
        if options.change_alpha:
            param.alpha = options.alpha
    print('Model and hyper-parameters successfully loaded!')
    return param,classifier


def load_data(data_path):
   
    assert os.path.exists(data_path), \
        "Can not find the dataset file '{}'".format(data_path)
    with open(data_path,'rb') as f:
        graph = pickle.load(f)
        
    return graph

def test(options):
    th.multiprocessing.set_sharing_strategy('file_system')
    device = th.device("cuda:"+str(options.gpu) if th.cuda.is_available() else "cpu")
    predict_path = options.predict_path
    data_path = options.datapath
    print(data_path)
    if options.test_id == 0:
        test_save_file = 'test.pkl'
    else:
        test_save_file = 'test_{}.pkl'.format(options.test_id)
    test_data_file = os.path.join(data_path,test_save_file)

    print(options)
    # load the model
    options, model = load_model(device, options)
    if model is None:
        print("No model, please prepocess first , or choose a pretrain model")
        return
    print(model)

    in_nlayers = options.in_nlayers if isinstance(options.in_nlayers,int) else options.in_nlayers[0]
    out_nlayers = options.out_nlayers if isinstance(options.out_nlayers,int) else options.out_nlayers[0]

    print("----------------Loading data----------------")


    test_g = load_data(test_data_file)
    print(test_g)
    print('Data successfully loaded!')
    in_nlayers = max(1, in_nlayers)
    out_nlayers = max(1, out_nlayers)
    in_sampler = Sampler([None] *in_nlayers , include_dst_in_src=False)
    out_sampler = Sampler([None] * out_nlayers , include_dst_in_src=False)

    test_nids = th.tensor(range(test_g.num_nodes()))
    # test_nids = test_nids[test_g.ndata[label_name].squeeze(-1) != -1]

    # create dataloader for training/validate dataset
    graph_function = get_reverse_graph

    print(test_g.ndata['ntype'].shape,model.GCN1.in_dim)
    print(test_g.ndata['ntype'])

    testdataloader = MyNodeDataLoader(
        True,
        test_g,
        graph_function(test_g),
        test_nids,
        in_sampler,
        out_sampler,
        batch_size=test_g.num_nodes(),
        shuffle=True,
        drop_last=False,
    )

    beta = options.beta
    # set loss function

    print("----------------Start testing---------------")
    predict_labels = None
    runtime = 0

    with th.no_grad():
        for ni, (in_blocks, out_blocks) in enumerate(testdataloader):
            start = time()
            # transfer the data to GPU
            in_blocks = [b.to(device) for b in in_blocks]
            out_blocks = [b.to(device) for b in out_blocks]
            # print(out_blocks)
            # get in input features
            in_input_features = in_blocks[0].srcdata["ntype"]
            out_input_features = out_blocks[0].srcdata["ntype"]
            #print(in_input_features.shape,model.GNN1)
            # the central nodes are the output of the final block
            # predict the labels of central nodes
            label_hat = model(in_blocks, in_input_features, out_blocks, out_input_features)
            pos_prob = nn.functional.softmax(label_hat, 1)[:, 1]
            # adjust the predicted labels based on a given thredshold beta
            pos_prob[pos_prob >= beta] = 1
            pos_prob[pos_prob < beta] = 0
            predict_labels = pos_prob

            end = time()
            runtime += end - start

            os.makedirs(predict_path, exist_ok=True)

    print("----------------Saving the prediction results---------------")
    with open(os.path.join(predict_path, 'predicted_nids.pkl'), 'wb') as f:
        #predict_labels = predict_labels.cpu().numpy().tolist()
        pos_nids = th.tensor(range(len(predict_labels)))[predict_labels==1]
        pos_nids = pos_nids.numpy().tolist()
        pickle.dump(pos_nids,f)
if __name__ == "__main__":
    seed = 1234
    # th.set_deterministic(True)
    th.manual_seed(seed)
    th.cuda.manual_seed(seed)
    np.random.seed(seed)
    test(get_options())
