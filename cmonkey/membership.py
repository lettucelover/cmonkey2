# vi: sw=4 ts=4 et:
"""membership.py - cMonkey cluster membership functionality
This module captures the microarray-specific scoring component
of cMonkey.

This file is part of cMonkey Python. Please see README and LICENSE for
more information and licensing details.
"""
import datamatrix as dm
import math
import util
import random
import logging
import sys
import numpy as np
import rpy2.robjects as robjects
import multiprocessing as mp
import cPickle
import array


# Default values for membership creation
MAX_ADJUST_TRIES = 50

KEY_NUM_CLUSTERS = 'num_clusters'
KEY_CLUSTERS_PER_ROW = 'memb.clusters_per_row'
KEY_CLUSTERS_PER_COL = 'memb.clusters_per_col'
KEY_PROB_ROW_CHANGE = 'memb.prob_row_change'
KEY_PROB_COL_CHANGE = 'memb.prob_col_change'
KEY_MAX_CHANGES_PER_ROW = 'memb.max_changes_per_row'
KEY_MAX_CHANGES_PER_COL = 'memb.max_changes_per_col'
KEY_MIN_CLUSTER_ROWS_ALLOWED = 'memb.min_cluster_rows_allowed'
KEY_MAX_CLUSTER_ROWS_ALLOWED = 'memb.max_cluster_rows_allowed'

# These keys are for save points
KEY_ROW_IS_MEMBER_OF = 'memb.row_is_member_of'
KEY_COL_IS_MEMBER_OF = 'memb.col_is_member_of'


