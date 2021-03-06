import os
import numpy as np
from Bio import Phylo
from collections import defaultdict
from sf_coreTree_json import Metadata
from sf_miscellaneous import write_pickle

class PresenceAbsenceAssociation(object):
    """docstring for Association"""
    def __init__(self, tree, meta_info):
        super(PresenceAbsenceAssociation, self).__init__()
        self.meta_info = meta_info
        if type(tree)==str and os.path.isfile(tree):
            self.tree = Phylo.load(tree_name, 'newick')
        else:
            self.tree = tree

    def set_gain_loss(self, gain_loss):
        clade = 0
        for n in self.tree.find_clades(order='preorder'):
            if n==self.tree.root:
                continue
            n.present = 'present' if gain_loss[clade] in [1, 3] else 'absent'
            n.event = (gain_loss[clade] in [1, 2])
            clade+=1

        rn = self.tree.root
        rn.present = 'present' if np.mean([c.present=='present' for c in rn])>=0.5 else 'absent'
        rn.event = True

    def calc_association(self,meta_column, transform=None, pc=3):
        '''
        calculate the mean value of the phenotype of leaves upstream and down stream
        of each branch in the tree.
        '''
        if transform is None:
            transform = lambda x:x
        for n in self.tree.find_clades(order='postorder'):
            if n.is_terminal():
                n.strain = n.name.split('|')[0]
                n.meta_value = transform(self.meta_info[n.strain][meta_column])
                if not np.isnan(n.meta_value):
                    n.meta_count = 1
                    n.meta_sq_value = n.meta_value*n.meta_value
                else:
                    n.meta_count = 0
                    n.meta_sq_value = np.nan

            else:
                n.meta_count = np.sum([c.meta_count for c in n if c.meta_count and not c.event])
                n.meta_value = np.sum([c.meta_value for c in n if c.meta_count and not c.event])
                n.meta_sq_value = np.sum([c.meta_sq_value for c in n if c.meta_count and not c.event])

        self.averages = {'present':[], 'absent':[]}
        rn = self.tree.root
        if rn.meta_count:
            self.averages[rn.present].append(rn.meta_value/rn.meta_count)
        for n in self.tree.find_clades(order='preorder'):
            if n.event and n.meta_count:
                self.averages[n.present].append(n.meta_value/n.meta_count)

        from scipy.stats import ttest_ind
        return (np.mean(self.averages['present']) - np.mean(self.averages['absent']))*np.sqrt(1.0/(1.0/len(self.averages['present']) + 1.0/len(self.averages['present'])))


class BranchAssociation(object):
    """docstring for Association"""
    def __init__(self, tree, meta_info):
        super(BranchAssociation, self).__init__()
        self.meta_info = meta_info
        if type(tree)==str and os.path.isfile(tree):
            self.tree = Phylo.load(tree_name, 'newick')
        else:
            self.tree = tree


    def calc_up_down_averages(self,meta_column, transform=None, pc=3):
        '''
        calculate the mean value of the phenotype of leaves upstream and down stream
        of each branch in the tree.
        '''
        if transform is None:
            transform = lambda x:x
        for n in self.tree.find_clades(order='postorder'):
            for c in n: c.up=n # add up links for convenience

            if n.is_terminal():
                n.strain = n.name.split('|')[0]
                n.meta_value = transform(self.meta_info[n.strain][meta_column])
                if not np.isnan(n.meta_value):
                    n.meta_count = 1
                    n.meta_sq_value = n.meta_value*n.meta_value
                else:
                    n.meta_count = 0
                    n.meta_sq_value = np.nan

            else:
                n.meta_count = np.sum([c.meta_count for c in n if c.meta_count])
                n.meta_value = np.sum([c.meta_value for c in n if c.meta_count])
                n.meta_sq_value = np.sum([c.meta_sq_value for c in n if c.meta_count])


        root_node = self.tree.root
        n = root_node
        n.meta_derived_average = n.meta_value/n.meta_count
        n.meta_derived_var = n.meta_count/(n.meta_count-1.0)\
                        *(n.meta_sq_value/n.meta_count - n.meta_derived_average**2)
        n.meta_derived_SSEM = n.meta_derived_var/n.meta_count
        pseudo_var = self.tree.root.meta_derived_var

        for n in self.tree.find_clades(order='preorder'):
            if n==root_node:
                continue

            # calculate average and standard deviation of meta data of child nodes
            if n.meta_count==0:
                n.meta_derived_average = np.nan
                n.meta_derived_var = np.nan
                n.meta_derived_SSEM = np.inf
            else:
                n.meta_derived_average = n.meta_value/n.meta_count
                if n.meta_count==1:
                    n.meta_derived_var = np.nan
                    n.meta_derived_SSEM = np.inf
                else:
                    n.meta_derived_var = n.meta_count/(n.meta_count-1.0)\
                                *(n.meta_sq_value/n.meta_count - n.meta_derived_average**2)
                    n.meta_derived_SSEM = (n.meta_derived_var+pc*pseudo_var)/n.meta_count

            # calculate average and standard deviation of meta data of all non child nodes
            n_non_child = root_node.meta_count - n.meta_count
            n.meta_ancestral_average = (root_node.meta_value-n.meta_value)/n_non_child
            n.meta_ancestral_var = n_non_child/(n_non_child-1.0)\
                            *((root_node.meta_sq_value - n.meta_sq_value)/n_non_child
                               - n.meta_ancestral_average**2)
            n.meta_ancestral_SSEM = (n.meta_ancestral_var+pc*pseudo_var)/n_non_child


    def calc_significance(self):
        max_score = 0
        for n in self.tree.find_clades():
            if n==self.tree.root:
                n.z_score=np.nan
            else:
                n.z_score = np.abs(n.meta_derived_average - n.meta_ancestral_average)/\
                        np.sqrt(n.meta_ancestral_SSEM + n.meta_derived_SSEM)

                if (not np.isnan(n.z_score)) and n.z_score>max_score:
                    max_score=n.z_score

        return max_score



