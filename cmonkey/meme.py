"""meme.py - cMonkey meme suite integration
These are functions and classes to conveniently call the needed
commands of the MEME suite in order to find motifs

This file is part of cMonkey Python. Please see README and LICENSE for
more information and licensing details.
"""
import subprocess
import tempfile
import logging
import seqtools as st
import os
import util
import re


class MemeSuite:
    """Regard the meme suite as a unit of tools. This helps
    us capturing things like versions, global settings and data
    passing
    These represent the command line tools and currently are specific
    for 4.3.0, in 4.6.1 the interface has changed, later the MemeSuite
    will take a MemeSuiteVersion object to make these changes transparent.

    dust - remove low-complexity regions or sequence repeats
    meme - discover motifs in a set of sequences
    mast - search for a group of motifs in a set of sequences
    """
    def __init__(self, max_width=24, use_revcomp=True):
        """Create MemeSuite instance"""
        self.__max_width = max_width
        self.__use_revcomp = use_revcomp

    def max_width(self):
        """returns the max_width attribute"""
        return self.__max_width

    def remove_low_complexity(self, seqs):
        """send sequences through dust filter, send only those
        to dust that are larger than max_width"""
        def process_with_dust(seqs):
            """data conversion from and to dust tool"""
            dust_tmp_file = None
            with tempfile.NamedTemporaryFile(prefix='dust',
                                             delete=False) as dust_input:
                for feature_id, seq in seqs.items():
                    dust_input.write(">%s\n" % feature_id)
                    dust_input.write("%s\n" % seq[1])
                dust_tmp_file = dust_input.name
                logging.info("DUST input written to: %s", dust_input.name)
            seqpairs = st.read_sequences_from_fasta_string(
                self.dust(dust_tmp_file))
            os.remove(dust_tmp_file)
            result = {}
            for feature_id, seq in seqpairs:
                result[feature_id] = seq
            return result

        seqs_for_dust = {}
        for feature_id, seq in seqs.items():
            if len(seq[1]) > self.__max_width:
                seqs_for_dust[feature_id] = seq
        return process_with_dust(seqs_for_dust)

    def run_meme(self, input_seqs, all_seqs):
        """Runs the meme tool. input_seqs is a dictionary of
        (feature_id : (location, sequence)) that are to be provided as meme
        input, all_seqs is a dictionary that provides all sequences used
        in the cMonkey run, which will be used to compute background
        distribution"""
        def add_if_unique(meme_input_seqs, seq):
            """add the sequence to the list only if it does not exist"""
            if seq not in meme_input_seqs:
                meme_input_seqs.append(seq)

        def make_seqs(seqs):
            """prepare the input sequences for feeding into meme.
            This means only taking the unique sequences and rever"""
            meme_input_seqs = []
            for locseq in seqs.values():
                seq = locseq[1]
                add_if_unique(meme_input_seqs, seq)
                if self.__use_revcomp:
                    add_if_unique(meme_input_seqs, st.revcomp(seq))
            return meme_input_seqs

        def background_seqs():
            """return all sequences to be used for background calculation"""
            return {feature_id: all_seqs[feature_id]
                    for feature_id in all_seqs if feature_id not in input_seqs}

        def make_background_file():
            """create a meme background file and returns its name"""
            bgseqs = background_seqs()
            filename = None
            bgmodel = st.markov_background(make_seqs(bgseqs), 3)
            with tempfile.NamedTemporaryFile(prefix='memebg',
                                             delete=False) as outfile:
                filename = outfile.name
                outfile.write("# %s order Markov background model\n" %
                              util.order2string(len(bgmodel) - 1))
                for order_row in bgmodel:
                    for seq, frequency in order_row.items():
                        outfile.write('%s %10s\n' %
                                      (seq, str(round(frequency, 8))))
            return filename

        def make_sequence_file(seqs):
            """Creates a FASTA file from a dictionary of (feature_id: sequence)
            entries"""
            outseqs = [(feature_id, seqs[feature_id]) for feature_id in seqs]
            filename = None
            with tempfile.NamedTemporaryFile(prefix='memeseqs',
                                             delete=False) as outfile:
                filename = outfile.name
                st.write_sequences_to_fasta_file(outfile, outseqs)
            return filename

        logging.info("run_meme() - # seqs = %d", len(input_seqs))
        logging.info("# all seqs = %d", len(all_seqs))
        bgfile = make_background_file()
        logging.info("created background file in %s", bgfile)
        seqfile = make_sequence_file(input_seqs)
        logging.info("created sequence file in %s", seqfile)
        motif_infos, output = self.meme(seqfile, bgfile)

        # run mast
        meme_outfile = None
        with tempfile.NamedTemporaryFile(prefix='meme.out.',
                                         delete=False) as outfile:
            meme_outfile = outfile.name
            outfile.write(output)
        logging.info('wrote meme output to %s', meme_outfile)

        all_seqs_dict = {feature_id: locseq[1]
                         for feature_id, locseq in all_seqs.items()}
        dbfile = make_sequence_file(all_seqs_dict)
        logging.info('created mast database in %s', dbfile)
        mast_output = self.mast(meme_outfile, dbfile, bgfile)
        #print mast_output

    def dust(self, fasta_file_path):  # pylint: disable-msg=R0201
        """runs the dust command on the specified FASTA file and
        returns a list of sequences. It is assumed that dust has
        a very simple interface: FASTA in, output on stdout"""
        output = subprocess.check_output(['dust', fasta_file_path])
        return output

    # pylint: disable-msg=W0613,R0201
    def meme(self, infile_path, bgfile_path, num_motifs=2,
             pspfile_path=None):
        """Please implement me"""
        logging.error("MemeSuite.meme() - please implement me")

    def mast(self, meme_outfile_path, database_file_path,
             bgfile_path):  # pylint: disable-msg=R0201
        """Please implement me"""
        logging.error("MemeSuite.mast() - please implement me")