class ClusterMembership:
    """A class to store row and column memberships of an input matrix
    1. Row memberships are stored as a matrix where each row represents a gene
    in the input and num_clusters_per_row columns.
    2. Column memberships are stored as a matrix of |input genes| rows and
       num_clusters_per_column columns columns
    When creating a ClusterMembership, a row membership seed function is
    called to generate the first column of cluster memberships
    This function is of the type
    DataMatrix => [int]
    A column seed function is called after this, which generates the
    entire column membership matrix.
    """
    def __init__(self, row_is_member_of, column_is_member_of,
                 config_params):
        """creates an instance of ClusterMembership"""

        def create_cluster_to_names_map(name_to_cluster_map):
            """from a name->cluster-list dictionary, create a cluster->name
            list dictionary"""
            result = {}
            for name, clusters in name_to_cluster_map.items():
                for cluster in clusters:
                    if cluster not in result:
                        result[cluster] = set()
                    result[cluster].add(name)
            return result
        # converting to set for efficiency in membership tests
        self.__config_params = config_params
        self.__row_is_member_of = {row: set(clusters)
                                   for row, clusters in row_is_member_of.items()}
        self.__column_is_member_of = {col: set(clusters)
                                      for col, clusters in column_is_member_of.items()}
        self.__cluster_row_members = create_cluster_to_names_map(
            self.__row_is_member_of)
        self.__cluster_column_members = create_cluster_to_names_map(
            self.__column_is_member_of)

    # pylint: disable-msg=R0913
    @classmethod
    def create(cls, data_matrix,
               seed_row_memberships,
               seed_column_memberships,
               config_params):
        """create instance of ClusterMembership using
        the provided seeding algorithms"""
        def make_member_map(membership, names):
            """using a membership array, build a dictionary representing
            the contained memberships for a name"""
            result = {}
            for row_index in xrange(len(names)):
                row = membership[row_index]
                result[names[row_index]] = set(
                    [row[col_index] for col_index in xrange(len(row))
                     if row[col_index] > 0])
            return result

        # using the seeding functions, build the initial membership
        # dictionaries
        num_clusters_per_row = config_params[KEY_CLUSTERS_PER_ROW]
        num_clusters = config_params[KEY_NUM_CLUSTERS]
        num_clusters_per_col = config_params[KEY_CLUSTERS_PER_COL]

        num_rows = data_matrix.num_rows
        row_membership = [[0 for _ in xrange(num_clusters_per_row)]
                          for _ in xrange(num_rows)]
        seed_row_memberships(row_membership, data_matrix)
        column_membership = seed_column_memberships(
            data_matrix, row_membership, num_clusters, num_clusters_per_col)
        row_is_member_of = make_member_map(row_membership,
                                           data_matrix.row_names)
        col_is_member_of = make_member_map(column_membership,
                                           data_matrix.column_names)
        return ClusterMembership(row_is_member_of, col_is_member_of,
                                 config_params)

    def num_clusters(self):
        """returns the number of clusters"""
        return self.__config_params[KEY_NUM_CLUSTERS]

    def num_clusters_per_row(self):
        """returns the number of clusters per row"""
        return self.__config_params[KEY_CLUSTERS_PER_ROW]

    def num_clusters_per_column(self):
        """returns the number of clusters per row"""
        return self.__config_params[KEY_CLUSTERS_PER_COL]

    def probability_seeing_row_change(self):
        """returns the probability for seeing a row change"""
        return self.__config_params[KEY_PROB_ROW_CHANGE]

    def probability_seeing_col_change(self):
        """returns the probability for seeing a row change"""
        return self.__config_params[KEY_PROB_COL_CHANGE]

    def max_changes_per_row(self):
        """returns the maximum number of changes per row"""
        return self.__config_params[KEY_MAX_CHANGES_PER_ROW]

    def max_changes_per_col(self):
        """returns the maximum number of changes per column"""
        return self.__config_params[KEY_MAX_CHANGES_PER_COL]

    def min_cluster_rows_allowed(self):
        """returns the minimum number of rows that should be in a cluster"""
        return self.__config_params[KEY_MIN_CLUSTER_ROWS_ALLOWED]

    def max_cluster_rows_allowed(self):
        """returns the maximum number of rows that should be in a cluster"""
        return self.__config_params[KEY_MAX_CLUSTER_ROWS_ALLOWED]

    def min_cluster_columns_allowed(self):
        """returns the minimum number of columns that should be in a cluster"""
        return 0

    def clusters_for_row(self, row_name):
        """determine the clusters for the specified row"""
        return self.__row_is_member_of.get(row_name, set())

    def num_clusters_for_row(self, row_name):
        """returns the number of clusters for the row"""
        return len(self.clusters_for_row(row_name))

    def clusters_for_column(self, column_name):
        """determine the clusters for the specified column"""
        return self.__column_is_member_of.get(column_name, set())

    def num_clusters_for_column(self, column_name):
        """returns the number of clusters for the column"""
        return len(self.clusters_for_column(column_name))

    def rows_for_cluster(self, cluster):
        """returns the rows contained in a cluster"""
        return self.__cluster_row_members.get(cluster, set())

    def columns_for_cluster(self, cluster):
        """returns the columns contained in a cluster"""
        return self.__cluster_column_members.get(cluster, set())

    def num_row_members(self, cluster):
        """returns the number of row members in the specified cluster"""
        return len(self.__cluster_row_members.get(cluster, set()))

    def num_column_members(self, cluster):
        """returns the number of row members in the specified cluster"""
        return len(self.__cluster_column_members.get(cluster, set()))

    def clusters_not_in_row(self, row, clusters):
        """returns the clusters in the input that are not in column,
        preserving the order of clusters"""
        return [cluster for cluster in clusters
                if cluster not in self.__row_is_member_of[row]]

    def clusters_not_in_column(self, column, clusters):
        """returns the clusters in the input that are not in column"""
        return [cluster for cluster in clusters
                if cluster not in self.__column_is_member_of[column]]

    def is_row_in_cluster(self, row, cluster):
        """returns true if the specified row is in all spefied clusters"""
        return row in self.rows_for_cluster(cluster)

    def is_column_in_cluster(self, col, cluster):
        """returns true if the specified row is in all spefied clusters"""
        return col in self.columns_for_cluster(cluster)

    def add_cluster_to_row(self, row, cluster):
        """checked adding of a row to a cluster"""
        if self.num_clusters_for_row(row) >= self.num_clusters_per_row():
            raise Exception(("add_row_to_cluster() - exceeded clusters/row " +
                            "limit for row: '%s'" % str(row)))
        self.__add_cluster_to_row(row, cluster)

    def __add_cluster_to_row(self, row, cluster):
        """adds the specified row as a member to the cluster. Unchecked
        version, without checking limits"""
        if not row in self.__row_is_member_of:
            self.__row_is_member_of[row] = set()
        if not cluster in self.__cluster_row_members:
            self.__cluster_row_members[cluster] = set()

        clusters = self.__row_is_member_of[row]
        rows = self.__cluster_row_members[cluster]
        if cluster not in clusters:
            clusters.add(cluster)
        if row not in rows:
            rows.add(row)

    def remove_cluster_from_row(self, row, cluster):
        """removes a cluster from the list of associated clusters for a row"""
        if row in self.__row_is_member_of:
            clusters = self.__row_is_member_of[row]
            clusters.remove(cluster)

        if cluster in self.__cluster_row_members:
            rows = self.__cluster_row_members[cluster]
            rows.remove(row)

    def replace_row_cluster(self, row, cluster, replacement):
        """replaces a cluster in the list of clusters for a row"""
        if cluster != replacement and not self.is_row_in_cluster(row, replacement):
            self.remove_cluster_from_row(row, cluster)
            self.add_cluster_to_row(row, replacement)

    def add_cluster_to_column(self, column, cluster):
        """checked adding of a column to a cluster"""
        if (self.num_clusters_for_column(column) >=
            self.num_clusters_per_column()):
            raise Exception(("add_col_to_cluster() - exceeded clusters/col " +
                            "limit for col: '%s'" % str(column)))
        self.__add_cluster_to_column(column, cluster)

    def __add_cluster_to_column(self, column, cluster):
        """unchecked adding of a column to a cluster"""
        if not column in self.__column_is_member_of:
            self.__column_is_member_of[column] = set()
        if not cluster in self.__cluster_column_members:
            self.__cluster_column_members[cluster] = set()

        clusters = self.__column_is_member_of[column]
        columns = self.__cluster_column_members[cluster]
        if cluster not in clusters:
            clusters.add(cluster)
        if column not in columns:
            columns.add(column)

    def remove_cluster_from_column(self, column, cluster):
        """removes a cluster from the list of associated clusters
        for a column"""
        if cluster in self.__cluster_column_members:
            columns = self.__cluster_column_members[cluster]
            columns.remove(column)

        if column in self.__column_is_member_of:
            clusters = self.__column_is_member_of[column]
            clusters.remove(cluster)

    def replace_column_cluster(self, column, cluster, replacement):
        """replaces a cluster in the list of clusters for a column"""
        if replacement != cluster and not self.is_column_in_cluster(column, replacement):
            self.remove_cluster_from_column(column, cluster)
            self.add_cluster_to_column(column, replacement)

    def __repr__(self):
        """returns the string representation of memberships"""
        result = "ROW MEMBERS:\n"
        result += repr(self.__cluster_row_members)
        result += "\n\nCOLUMN MEMBERS:\n"
        result += repr(self.__cluster_column_members)
        return result

    def pickle_path(self):
        """returns the function-specific pickle-path"""
        return '%s/last_row_scores.pkl' % (self.__config_params['output_dir'])

    def update(self, matrix, row_scores, column_scores,
               num_iterations, iteration_result, add_fuzz=True):
        """top-level update method"""
        if add_fuzz:
            start = util.current_millis()
            row_scores, column_scores = fuzzify(self, row_scores,
                                                column_scores,
                                                num_iterations,
                                                iteration_result)
            elapsed = util.current_millis() - start
            logging.info("fuzzify took %f s.", elapsed / 1000.0)

        # pickle the (potentially fuzzed) row scores to use them
        # in the post adjustment step. We only need to do that in the last
        # iteration
        iteration = iteration_result['iteration']
        if iteration == num_iterations:
            with open(self.pickle_path(), 'w') as outfile:
                cPickle.dump(row_scores, outfile)

        #rpc = map(len, self.__cluster_row_members.values())
        #logging.info('Rows per cluster: %i to %i (median %d)' \
        #  %( min(rpc), max(rpc), np.median(rpc) ) )

        start = util.current_millis()
        rd_scores, cd_scores = get_density_scores(self, row_scores,
                                                  column_scores)
        elapsed = util.current_millis() - start
        logging.info("GET_DENSITY_SCORES() took %f s.", elapsed / 1000.0)

        start = util.current_millis()
        compensate_size(self, matrix, rd_scores, cd_scores)
        elapsed = util.current_millis() - start
        logging.info("COMPENSATE_SIZE() took %f s.", elapsed / 1000.0)

        start_time = util.current_millis()
        update_for_rows(self, rd_scores, self.__config_params['multiprocessing'])
        elapsed = util.current_millis() - start_time
        logging.info("update_for rdscores finished in %f s.", elapsed / 1000.0)

        start_time = util.current_millis()
        update_for_cols(self, cd_scores, self.__config_params['multiprocessing'])
        elapsed = util.current_millis() - start_time
        logging.info("update_for cdscores finished in %f s.", elapsed / 1000.0)

    def replace_delta_row_member(self, row, cluster, rd_scores,
                                 check_zero_size=False):
        index = rd_scores.row_indexes([row])[0]
        rds_values = rd_scores.values
        current_clusters = self.__row_is_member_of[row]
        compval = rds_values[index][cluster - 1]
        
        deltas = sorted([(compval - rds_values[index][c - 1], c) for c in current_clusters],
                        reverse=True)
        if len(deltas) > 0 and deltas[0][0] > 0:
            self.replace_row_cluster(row, deltas[0][1], cluster)
            return deltas[0][1]
        return 0

    def replace_delta_column_member(self, col, cluster, cd_scores):
        index = cd_scores.row_indexes([col])[0]
        cds_values = cd_scores.values
        current_clusters = self.__column_is_member_of[col]
        compval = cds_values[index][cluster - 1]
        
        deltas = sorted([(compval - cds_values[index][c - 1], c) for c in current_clusters],
                        reverse=True)
        if len(deltas) > 0 and deltas[0][0] > 0:
            self.replace_column_cluster(col, deltas[0][1], cluster)
            return deltas[0][1]
        return 0


    def postadjust(self, rowscores=None, cutoff=0.33, limit=100):
        """adjusting the cluster memberships after the main iterations have been done
        Returns true if the function changed the membership, false if not"""
        if rowscores == None:
            # load the row scores from the last iteration from the pickle file
            with open(self.pickle_path()) as infile:
                rowscores = cPickle.load(infile)

        has_changed = False
        assign_list = []
        for cluster in range(1, self.num_clusters() + 1):
            assign = self.adjust_cluster(cluster, rowscores, cutoff, limit)
            assign_list.append(assign)

        for assign in assign_list:
            if len(assign) > 0:
                has_changed = True
            for row, cluster in assign.items():
                self.__add_cluster_to_row(row, cluster)
        return has_changed

    def adjust_cluster(self, cluster, rowscores, cutoff, limit):
        """adjust a single cluster"""
        def max_row_in_column(matrix, column):
            """returns a pair of the maximum row index and score in the given matrix and column"""
            sm = matrix.submatrix_by_name(wh, [matrix.column_names[column]])
            sm_values = sm.values
            max_row = 0
            max_score = sys.float_info.min
            for row in range(sm.num_rows):
                if sm_values[row][0] > max_score:
                    max_score = sm_values[row][0]
                    max_row = row
            return sm.row_names[max_row]

        old_rows = self.rows_for_cluster(cluster)
        not_in = []
        for row in range(rowscores.num_rows):
            row_name = rowscores.row_names[row]
            if row_name not in old_rows:
                not_in.append((row, rowscores.row_names[row]))
        #print old_rows
        threshold = rowscores.submatrix_by_name(old_rows,
                                                [rowscores.column_names[cluster - 1]]).quantile(cutoff)
        wh = []
        rs_values = rowscores.values
        for row, row_name in not_in:
            if rs_values[row][cluster - 1] < threshold:
                #print "Appending %s with score: %f" % (row_name, rowscores[row][cluster - 1])
                wh.append(row_name)
        #print "THRESHOLD: ", threshold
        #print "WH: ", wh
        if len(wh) == 0:
            return {} # return unmodified row membership
        elif len(wh) > limit:
            return {} # return unmodified row membership
 
        tries = 0
        result = {}
        while len(wh) > 0 and tries < MAX_ADJUST_TRIES:
            wh2 = max_row_in_column(rowscores, cluster - 1)
            wh2_index = rowscores.row_names.index(wh2)
            clusters = self.clusters_for_row(wh2)
            wh2_scores = []
            for c in clusters:
                wh2_scores.append(rs_values[wh2_index][c - 1])
            #print "WH2: ", wh2, " CLUSTERS: ", clusters, " WH2_SCORES: ", wh2_scores
            result[wh2] = cluster
            wh.remove(wh2)
            tries += 1
        old_num = len(self.rows_for_cluster(cluster))
        logging.info("CLUSTER %d, # ROWS BEFORE: %d, AFTER: %d",
                     cluster, old_num, old_num + len(result))
        return result

    def store_checkpoint_data(self, shelf):
        """Save memberships into checkpoint"""
        logging.info("Saving checkpoint data for memberships in iteration %d",
                     shelf['iteration'])
        shelf[KEY_ROW_IS_MEMBER_OF] = self.__row_is_member_of
        shelf[KEY_COL_IS_MEMBER_OF] = self.__column_is_member_of

    @classmethod
    def restore_from_checkpoint(cls, config_params, shelf):
        """Restore memberships from checkpoint information"""
        logging.info("Restoring cluster memberships from checkpoint data")
        row_is_member_of = shelf[KEY_ROW_IS_MEMBER_OF]
        col_is_member_of = shelf[KEY_COL_IS_MEMBER_OF]
        return cls(row_is_member_of, col_is_member_of, config_params)

