# -*- coding: utf-8 -*-
"""
Created on Wed Apr 01 02:33:10 2015

@author: ayanami
"""
import numpy as np
import scipy as sp
from greedy import *

from sklearn.externals import joblib




from loss_functions import entropy

def select_criteria(factory, thresholds_active,depth,verbose = True):
    """
    I find the most _even_ dichotomies of a given depth among the given thresholds... greedily
    """
    leaves = {"":factory}
    criteria = []

    for i in range(depth):
        entropies = []
        for feature,cut,_ in thresholds_active:
            split_distribution = []
            for leaf in leaves:
                subFactory = leaves[leaf]
                predicate = (subFactory.events[:,feature] > cut)
                trues = sum(subFactory.weights[predicate])
                
                split_distribution.append(trues)
                split_distribution.append(sum(subFactory.weights) - trues)
                
            split_distribution = np.array(split_distribution)/sum(factory.weights)
            entropies.append( entropy(split_distribution))

        feature,cut,_ = criterion = thresholds_active[entropies.index(max(entropies))]
        new_leaves = {}
        
        for leaf in leaves:
            subFactory = leaves[leaf]
            predicate = (subFactory.events[:,feature] > cut)
            new_leaves[leaf+"1"],new_leaves[leaf+"0"] = subFactory.split_by(predicate)

        leaves = new_leaves    
        criteria.append(criterion)
        if verbose:
            print 's:',[leaves[i].events.shape[0] for i in leaves]
            print 'w:',[sum(leaves[i].weights) for i in leaves]
    return criteria
    
def split_upper(factory,criteria,returnIndices = False,equalizeWeights = False,normalizeWeights = False,
                       split_weights = 0.,split_inclusion = 0.):
    """
    I split the data into the leaves of the upper level ODT given it's criterea
    """
    split = {'':factory}
    indices = {'':np.arange(factory.n_events)}
    for criterion in criteria:
        feature,cut,_= criterion
        split_new = {}
        indices_new = {}
        for splt in split:
            dichotomy = split[splt].features[:,feature][:split[splt].n_events]> cut
            split_new[splt+'1'],split_new[splt+'0'] = split[splt].split_by(dichotomy,split_weights,split_inclusion)
            if returnIndices:
                indices_new[splt+'1'] = indices[splt][dichotomy]
                indices_new[splt+'0'] = indices[splt][dichotomy == False]
        split = split_new
        indices = indices_new
    if equalizeWeights:
        for splt in split:
            split[splt].equalizeWeights()
    if normalizeWeights:
        for splt in split:
            split[splt].normalizeWeights()
        
    return ((split, indices ) if returnIndices else split)

def train_splitted_boosts( trees,
                           factory,
                           criteria,
                           loss,
                           learning_rate,
                           breadth,
                           nTrees_leaf,
                           trees_sample_size,
                           wheel_up_times = 0,
                           wheel_learning_rate = None,
                           wheel_learning_rate_decay = None,
                           wheel_nTrees_leaf = None,
                           wheel_sample_increase = None,
                           wheel_regularizer = None,
                           wheel_randomize = True,
                           verbose = True,
                           learning_rate_decay = 1.,
                           trees_sample_increase = 0,
                           regularizer = 0.,
                           weights_outside_leaf = 0.,
                           inclusion_outside_leaf = 0.,
                           use_joblib = False,
                           n_jobs = -1):
    """
    make greedy prune for every leaf in split. I know i should be with kwargs
    """
    factories = split_upper(factory,criteria,
                                   split_weights = weights_outside_leaf,
                                   split_inclusion= inclusion_outside_leaf)

    if wheel_learning_rate == None:
        wheel_learning_rate = learning_rate
    if wheel_learning_rate_decay == None:
        wheel_learning_rate_decay = learning_rate_decay
    if wheel_nTrees_leaf ==None:
        wheel_nTrees_leaf = nTrees_leaf
    if wheel_sample_increase == None:
        wheel_sample_increase = trees_sample_increase
    if wheel_regularizer == None:
        wheel_regularizer = regularizer
    
    
        
    leaves = factories.keys()
    if not use_joblib:
        classis = []
        itr = 1
        for leaf in leaves:
            if verbose:
                print "\n\nNow training leaf ",leaf, itr,"/",len(leaves)
                print "n_ samples at leaf = ", factories[leaf].n_events
                itr +=1
            classi = greed_up_features_bfs(
                               trees,
                               factories[leaf],
                               loss,
                               learning_rate,
                               breadth,
                               nTrees_leaf,
                               trees_sample_size,
                               verbose,
                               learning_rate_decay,
                               trees_sample_increase,
                               regularizer
                               )
            if wheel_up_times != 0:
                if verbose:
                    print "fortune-wheeling the trees"
                classi = wheel_up_features_bfs (classi,
                               trees,
                               factories[leaf],
                               loss,
                               wheel_learning_rate,
                               wheel_up_times,
                               wheel_nTrees_leaf,
                               verbose,
                               wheel_learning_rate_decay,
                               wheel_sample_increase,
                               wheel_regularizer,
                               random_walk = wheel_randomize)
            classis.append(classi)
    else: #use joblib
        tasks = [joblib.delayed(greed_up_features_bfs)(
                               trees,
                               factories[leaf],
                               loss,
                               learning_rate,
                               breadth,
                               nTrees_leaf,
                               trees_sample_size,
                               False,
                               learning_rate_decay,
                               trees_sample_increase,
                               regularizer
                               )for leaf in leaves]
        classis = joblib.Parallel(n_jobs = n_jobs,
                                  backend = "threading",
                                  verbose=verbose)(tasks)
        if wheel_up_times != 0:
            if verbose:
                print "fortune-wheeling the trees"
            tasks = [joblib.delayed(wheel_up_features_bfs)(
                                   classis[i],
                                   trees,
                                   factories[leaves[i]],
                                   loss,
                                   wheel_learning_rate,
                                   wheel_up_times,
                                   wheel_nTrees_leaf,
                                   False,
                                   wheel_learning_rate_decay,
                                   wheel_sample_increase,
                                   wheel_regularizer,
                                   random_walk = wheel_randomize
                                   )for i in range(len(leaves))]
            classis = joblib.Parallel(n_jobs = n_jobs,
                                      backend = "threading",
                                      verbose=verbose)(tasks)

    return {leaves[i]:classis[i] for i in range(len(leaves))}

def predict_splitted(factory,criteria,trees):
    """predict with a splitted trees boost"""
    factories, indices =  split_upper(factory,criteria,True)
    y_pred = np.zeros(factory.n_events)
    for leaf in factories.keys():
        y_pred[indices[leaf]] = factories[leaf].predict(trees[leaf])
    return y_pred
    