class MemeSuite430(MemeSuite):
    """Version 4.3.0 of MEME"""

    def meme(self, infile_path, bgfile_path, num_motifs=2,
             pspfile_path=None):
        """runs the meme command on the specified input file, background file
        and positional priors file. Returns a tuple of
        (list of MemeMotifInfo objects, meme output)
        """
        command = ['meme', infile_path, '-bfile', bgfile_path,
                   '-time', '600', '-dna', '-revcomp',
                   '-maxsize', '9999999', '-nmotifs', str(num_motifs),
                   '-evt', '1e9', '-minw', '6', '-maxw', str(self.max_width()),
                   '-mod',  'zoops', '-nostatus', '-text']

        if pspfile_path:
            command.append(['-psp', pspfile_path])

        logging.info("running: %s", " ".join(command))
        output = subprocess.check_output(command)
        return (read_meme_output(output, num_motifs), output)

    def mast(self, meme_outfile_path, database_file_path,
             bgfile_path):
        """runs the mast command"""
        command = ['mast', meme_outfile_path, '-d', database_file_path,
                   '-bfile', bgfile_path, '-nostatus', '-stdout', '-text',
                   '-brief', '-ev', '99999', '-mev', '99999', '-mt', '0.99',
                   '-seqp', '-remcorr']
        output = subprocess.check_output(command)
        return output


class MemeMotifInfo:
    """Only a motif's info line, the
    probability matrix and the site information is relevant"""
    # pylint: disable-msg=R0913
    def __init__(self, width, num_sites, llr, evalue, sites, pssm):
        """Creates a MemeMotifInfo instance"""
        self.__width = width
        self.__num_sites = num_sites
        self.__llr = llr
        self.__evalue = evalue
        self.__sites = sites
        self.__pssm = pssm

    def width(self):
        """Returns the width"""
        return self.__width

    def num_sites(self):
        """returns the number of sites"""
        return self.__num_sites

    def llr(self):
        """returns the log-likelihood ratio"""
        return self.__llr

    def evalue(self):
        """returns the e value"""
        return self.__evalue

    def sites(self):
        """returns the sites"""
        return self.__sites

    def __repr__(self):
        """returns the string representation"""
        return ("Motif width: %d sites: %d llr: %d e-value: %f" %
         (self.width(), self.num_sites(), self.llr(),
          self.evalue()))