##################################################################################
####
#### Original membership class
####
##################################################################################

class OrigMembership:
    """This is an implementation of a membership data structure that more
    closely resembles the R original. It is much simpler than
    ClusterMembership, with a smaller memory footprint"""
    def __init__(self, row_is_member_of, col_is_member_of,
                 config_params):
        """identical constructor to ClusterMembership"""

        def cluster2names_map(name2clusters):
            result = {}
            for name, clusters in name2clusters.items():
                for cluster in clusters:
                    if cluster > 0:
                        if cluster not in result:
                            result[cluster] = set()
                        result[cluster].add(name)
            return result
            
        self.__config_params = config_params

        # table with |genes| rows and the configured number of columns
        num_per_row = config_params['memb.clusters_per_row']
        num_per_col = config_params['memb.clusters_per_col']

        self.row_memb = {}
        self.col_memb = {}
        for row, clusters in row_is_member_of.items():
            tmp = row_is_member_of[row][:num_per_row]
            tmp.extend([0] * (num_per_row - len(tmp)))
            self.row_memb[row] = array.array('i', tmp)

        for col, clusters in col_is_member_of.items():
            tmp = col_is_member_of[col][:num_per_col]
            tmp.extend([0] * (num_per_col - len(tmp)))
            self.col_memb[col] = array.array('i', tmp)

        # without these maps, updating will be super-slow
        self.cluster_rows = cluster2names_map(self.row_memb)
        self.cluster_cols = cluster2names_map(self.col_memb)

    # pylint: disable-msg=R0913
    @classmethod
    def create(cls, matrix,
               seed_row_memberships,
               seed_column_memberships,
               config_params):
        """create instance of ClusterMembership using
        the provided seeding algorithms"""
        def make_member_map(membs, names):
            """build a map row->[clusters]"""
            result = {}
            for i in xrange(len(names)):
                result[names[i]] = [c for c in membs[i] if c > 0]
            return result

        # using the seeding functions, build the initial membership
        # dictionaries
        num_clusters_per_row = config_params[KEY_CLUSTERS_PER_ROW]
        num_clusters = config_params[KEY_NUM_CLUSTERS]
        num_clusters_per_col = config_params[KEY_CLUSTERS_PER_COL]

        num_rows = matrix.num_rows
        row_membership = [[0 for _ in xrange(num_clusters_per_row)]
                          for _ in xrange(num_rows)]
        seed_row_memberships(row_membership, matrix)
        column_membership = seed_column_memberships(matrix, row_membership,
                                                    num_clusters, num_clusters_per_col)
        row_is_member_of = make_member_map(row_membership, matrix.row_names)
        col_is_member_of = make_member_map(column_membership, matrix.column_names)
        return OrigMembership(row_is_member_of, col_is_member_of,
                              config_params)

    def num_clusters(self):
        """returns the number of clusters"""
        return self.__config_params[KEY_NUM_CLUSTERS]

    def num_clusters_per_row(self):
        """returns the number of clusters per row"""
        return self.__config_params[KEY_CLUSTERS_PER_ROW]

    def num_clusters_per_column(self):
        """returns the number of clusters per row"""
        return self.__config_params[KEY_CLUSTERS_PER_COL]

    def probability_seeing_row_change(self):
        """returns the probability for seeing a row change"""
        return self.__config_params[KEY_PROB_ROW_CHANGE]

    def probability_seeing_col_change(self):
        """returns the probability for seeing a row change"""
        return self.__config_params[KEY_PROB_COL_CHANGE]

    def max_changes_per_row(self):
        """returns the maximum number of changes per row"""
        return self.__config_params[KEY_MAX_CHANGES_PER_ROW]

    def max_changes_per_col(self):
        """returns the maximum number of changes per column"""
        return self.__config_params[KEY_MAX_CHANGES_PER_COL]

    def min_cluster_rows_allowed(self):
        """returns the minimum number of rows that should be in a cluster"""
        return self.__config_params[KEY_MIN_CLUSTER_ROWS_ALLOWED]

    def max_cluster_rows_allowed(self):
        """returns the maximum number of rows that should be in a cluster"""
        return self.__config_params[KEY_MAX_CLUSTER_ROWS_ALLOWED]

    def min_cluster_columns_allowed(self):
        """returns the minimum number of columns that should be in a cluster"""
        return 0

    def clusters_for_row(self, row_name):
        """determine the clusters for the specified row"""
        return {m for m in self.row_memb[row_name] if m > 0}

    def num_clusters_for_row(self, row):
        """returns the number of clusters for the row"""
        return len(self.clusters_for_row(row))

    def clusters_for_column(self, column_name):
        """determine the clusters for the specified column"""
        return {m for m in self.col_memb[column_name] if m > 0}

    def num_clusters_for_column(self, column):
        """returns the number of clusters for the column"""
        return len(self.clusters_for_column(column))

    def rows_for_cluster(self, cluster):
        return self.cluster_rows.get(cluster, set())

    def columns_for_cluster(self, cluster):
        return self.cluster_cols.get(cluster, set())

    def num_row_members(self, cluster):
        return len(self.rows_for_cluster(cluster))

    def num_column_members(self, cluster):
        return len(self.columns_for_cluster(cluster))

    def clusters_not_in_row(self, row, clusters):
        return [cluster for cluster in clusters
                if cluster not in self.clusters_for_row(row)]

    def clusters_not_in_column(self, col, clusters):
        return [cluster for cluster in clusters
                if cluster not in self.clusters_for_column(col)]

    def is_row_in_cluster(self, row, cluster):
        return cluster in self.clusters_for_row(row)

    def is_column_in_cluster(self, col, cluster):
        return cluster in self.clusters_for_column(col)

    def first_free_slot_for_row(self, row):
        return self.row_memb[row].index(0)

    def first_free_slot_for_column(self, col):
        return self.col_memb[col].index(0)

    def add_cluster_to_row(self, row, cluster, force=False):
        def add_reverse(cluster, row):
            if cluster not in self.cluster_rows:
                self.cluster_rows[cluster] = {row}
            else:
                self.cluster_rows[cluster].add(row)

        try:
            index = self.row_memb[row].index(0)
            self.row_memb[row][index] = cluster
            add_reverse(cluster, row)
        except:
            if not force:
                raise Exception(("add_cluster_to_row() - exceeded clusters/row " +
                                 "limit for row: '%s'" % str(row)))
            else:
                self.row_memb[row].append(cluster)
                add_reverse(cluster, row)

    def add_cluster_to_column(self, col, cluster, force=False):
        def add_reverse(cluster, col):
            if cluster not in self.cluster_cols:
                self.cluster_cols[cluster] = {col}
            else:
                self.cluster_cols[cluster].add(col)
            
        try:
            index = self.col_memb[col].index(0)
            self.col_memb[col][index] = cluster
            add_reverse(cluster, col)
        except:
            if not force:
                raise Exception(("add_cluster_to_column() - exceeded clusters/col " +
                                 "limit for column: '%s'" % str(col)))
            else:
                self.col_memb[col].append(cluster)
                add_reverse(cluster, col)

    def replace_row_cluster(self, row, index, new):
        if new not in self.clusters_for_row(row):
            old = self.row_memb[row][index]
            self.row_memb[row][index] = new

            # add reverse edge
            # check whether old is still member of this row
            if old not in self.row_memb[row]:
                self.cluster_rows[old].remove(row)
            if new not in self.cluster_rows:
                self.cluster_rows[new] = set()
            self.cluster_rows[new].add(row)


    def replace_column_cluster(self, col, old, new):
        index = self.col_memb[col].index(old)
        self.col_memb[col][index] = new

        # check whether old is still member of this row
        if old not in self.col_memb[col]:
            self.cluster_cols[old].remove(col)
        if new not in self.cluster_cols:
            self.cluster_cols[new] = set()
        self.cluster_cols[new].add(col)


    def pickle_path(self):
        """returns the function-specific pickle-path"""
        return '%s/last_row_scores.pkl' % (self.__config_params['output_dir'])

    def update(self, matrix, row_scores, column_scores,
               num_iterations, iteration_result, add_fuzz=True):
        """top-level update method"""
        if add_fuzz:
            start = util.current_millis()
            row_scores, column_scores = fuzzify(self, row_scores, column_scores,
                                                num_iterations, iteration_result)
            elapsed = util.current_millis() - start
            logging.info("fuzzify took %f s.", elapsed / 1000.0)

        # pickle the (potentially fuzzed) row scores to use them
        # in the post adjustment step. We only need to do that in the last
        # iteration
        iteration = iteration_result['iteration']
        if iteration == num_iterations:
            with open(self.pickle_path(), 'w') as outfile:
                cPickle.dump(row_scores, outfile)

        #rpc = map(len, self.__cluster_row_members.values())
        #logging.info('Rows per cluster: %i to %i (median %d)' \
        #  %( min(rpc), max(rpc), np.median(rpc) ) )

        start = util.current_millis()
        rd_scores, cd_scores = get_density_scores(self, row_scores,
                                                  column_scores)
        elapsed = util.current_millis() - start
        logging.info("GET_DENSITY_SCORES() took %f s.", elapsed / 1000.0)

        start = util.current_millis()
        compensate_size(self, matrix, rd_scores, cd_scores)
        elapsed = util.current_millis() - start
        logging.info("COMPENSATE_SIZE() took %f s.", elapsed / 1000.0)

        start_time = util.current_millis()
        update_for_rows2(self, rd_scores, self.__config_params['multiprocessing'])
        elapsed = util.current_millis() - start_time
        logging.info("update_for rdscores finished in %f s.", elapsed / 1000.0)

        start_time = util.current_millis()
        update_for_cols2(self, cd_scores, self.__config_params['multiprocessing'])
        elapsed = util.current_millis() - start_time
        logging.info("update_for cdscores finished in %f s.", elapsed / 1000.0)

    def store_checkpoint_data(self, shelf):
        """Save memberships into checkpoint"""
        logging.info("Saving checkpoint data for memberships in iteration %d",
                     shelf['iteration'])
        shelf[KEY_ROW_IS_MEMBER_OF] = self.row_memb
        shelf[KEY_COL_IS_MEMBER_OF] = self.col_memb

    @classmethod
    def restore_from_checkpoint(cls, config_params, shelf):
        """Restore memberships from checkpoint information"""
        logging.info("Restoring cluster memberships from checkpoint data")
        row_is_member_of = shelf[KEY_ROW_IS_MEMBER_OF]
        col_is_member_of = shelf[KEY_COL_IS_MEMBER_OF]
        return cls(row_is_member_of, col_is_member_of, config_params)


