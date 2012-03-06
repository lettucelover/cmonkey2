# vi: sw=4 ts=4 et:
"""microbial_setup.py - cMonkey module for microbe-specific configuration

This file is part of cMonkey Python. Please see README and LICENSE for
more information and licensing details.
"""
import util
import logging
import datamatrix as dm
import microarray
import scoring
import organism as org
import meme
import motif
import network as nw
import microbes_online
import stringdb
import rsat
import membership as memb

CACHE_DIR = 'cache'
STRING_LINKS = 'tps/string_links.tps.tab'
ROW_WEIGHT = 6.0
NUM_ITERATIONS = 2000
NETWORK_SCORE_INTERVAL = 7
MOTIF_SCORE_INTERVAL = 10
#NUM_CLUSTERS = 43
NUM_CLUSTERS = 250
#MAX_CLUSTER_ROWS = 110
MAX_CLUSTER_ROWS = 80

"""these are the default meme iterations ("meme.iters") in the R version"""
MEME_ITERS = range( 600, 1200, 100 ) + \
             range( 1250, 1500, 50 ) + \
             range( 1525, 1800, 25 ) + \
             range( 1810, max( NUM_ITERATIONS, 1820 ) + 10 )

debug = False
#debug = True
if debug:
    NUM_ITERATIONS = 200
    MEME_ITERS = [100,200]
    NETWORK_SCORE_INTERVAL = 50

def meme_iterations(iteration):
    return iteration in MEME_ITERS

def network_iterations(iteration):
    return iteration > 0 and iteration % NETWORK_SCORE_INTERVAL == 0

THESAURUS_FILE = 'tps/tps.synonyms.gz'
PROM_SEQFILE = 'tps/tps.upstream.-350.50.csv'
SEQ_FILENAMES = {'upstream': PROM_SEQFILE}
SEQUENCE_TYPES = ['upstream']
# used to select sequences and MEME
# note that for pre-computed upstream sequences, the distance relative to the start is already implicit in the subsequence.
# Here specify where to look in the subsequence.
SEARCH_DISTANCES = {'upstream': (0, 400)}
# used for background distribution and MAST
SCAN_DISTANCES = {'upstream': (0, 400)}


class CMonkeyConfiguration(scoring.ConfigurationBase):
    """Microbe-specific configuration class"""

    def __init__(self, config_params, checkpoint_file=None):
        """create instance"""
        scoring.ConfigurationBase.__init__(self, config_params,
                                           checkpoint_file)

    @classmethod
    def create(cls, organism_code, matrix_filename,
               checkpoint_file=None):
        """Creates an initialized instance"""
        params = (scoring.ConfigurationBuilder().
                  with_organism(organism_code).
                  with_num_iterations(NUM_ITERATIONS).
                  with_matrix_filenames([matrix_filename]).
                  with_cache_dir(CACHE_DIR).
                  with_num_clusters(NUM_CLUSTERS).
                  with_sequence_types(SEQUENCE_TYPES).
                  with_search_distances(SEARCH_DISTANCES).
                  with_scan_distances(SCAN_DISTANCES).
                  with_num_clusters(NUM_CLUSTERS).
                  with_max_cluster_rows(MAX_CLUSTER_ROWS).
                  build())
        return cls(params, checkpoint_file)

    def read_matrix(self, filename):
        """reads the data matrix from a file"""
        matrix_factory = dm.DataMatrixFactory(
            [dm.nochange_filter, dm.center_scale_filter])
        infile = util.DelimitedFile.read(filename, has_header=True,
                                         quote='\"')
        return matrix_factory.create_from(infile)

    def make_membership(self):
        """returns the seeded membership"""
        #fake_row_membership_seed = util.DelimitedFileMapper(
        #    util.DelimitedFile.read('clusters.tsv', has_header=False), 0, 1)
        return memb.ClusterMembership.create(
            self.matrix().sorted_by_row_name(),
            #fake_seed_row_memberships(fake_row_membership_seed),
            memb.make_kmeans_row_seeder(NUM_CLUSTERS),
            microarray.seed_column_members,
            self.config_params)

    def row_scoring(self):
        """setup the gene-related scoring functions here
        each object in this array supports the method
        compute(organism, membership, matrix) and returns
        a DataMatrix(genes x cluster)
        """
        row_scoring = microarray.RowScoringFunction(
            self.membership(), self.matrix(),
            lambda iteration: ROW_WEIGHT,
            config_params=self.config_params)

        meme_suite = meme.MemeSuite430()
        sequence_filters = [
            motif.unique_filter,
#            motif.get_remove_low_complexity_filter(meme_suite),
            motif.get_remove_atgs_filter(SEARCH_DISTANCES['upstream'])]

        motif_scoring = motif.MemeScoringFunction(
            self.organism(),
            self.membership(),
            self.matrix(),
            meme_suite,
            sequence_filters=sequence_filters,
            pvalue_filter=motif.MinPValueFilter(-20.0),
            weight_func=lambda iteration: 0.0,
            run_in_iteration=meme_iterations,
            config_params=self.config_params)

        network_scoring = nw.ScoringFunction(self.organism(),
                                             self.membership(),
                                             self.matrix(),
                                             network_iterations,
                                             scoring.default_network_iterations,
                                             config_params=self.config_params)

        return scoring.ScoringFunctionCombiner(self.membership(),
                                               [row_scoring, motif_scoring,
                                                network_scoring],
                                               log_subresults=True)

    def make_organism(self):
        """T. pseudonana is eukaryotic and is not represented in RSAT
        therefore it presently must be treated as a GenericOrganism
        with manually-supplied information. Be warned that otherwise, RSAT
        will falsely supply Mycoplasma for unkwown queries and the
        code will run as a 'Microbe,' likely yielding erroneous results."""
#        keggfile = util.DelimitedFile.read(KEGG_FILE_PATH, comment='#')
#        gofile = util.DelimitedFile.read(GO_FILE_PATH)
        nw_factories = [ stringdb.get_network_factory2(STRING_LINKS) ]
        return org.GenericOrganism('tps', THESAURUS_FILE, nw_factories,
                                        seq_filenames=SEQ_FILENAMES,
                                        search_distances=SEARCH_DISTANCES,
                                        scan_distances=SCAN_DISTANCES)

############################################################
#### Replace with real seeding when everything works
############################################################


def fake_seed_row_memberships(fake_mapper):
    """This method sets the memberships according to a seed that was
    created by running the original cMonkey on halo_ratios5.tsv with
    kmeans row seeding. To compromise on its NP complete behavior,
    kmeans does not always return the same clusters. We bake all random
    components of cMonkey for development to make it possible to compare
    results"""
    def compute(row_membership, _):
        """pseudo-seed with fixed numbers"""
        logging.debug("fake_seed_row_memberships")
        index = 0
        for key in sorted(fake_mapper.keys()):
            row_membership[index][0] = int(fake_mapper[key])
            index += 1
    return compute