def read_meme_output(output_text, num_motifs):
    """Reads meme output file into a list of MotifInfo objects"""

    def extract_width(infoline):
        """extract the width value from the info line"""
        return int(__extract_regex('width =\s+\d+', infoline))

    def extract_num_sites(infoline):
        """extract the sites value from the info line"""
        return int(__extract_regex('sites =\s+\d+', infoline))

    def extract_llr(infoline):
        """extract the llr value from the info line"""
        return int(__extract_regex('llr =\s+\d+', infoline))

    def extract_evalue(infoline):
        """extract the e-value from the info line"""
        return float(__extract_regex('E-value =\s+\S+', infoline))

    def next_info_line(motif_number, lines):
        """finds the index of the next info line for the specified motif number
        1-based """
        return __next_regex_index('MOTIF\s+' + str(motif_number) + '.*',
                                  0, lines)

    def next_sites_index(start_index, lines):
        """returns the next sites index"""
        return __next_regex_index('[\t]Motif \d+ sites sorted by position ' +
                                  'p-value', start_index, lines)

    def read_sites(start_index, lines):
        """reads the sites"""
        sites_index = next_sites_index(start_index, lines)
        pattern = re.compile("(\S+)\s+([+-])\s+(\d+)\s+(\S+)\s+\S+ (\S+) \S+")
        current_index = sites_index + 4
        line = lines[current_index]
        sites = []
        while not line.startswith('----------------------'):
            match = pattern.match(line)
            sites.append((match.group(1), match.group(2), int(match.group(3)),
                          float(match.group(4)), match.group(5)))
            current_index += 1
            line = lines[current_index]
        return sites

    def read_pssm(start_index, lines):
        """reads the PSSM, in this case it's what is called the probability
        matrix in the meme output"""
        pssm_index = next_pssm_index(start_index, lines)
        current_index = pssm_index + 3
        line = lines[current_index]
        pattern = re.compile("\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)")
        rows = []
        while not line.startswith('----------------------'):
            match = pattern.match(line)
            rows.append([float(match.group(1)), float(match.group(2)),
                         float(match.group(3)), float(match.group(4))])
            current_index += 1
            line = lines[current_index]
        return rows

    def next_pssm_index(start_index, lines):
        """determines the next PSSM start index"""
        return __next_regex_index('[\t]Motif \d+ position-specific ' +
                                  'probability matrix', start_index, lines)

    def read_motif_info(motif_number, lines):
        """Reads the MemeMotifInfo with the specified number from the input"""
        info_line_index = next_info_line(motif_number, lines)
        info_line = lines[info_line_index]
        return MemeMotifInfo(extract_width(info_line),
                             extract_num_sites(info_line),
                             extract_llr(info_line),
                             extract_evalue(info_line),
                             read_sites(info_line_index + 1, lines),
                             read_pssm(info_line_index + 1, lines))

    lines = output_text.split('\n')
    result = []
    for motif_number in range(1, num_motifs + 1):
        result.append(read_motif_info(motif_number, lines))
    return result