def update_for_rows2(membership, rd_scores, multiprocessing):
    """generically updating row memberships according to  rd_scores"""
    rownames = rd_scores.row_names
    # note: for rows, the original version sorts the best clusters by cluster number !!!
    best_clusters = get_best_clusters(rd_scores, membership.num_clusters_per_row(), True)
    max_changes = membership.max_changes_per_row()
    change_prob = membership.probability_seeing_row_change()

    """
    with open('cmpy-rm.tsv', 'w') as outfile:
        outfile.write('V1\tV2\n')
        for gene in sorted(best_clusters.keys()):
            clust = best_clusters[gene]
            outfile.write('%s\t%d\t%d\n' % (gene, clust[0], clust[1]))
    """
    for index in xrange(rd_scores.num_rows):
        row = rownames[index]
        clusters = best_clusters[row]

        if seeing_change(change_prob):
            for _ in range(max_changes):
                if len(clusters) > 0:
                    # array.index() throws exception if 0 not in array
                    # using exception handling is idiomatic in Python
                    try:
                        free_slot = membership.first_free_slot_for_row(row)
                        take_cluster = clusters[free_slot]
                        if take_cluster not in membership.clusters_for_row(row):
                            membership.add_cluster_to_row(row, take_cluster)
                    except:
                        replace_delta_row_member2(membership, row, clusters, rd_scores)