def infer_branch_associations(path):
    from sf_geneCluster_align_makeTree import load_sorted_clusters
    from sf_coreTree_json import metadata_load
    metaFile= '%s%s'%(path,'metainfo.tsv')
    data_description = '%s%s'%(path,'meta_tidy.tsv')
    association_dict = defaultdict(dict)
    metadata = Metadata(metaFile, data_description)
    metadata_dict = metadata.to_dict()

    sorted_genelist = load_sorted_clusters(path)
    ## sorted_genelist: [(clusterID, [ count_strains,[memb1,...],count_genes]),...]
    for clusterID, gene in sorted_genelist:
        if gene[-1]==616: # and clusterID=='GC00001136':
            print(clusterID)
            tree = Phylo.read("%s/geneCluster/%s.nwk"%(path, clusterID), 'newick')
            assoc = BranchAssociation(tree, metadata_dict)
            for col, d  in metadata.data_description.iterrows():
                if d['associate']=='yes':
                    #if 'log_scale' in d and d['log_scale']=='yes':
                    t = lambda x:np.log(x)
                    #else:
                    #    t = lambda x:x
                    assoc.calc_up_down_averages(d["meta_category"], transform = t)
                    max_assoc = assoc.calc_significance()
                    association_dict[clusterID][d["meta_category"]] = max_assoc

    write_pickle("%s/branch_association.cpk"%path, association_dict)


def load_gain_loss(path, clusterID):
    with open('%s/geneCluster/%s_patterns.json'%(path, clusterID), 'r') as ifile:
        tmp = ifile.readlines()[-1].strip().split(':')[-1].split('"')[-2]
    return map(int, list(tmp))


def infer_presence_absence_associations(path):
    from sf_geneCluster_align_makeTree import load_sorted_clusters
    from sf_coreTree_json import metadata_load
    metaFile= '%s%s'%(path,'metainfo.tsv')
    data_description = '%s%s'%(path,'meta_tidy.tsv')
    association_dict = defaultdict(dict)
    metadata = Metadata(metaFile, data_description)
    metadata_dict = metadata.to_dict()

    sorted_genelist = load_sorted_clusters(path)
    ## sorted_genelist: [(clusterID, [ count_strains,[memb1,...],count_genes]),...]
    # TODO fix vis
    tree = Phylo.read("%s/vis/strain_tree.nwk"%(path), 'newick')
    assoc = PresenceAbsenceAssociation(tree, metadata_dict)
    for clusterID, gene in sorted_genelist:
        if gene[-1]>10 and gene[-1]<600:
            print(clusterID)
            gl = load_gain_loss(path, clusterID)
            for col, d  in metadata.data_description.iterrows():
                if d['associate']=='yes':
                    #if 'log_scale' in d and d['log_scale']=='yes':
                    t = lambda x:np.log(x)
                    #else:
                    #    t = lambda x:x
                    assoc.set_gain_loss(gl)
                    ttest_result = assoc.calc_association(d["meta_category"], transform = t)
                    association_dict[clusterID][d["meta_category"]] = ttest_result

    write_pickle("%s/presence_absence_association.cpk"%path, association_dict)