def read_mast_output(output_text, genes):
    """Reads out the p-values and e-values and the gene annotations
    from a mast output file"""
    def next_pe_value_line(start_index, lines):
        """Find the next combined p-value and e-value line"""
        return __next_regex_index('.*COMBINED P-VALUE.*',
                                  start_index, lines)

    def read_pe_values(lines):
        """read all combined p-values and e-values"""
        result = []
        current_index = next_pe_value_line(0, lines)
        while current_index != -1:
            gene = lines[current_index - 2].strip()
            line = lines[current_index]
            pvalue = float(__extract_regex('P-VALUE\s+=\s+(\S+)', line))
            evalue = float(__extract_regex('E-VALUE\s+=\s+(\S+)', line))
            result.append((gene, pvalue, evalue))
            current_index = next_pe_value_line(current_index + 1, lines)
        return result

    def read_seqalign_blocks(lines, start_index, seqlen):
        """Read the sequence alignment blocks starting at start_index
        a block has the format:
        1. motif number line (+/- = forward/reverse)
        2. pvalue line
        3. motif sequence line
        4. alignment/match line
        5. gene sequence line
        6. blank line (separator)
        -> Repeat this pattern until the whole database sequence printed

        While the mast output is easily human-readable, it
        is hard to parse programmatically.
        This method does it as follows:
        - read all motif numbers in sequence
        - read all p-values in sequencs
        - the motif number opening brackets are regarded as position markers

        for each block, we only need to keep track in which column the gene
        sequence starts and at which relative position we are
        """
        current_index = start_index
        is_last = False
        motif_nums = []
        pvalues = []
        positions = []
        while not is_last:
            is_last = is_last_block(lines, current_index, seqlen)
            read_block(lines, current_index, motif_nums,
                       pvalues, positions)
            current_index += 6
        return zip(pvalues, positions, motif_nums)

    def is_last_block(lines, index, seqlen):
        """determines whether the specified block is the last one for
        the current gene"""
        seqline = lines[index + 4]
        seqstart_index = int(re.match('(\d+).*', seqline).group(1))
        seq_start = re.match('\d+\s+(\S+)', seqline).start(1)
        return (len(seqline) - seq_start) + seqstart_index >= seqlen

    def read_block(lines, index, motif_nums, pvalues, positions):
        """Reads the motif numbers, pvalues and positions from the
        specified block"""
        motif_nums.extend(read_motif_numbers(lines[index]))
        pvalues.extend(read_pvalues(lines[index + 1]))
        positions.extend(read_positions(lines[index], lines[index + 4]))

    def read_motif_numbers(motifnum_line):
        """reads the motif numbers contained in a motif number line"""
        return [int(re.sub('\[|\]', '', motifnum))
                for motifnum in re.split(' +', motifnum_line)
                if len(motifnum.strip()) > 0]

    def read_pvalues(pvalue_line):
        """reads the p-values contained in a p-value line"""
        return [float(pvalue)
                for pvalue in re.split(' +', pvalue_line)
                if len(pvalue.strip()) > 0]

    def read_positions(motifnum_line, seqline):
        """we only need the motif number line and the sequence line
        to retrieve the position"""
        start_index = int(re.match('(\d+).*', seqline).group(1))
        seq_start = re.match('\d+\s+(\S+)', seqline).start(1)
        # offset +1 for compatibility with cMonkey R, don't really
        # know why
        return [(m.start() - seq_start + start_index + 1)
                for m in re.finditer('\[', motifnum_line)]

    def read_annotations(lines, genes):
        """extract annotations"""
        result = {}
        current_index = next_pe_value_line(0, lines)
        while current_index != -1:
            gene = lines[current_index - 2].strip()
            if gene in genes:
                info_line = lines[current_index]
                length = int(__extract_regex('LENGTH\s+=\s+(\d+)', info_line))
                result[gene] = read_seqalign_blocks(lines, current_index + 3,
                                                    length)

            current_index = next_pe_value_line(current_index + 1, lines)
        return result

    lines = output_text.split('\n')
    pe_values = read_pe_values(lines)
    annotations = read_annotations(lines, genes)
    return (pe_values, annotations)


# extraction helpers
def __extract_regex(pattern, infoline):
    """generic info line field extraction based on regex"""
    match = re.search(pattern, infoline)
    return infoline[match.start():match.end()].split('=')[1].strip()


def __next_regex_index(pat, start_index, lines):
    """finds the line index of the first occurrence of the pattern"""
    line_index = start_index
    pattern = re.compile(pat)
    current_line = lines[line_index]
    while not pattern.match(current_line):
        line_index += 1
        if line_index >= len(lines):
            return -1
        current_line = lines[line_index]
    return line_index


__all__ = ['read_meme_output']