def replace_delta_row_member2(membership, row, rm, rd_scores):
    index = rd_scores.row_indexes([row])[0]
    rds_values = rd_scores.values
    curr_indexes = [c - 1 for c in membership.row_memb[row]]
    rm_indexes = [c - 1 for c in rm]    
    deltas = rds_values[index][rm_indexes] - rds_values[index][curr_indexes]
    if len(deltas[deltas != 0.0]) != 0:
        maxidx = deltas.argmax(axis=0)
        membership.replace_row_cluster(row, maxidx, rm[maxidx])


def update_for_cols2(membership, cd_scores, multiprocessing):
    """updating column memberships according to cd_scores"""
    global UPDATE_MEMBERSHIP

    colnames = cd_scores.row_names
    best_clusters = get_best_clusters(cd_scores, membership.num_clusters_per_column())
    max_changes = membership.max_changes_per_col()
    change_prob = membership.probability_seeing_col_change()

    for index in xrange(cd_scores.num_rows):
        col = colnames[index]
        clusters = membership.clusters_not_in_column(col, best_clusters[col])
        if seeing_change(change_prob):
            for c in range(max_changes):
                if len(clusters) > 0:
                    # array.index() throws exception if 0 not in array
                    # using exception handling is idiomatic in Python
                    try:
                        free_slot = membership.first_free_slot_for_column(col)
                        take_cluster = clusters[free_slot]
                        if take_cluster not in membership.clusters_for_column(col):
                            membership.add_cluster_to_column(row, take_cluster)
                    except:
                        old = replace_delta_column_member2(membership, col, clusters[0],
                                                           cd_scores)

def replace_delta_column_member2(membership, col, cluster, cd_scores):
    index = cd_scores.row_indexes([col])[0]
    cds_values = cd_scores.values
    current_clusters = membership.clusters_for_column(col)
    compval = cds_values[index][cluster - 1]

    deltas = sorted([(compval - cds_values[index][c - 1], c) for c in current_clusters],
                    reverse=True)
    if len(deltas) > 0 and deltas[0][0] > 0:
        membership.replace_column_cluster(col, deltas[0][1], cluster)
        return deltas[0][1]
    return 0


def postadjust2(membership, rowscores=None, cutoff=0.33, limit=100):
    """adjusting the cluster memberships after the main iterations have been done
    Returns true if the function changed the membership, false if not"""
    if rowscores == None:
        # load the row scores from the last iteration from the pickle file
        with open(membership.pickle_path()) as infile:
            rowscores = cPickle.load(infile)

    has_changed = False
    assign_list = []
    for cluster in range(1, membership.num_clusters() + 1):
        assign = adjust_cluster2(membership, cluster, rowscores, cutoff, limit)
        assign_list.append(assign)

    for assign in assign_list:
        if len(assign) > 0:
            has_changed = True
        for row, cluster in assign.items():
            membership.add_cluster_to_row(row, cluster, force=True)
    return has_changed


def adjust_cluster2(membership, cluster, rowscores, cutoff, limit):
    """adjust a single cluster"""
    def max_row_in_column(matrix, column):
        """returns a pair of the maximum row index and score in the given matrix and column"""
        sm = matrix.submatrix_by_name(wh, [matrix.column_names[column]])
        sm_values = sm.values
        max_row = 0
        max_score = sys.float_info.min
        for row in range(sm.num_rows):
            if sm_values[row][0] > max_score:
                max_score = sm_values[row][0]
                max_row = row
        return sm.row_names[max_row]

    old_rows = membership.rows_for_cluster(cluster)
    not_in = []
    for row in range(rowscores.num_rows):
        row_name = rowscores.row_names[row]
        if row_name not in old_rows:
            not_in.append((row, rowscores.row_names[row]))
    #print old_rows
    threshold = rowscores.submatrix_by_name(old_rows,
                                            [rowscores.column_names[cluster - 1]]).quantile(cutoff)
    wh = []
    rs_values = rowscores.values
    for row, row_name in not_in:
        if rs_values[row][cluster - 1] < threshold:
            #print "Appending %s with score: %f" % (row_name, rowscores[row][cluster - 1])
            wh.append(row_name)
    #print "THRESHOLD: ", threshold
    #print "WH: ", wh
    if len(wh) == 0:
        return {} # return unmodified row membership
    elif len(wh) > limit:
        return {} # return unmodified row membership

    tries = 0
    result = {}
    while len(wh) > 0 and tries < MAX_ADJUST_TRIES:
        wh2 = max_row_in_column(rowscores, cluster - 1)
        wh2_index = rowscores.row_names.index(wh2)
        clusters = membership.clusters_for_row(wh2)
        wh2_scores = []
        for c in clusters:
            wh2_scores.append(rs_values[wh2_index][c - 1])
        #print "WH2: ", wh2, " CLUSTERS: ", clusters, " WH2_SCORES: ", wh2_scores
        result[wh2] = cluster
        wh.remove(wh2)
        tries += 1
    old_num = len(membership.rows_for_cluster(cluster))
    logging.info("CLUSTER %d, # ROWS BEFORE: %d, AFTER: %d",
                 cluster, old_num, old_num + len(result))
    return result

######################################################################
### Helpers
######################################################################

# Parallelized updating of row and column membership changes
UPDATE_MEMBERSHIP = None

def update_for_rows(membership, rd_scores, multiprocessing):
    """generically updating row memberships according to  rd_scores"""
    rownames = rd_scores.row_names    
    best_clusters = get_best_clusters(rd_scores, membership.num_clusters_per_row())
    max_changes = membership.max_changes_per_row()
    change_prob = membership.probability_seeing_row_change()
    for index in xrange(rd_scores.num_rows):
        row = rownames[index]
        clusters = membership.clusters_not_in_row(row, best_clusters[row])
        if seeing_change(change_prob):
            for _ in range(max_changes):
                if len(clusters) > 0:
                    if membership.num_clusters_for_row(row) < membership.num_clusters_per_row():
                        membership.add_cluster_to_row(row, clusters[0])
                        del clusters[0]
                    else:
                        old = membership.replace_delta_row_member(row, clusters[0], rd_scores)
                        if old != 0:
                            del clusters[0]


def update_for_cols(membership, cd_scores, multiprocessing):
    """updating column memberships according to cd_scores"""
    global UPDATE_MEMBERSHIP

    colnames = cd_scores.row_names
    best_clusters = get_best_clusters(cd_scores, membership.num_clusters_per_column())
    max_changes = membership.max_changes_per_col()
    change_prob = membership.probability_seeing_col_change()

    for index in xrange(cd_scores.num_rows):
        col = colnames[index]
        clusters = membership.clusters_not_in_column(col, best_clusters[col])
        if seeing_change(change_prob):
            for c in range(max_changes):
                if len(clusters) > 0:
                    if (membership.num_clusters_for_column(col) <
                        membership.num_clusters_per_column()):
                        membership.add_cluster_to_column(col, clusters[0])
                        del clusters[0]
                    else:
                        old = membership.replace_delta_column_member(col, clusters[0], cd_scores)
                        if old != 0:
                            del clusters[0]


def seeing_change(prob):
    """returns true if the update is seeing the change"""
    return prob >= 1.0 or random.uniform(0.0, 1.0) <= prob


def get_best_clusters(scores, n, sort=False):
    """retrieve the n best scored clusters for the given row/column score matrix"""
    if sort:
        return {scores.row_names[row]: sorted(util.order_fast(scores.row_values(row), n))
                for row in xrange(scores.num_rows)}
    else:
        return {scores.row_names[row]: util.order_fast(scores.row_values(row), n)
                for row in xrange(scores.num_rows)}



def get_row_density_scores(membership, row_scores):
    """getting density scores improves small clusters"""
    num_clusters = membership.num_clusters()
    rscore_range = abs(row_scores.max() - row_scores.min())
    rowscore_bandwidth = max(rscore_range / 100.0, 0.001)
    rd_scores = dm.DataMatrix(row_scores.num_rows,
                              row_scores.num_columns,
                              row_scores.row_names,
                              row_scores.column_names)
    rds_values = rd_scores.values

    start_time = util.current_millis()
    for cluster in xrange(1, num_clusters + 1):
        # instead of assigning the rr_scores values per row, we can assign to the
        # transpose and let numpy do the assignment
        rds_values.T[cluster - 1] = get_rr_scores(membership, row_scores,
                                                  rowscore_bandwidth,
                                                  cluster)

    elapsed = util.current_millis() - start_time
    logging.info("RR_SCORES IN %f s.", elapsed / 1000.0)
    return rd_scores

def get_col_density_scores(membership, col_scores):
    num_clusters = membership.num_clusters()
    cscore_range = abs(col_scores.max() - col_scores.min())
    colscore_bandwidth = max(cscore_range / 100.0, 0.001)
    cd_scores = dm.DataMatrix(col_scores.num_rows,
                              col_scores.num_columns,
                              col_scores.row_names,
                              col_scores.column_names)
    cds_values = cd_scores.values

    start_time = util.current_millis()
    for cluster in xrange(1, num_clusters + 1):
        # instead of assigning the cc_scores values per row, we can assign to the
        # transpose and let numpy do the assignment
        cds_values.T[cluster - 1] = get_cc_scores(membership, col_scores,
                                                  colscore_bandwidth,
                                                  cluster)

    elapsed = util.current_millis() - start_time
    logging.info("CC_SCORES IN %f s.", elapsed / 1000.0)
    return cd_scores

def get_density_scores(membership, row_scores, col_scores):
    return (get_row_density_scores(membership, row_scores),
            get_col_density_scores(membership, col_scores))

def get_rr_scores(membership, rowscores, bandwidth, cluster):
    """calculate the density scores for the given row score values in the
    specified cluster"""
    def bwscale(value):
        """standard bandwidth scaling function for row scores"""
        return math.exp(-value / 10.0) * 10.0

    cluster_rows = membership.rows_for_cluster(cluster)
    cluster_columns = membership.columns_for_cluster(cluster)
    kscores = rowscores.column_values(cluster - 1)
    kscores_finite = kscores[np.isfinite(kscores)]

    if (len(cluster_rows) == 0 or len(kscores_finite) == 0 or
        len(cluster_columns) == 0):
        num_rows = rowscores.num_rows
        return [(1.0 / num_rows) for _ in xrange(num_rows)]
    else:
        score_indexes = rowscores.row_indexes(cluster_rows)
        cluster_scores = [kscores[index] for index in score_indexes]
        cluster_bandwidth = bandwidth * bwscale(len(cluster_rows))
        return util.density(kscores, cluster_scores, cluster_bandwidth,
                            np.amin(kscores_finite) - 1,
                            np.amax(kscores_finite) + 1)


def get_cc_scores(membership, scores, bandwidth, cluster):
    """calculate the density scores for the given column score values in the
    specified cluster"""
    cluster_rows = membership.rows_for_cluster(cluster)
    cluster_columns = membership.columns_for_cluster(cluster)
    kscores = scores.column_values(cluster - 1)
    kscores_finite = kscores[np.isfinite(kscores)]

    if (len(cluster_rows) == 0 or len(kscores_finite) == 0 or
        len(cluster_columns) <= 1):
        # This is a little weird, but is here to at least attempt to simulate
        # what the original cMonkey is doing
        num_rows = scores.num_rows
        return [(1.0 / num_rows) for _ in xrange(num_rows)]
    else:
        score_indexes = scores.row_indexes(cluster_columns)
        cluster_scores = [kscores[index] for index in score_indexes]
        return util.density(kscores, cluster_scores, bandwidth,
                            np.amin(kscores_finite) - 1,
                            np.amax(kscores_finite) + 1)


def compensate_size(membership, matrix, rd_scores, cd_scores):
    """size compensation function"""
    def compensate_dim_size(size, dimsize, clusters_per_dim, num_clusters):
        """compensate size for a dimension"""
        return math.exp(-float(size) / (float(dimsize) *
                                        float(clusters_per_dim) /
                                        float(num_clusters)))

    def compensate_row_size(size):
        """compensation function for row dimension"""
        return compensate_dim_size(size,
                                   matrix.num_rows,
                                   membership.num_clusters_per_row(),
                                   membership.num_clusters())

    def compensate_column_size(size):
        """compensation function for column dimension"""
        return compensate_dim_size(size,
                                   matrix.num_columns,
                                   membership.num_clusters_per_column(),
                                   membership.num_clusters())

    def compensate_rows(cluster):
        """compensate density scores for row dimension"""
        num_rowmembers = membership.num_row_members(cluster)
        rd_scores.multiply_column_by(
            cluster - 1,
            compensate_row_size(max(num_rowmembers,
                                    membership.min_cluster_rows_allowed())))

    def compensate_columns(cluster):
        """compensate density scores for column dimension"""
        num_colmembers = membership.num_column_members(cluster)
        cd_scores.multiply_column_by(
            cluster - 1,
            compensate_column_size(max(num_colmembers,
                                       matrix.num_columns / 10.0)))

    num_clusters = membership.num_clusters()
    for cluster in xrange(1, num_clusters + 1):
        compensate_rows(cluster)
        compensate_columns(cluster)


def std_fuzzy_coefficient(iteration, num_iterations):
    """standard fuzzy coefficient as defined in cMonkey"""
    return 0.7 * math.exp(-(float(iteration) /
                            (float(num_iterations) / 3.0))) + 0.05


def old_fuzzy_coefficient(iteration, num_iterations):
    """standard fuzzy coefficient as defined in cMonkey"""
    return 0.75 * math.exp(-iteration/(num_iterations/4.0))


def make_kmeans_row_seeder(num_clusters):
    """creates a row seeding function based on k-means"""

    def seed(row_membership, matrix):
        """uses k-means seeding to seed row membership"""
        flat_values = [value if not np.isnan(value) else 0
                       for value in matrix.values.flatten()]
        matrix_values = robjects.r.matrix(
            robjects.FloatVector(flat_values), nrow=matrix.num_rows, byrow=True)
        kmeans = robjects.r['kmeans']
        kwargs = {'centers': num_clusters, 'iter.max': 20, 'nstart': 2}
        seeding = kmeans(matrix_values, **kwargs)[0]
        for row in xrange(len(seeding)):
            row_membership[row][0] = seeding[row]

    return seed

def make_file_seeder(filename, sep=' '):
    """uses a TSV file to seed row membership"""
    
    def seed(row_membership, matrix):
        """ignore matrix parameter"""
        row_map = {name: idx
                   for idx, name in enumerate(matrix.row_names)}

        with open(filename) as infile:
            header = infile.readline()
            for line in infile:
                row = line.strip().replace('"', '').split(sep)
                row_index = row_map[row[0]]
                row_membership[row_index][0] = int(row[1])
    
    return seed

def make_file_column_seeder(filename, sep=' '):
    def seed(matrix, row_membership, num_clusters,
             num_clusters_per_column):
        column_map = {name: idx
                      for idx, name in enumerate(matrix.column_names)}
        column_members = [[] for _ in range(len(matrix.column_names))]

        with open(filename) as infile:
            header = infile.readline()
            for line in infile:
                row = line.strip().replace('"', '').split(sep)
                col_index = column_map[row[0]]
                column_members[col_index] = map(int, row[1:])

        return column_members

    return seed


def fuzzify(membership, row_scores, column_scores, num_iterations, iteration_result):
    """Provide an iteration-specific fuzzification"""
    iteration = iteration_result['iteration']
    #logging.info("__fuzzify(), setup...")
    #start_time = util.current_millis()
    #fuzzy_coeff = std_fuzzy_coefficient(iteration, num_iterations)
    fuzzy_coeff = old_fuzzy_coefficient(iteration, num_iterations)
    iteration_result['fuzzy-coeff'] = fuzzy_coeff
    num_row_fuzzy_values = row_scores.num_rows * row_scores.num_columns
    num_col_fuzzy_values = (column_scores.num_rows *
                            column_scores.num_columns)
    row_sd_values = []

    # optimization: unwrap the numpy arrays to access them directly
    row_score_values = row_scores.values
    col_score_values = column_scores.values

    # iterate the row names directly
    row_names = row_scores.row_names
    for col in xrange(row_scores.num_columns):
        cluster_rows = membership.rows_for_cluster(col + 1)
        for row in xrange(row_scores.num_rows):
            if row_names[row] in cluster_rows:
                row_sd_values.append(row_score_values[row][col])

    # Note: If there are no non-NaN values in row_sd_values, row_rnorm
    # will have all NaNs
    row_rnorm = util.sd_rnorm(row_sd_values, num_row_fuzzy_values,
                              fuzzy_coeff)

    col_sd_values = []
    row_names = column_scores.row_names
    for col in xrange(column_scores.num_columns):
        cluster_cols = membership.columns_for_cluster(col + 1)
        for row in xrange(column_scores.num_rows):
            if row_names[row] in cluster_cols:
                col_sd_values.append(col_score_values[row][col])

    # Note: If there are no non-NaN values in col_sd_values, col_rnorm
    # will have all NaNs
    col_rnorm = util.sd_rnorm(col_sd_values, num_col_fuzzy_values,
                              fuzzy_coeff)

    #elapsed = util.current_millis() - start_time
    #logging.info("fuzzify() SETUP finished in %f s.", elapsed / 1000.0)
    #logging.info("fuzzifying scores...")
    #start_time = util.current_millis()

    # add fuzzy values to the row/column scores
    row_score_values += np.array(row_rnorm).reshape(
        row_scores.num_rows, row_scores.num_columns)
    col_score_values += np.array(col_rnorm).reshape(
        column_scores.num_rows, column_scores.num_columns)
    #elapsed = util.current_millis() - start_time
    #logging.info("fuzzify() finished in %f s.", elapsed / 1000.0)
    return row_scores, column_scores
